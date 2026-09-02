"""
ZEN Comparison - freelancer ball-by-ball coding QA.

Left  : the correct ZCD data, filtered down to one match.
Right : a freelancer's Excel/CSV for that same match.
Below : column-by-column accuracy, every mismatch, and a running scoreboard.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import compare_core as cc

APP_DIR = Path(__file__).parent
SCOREBOARD = APP_DIR / "scoreboard.csv"

st.set_page_config(page_title="ZEN Comparison", page_icon="🏏", layout="wide")


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------


@st.cache_data(show_spinner="Loading reference data...")
def load_reference(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(p)
    else:
        df = pd.read_csv(p, low_memory=False)
    df.columns = [str(c).lstrip("﻿") for c in df.columns]
    return df


# Freelancer workbooks carry several sheets; the ball-by-ball one is what we compare.
BALLS_SHEET_ALIASES = ("balls", "ball", "ballbyball", "ball by ball", "bbb", "ballsdata")


def is_excel(file) -> bool:
    return file.name.lower().endswith((".xlsx", ".xls"))


def list_upload_sheets(file) -> list[str]:
    """Sheet names in an uploaded workbook. Empty list for a CSV."""
    if not is_excel(file):
        return []
    file.seek(0)
    with pd.ExcelFile(file) as xl:
        return list(xl.sheet_names)


def pick_balls_sheet(sheets: list[str]) -> str | None:
    """The sheet named 'balls', matched loosely on case and spacing."""
    for alias in BALLS_SHEET_ALIASES:
        for s in sheets:
            if cc.norm_col(s) == cc.norm_col(alias):
                return s
    return None


def read_upload(file, sheet: str | None = None) -> pd.DataFrame:
    file.seek(0)
    if is_excel(file):
        return pd.read_excel(file, sheet_name=sheet if sheet is not None else 0)
    return pd.read_csv(file, low_memory=False)


def find_reference_files() -> list[Path]:
    """Reference exports sitting next to the app. Samples and templates are not references."""
    skip_prefixes = ("sample_", "template_", "~$")
    files = [
        p for p in APP_DIR.glob("*")
        if p.suffix.lower() in (".csv", ".xlsx", ".xls")
        and p.name != SCOREBOARD.name
        and not p.name.lower().startswith(skip_prefixes)
    ]
    return sorted(files, key=lambda p: (not p.name.startswith("ZCD"), p.name))


REQUIRED_REF_COLS = ["match_name", "team1", "team2", "innings_number", "over_number", "ball_in_over"]


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xl:
        for sheet, df in sheets.items():
            (df if not df.empty else pd.DataFrame({"": ["nothing to report"]})).to_excel(
                xl, sheet_name=sheet[:31], index=False
            )
    return buf.getvalue()


# --------------------------------------------------------------------------
# Sidebar - reference file, match filter, comparison rules
# --------------------------------------------------------------------------

st.sidebar.title("🏏 ZEN Comparison")

ref_files = find_reference_files()
if not ref_files:
    st.error(f"No reference .csv/.xlsx found in {APP_DIR}. Drop the ZCD export in there.")
    st.stop()

ref_path = st.sidebar.selectbox(
    "Reference file (correct data)",
    ref_files,
    format_func=lambda p: p.name,
)
ref_all = load_reference(str(ref_path))

missing_ref_cols = [c for c in REQUIRED_REF_COLS if c not in ref_all.columns]
if missing_ref_cols:
    st.error(
        f"**{ref_path.name}** is not a ZCD reference export — it has no "
        f"`{'`, `'.join(missing_ref_cols)}` column. Pick a different file in the sidebar."
    )
    st.stop()

st.sidebar.caption(f"{len(ref_all):,} balls · {ref_all['match_name'].nunique()} matches · {len(ref_all.columns)} columns")

st.sidebar.header("Match filter")

team_pool = sorted(set(ref_all["team1"].dropna()) | set(ref_all["team2"].dropna()))
team_pick = st.sidebar.selectbox("Team (optional)", ["All teams"] + team_pool)

pool = ref_all
if team_pick != "All teams":
    pool = pool[(pool["team1"] == team_pick) | (pool["team2"] == team_pick)]


def match_label(name: str) -> str:
    row = ref_all[ref_all["match_name"] == name].iloc[0]
    return f"{name} — {row['team1']} vs {row['team2']}"


def match_sort_key(name: str):
    """'Match 7' before 'Match 12'; finals-type names last."""
    parts = str(name).split()
    if len(parts) == 2 and parts[1].isdigit():
        return (0, int(parts[1]), "")
    return (1, 0, str(name))


match_names = sorted(pool["match_name"].dropna().unique(), key=match_sort_key)
if not match_names:
    st.sidebar.warning("No matches for that team.")
    st.stop()

if "match_pick" in st.session_state and st.session_state.match_pick not in match_names:
    del st.session_state["match_pick"]

match_pick = st.sidebar.selectbox("Match", match_names, format_func=match_label, key="match_pick")

ref_match = ref_all[ref_all["match_name"] == match_pick].copy()

innings_opts = sorted(ref_match["innings_number"].dropna().unique())
innings_pick = st.sidebar.multiselect("Innings", innings_opts, default=list(innings_opts))
if innings_pick:
    ref_match = ref_match[ref_match["innings_number"].isin(innings_pick)]

st.sidebar.header("Comparison rules")
case_insensitive = st.sidebar.checkbox("Ignore case & spacing", value=True)
ignore_blank_ref = st.sidebar.checkbox(
    "Skip balls where reference is blank", value=True,
    help="Some columns are empty in the reference. Off = a blank reference counts as a value to match.",
)
numeric_tol = st.sidebar.number_input(
    "Numeric tolerance", min_value=0.0, max_value=50.0, value=0.0, step=0.5,
    help="Wagon-wheel coordinates rarely match to the decimal. Try 2-5 for those.",
)

st.sidebar.header("Fields to score")
scored_preset = st.sidebar.radio(
    "Preset", ["Coded fields (recommended)", "All matching columns", "Custom"],
    help="'Coded fields' scores only what a human actually enters, not derived totals or metadata.",
)

st.sidebar.header("Layout")
stacked = st.sidebar.checkbox(
    "Stack panes vertically", value=False,
    help="Turn on for narrow screens — puts the upload box under the reference table "
         "instead of beside it. Collapsing this sidebar (arrow, top-left) also gains width.",
)


# --------------------------------------------------------------------------
# Main - side by side
# --------------------------------------------------------------------------

st.title("Freelancer coding comparison")

left, right = (st.container(), st.container()) if stacked else st.columns(2, gap="large")

with left:
    st.subheader("✅ Correct data — ZCD")
    st.caption(f"{match_pick} · {ref_match['team1'].iloc[0]} vs {ref_match['team2'].iloc[0]} · {len(ref_match)} balls")

    preview_default = [
        c for c in ("innings_number", "over_number", "ball_in_over", "striker", "bowler",
                    "runs_off_bat", "pitch_zone", "stump_zone", "delivery_type", "stroke")
        if c in ref_match.columns
    ]
    show_cols = st.multiselect(
        "Columns to preview", list(ref_match.columns), default=preview_default, key="prev_cols"
    )
    st.dataframe(ref_match[show_cols] if show_cols else ref_match, height=420,
                 width="stretch", hide_index=True)

    template_cols = [c for c in ref_match.columns if c in cc.CODED_FIELDS]
    key_meta = [c for c in ("innings_number", "over_number", "ball_in_over") if c in ref_match.columns]
    blank_tpl = ref_match[key_meta + [c for c in template_cols if c not in key_meta]].copy()
    for c in blank_tpl.columns:
        if c not in key_meta:
            blank_tpl[c] = ""
    st.download_button(
        "⬇️ Blank coding template for this match",
        data=to_excel_bytes({"template": blank_tpl}),
        file_name=f"template_{str(match_pick).replace(' ', '_')}.xlsx",
        help="Hand this to the freelancer so their sheet lines up with the reference exactly.",
    )

with right:
    st.subheader("📤 Freelancer file")
    freelancer = st.text_input("Freelancer name", placeholder="e.g. Ramesh")
    upload = st.file_uploader("Upload the coded Excel / CSV", type=["xlsx", "xls", "csv"])

    if not upload:
        st.info(
            "Upload a freelancer's sheet for the match selected on the left.\n\n"
            "Column headers are matched automatically — they do not have to be identical, "
            "and extra columns are ignored."
        )

if not upload:
    st.stop()

sheets = list_upload_sheets(upload)
sheet = None

with right:
    if sheets:
        balls_sheet = pick_balls_sheet(sheets)
        if balls_sheet:
            sheet = balls_sheet
            others = [s for s in sheets if s != balls_sheet]
            st.caption(
                f"Workbook has {len(sheets)} sheets — comparing **{balls_sheet}**"
                + (f"; ignoring {', '.join(others)}." if others else ".")
            )
            with st.expander("Compare a different sheet"):
                sheet = st.selectbox("Sheet", sheets, index=sheets.index(balls_sheet))
        else:
            st.warning(
                f"No sheet named **balls** in this workbook. Found: {', '.join(sheets)}. "
                "Pick the ball-by-ball sheet below."
            )
            sheet = st.selectbox("Sheet to compare", sheets)

up_df = read_upload(upload, sheet)
mapping = cc.build_column_map(list(ref_all.columns), list(up_df.columns))

with right:
    st.caption(f"{len(up_df):,} rows · {len(up_df.columns)} columns · {len(mapping)} mapped to reference fields")

    guessed = cc.guess_match(up_df, ref_all, mapping)
    if guessed and guessed != match_pick:
        st.warning(f"This file looks like **{guessed}**, not {match_pick}.")
        if st.button(f"Switch to {guessed}"):
            st.session_state.match_pick = guessed
            st.rerun()
    elif guessed == match_pick:
        st.success(f"File contents match {match_pick}.")

key_cols = cc.pick_key(mapping)
if not key_cols:
    st.error(
        "Could not find ball-identifying columns in the upload. It needs an innings column plus "
        "either over+ball, or a running ball number. Rename the headers and re-upload."
    )
    st.write("Uploaded headers:", list(up_df.columns))
    st.stop()

over_offset = 0
if "over_number" in key_cols:
    over_offset = cc.detect_over_offset(ref_match, up_df, mapping["over_number"])
    over_offset = st.sidebar.number_input(
        "Over numbering offset", min_value=-1, max_value=1, value=int(over_offset),
        help="Reference overs run 0-19. Set 1 if the freelancer numbered them 1-20.",
    )

# which columns to score
comparable = [c for c in ref_match.columns if c in mapping and c not in key_cols]
if scored_preset == "Coded fields (recommended)":
    scored = [c for c in cc.CODED_FIELDS if c in comparable]
elif scored_preset == "All matching columns":
    scored = comparable
else:
    scored = st.sidebar.multiselect(
        "Columns", comparable, default=[c for c in cc.CODED_FIELDS if c in comparable]
    )

if not scored:
    st.warning("No columns selected to score.")
    st.stop()

summary, mismatches, align = cc.compare(
    ref_match, up_df, mapping, key_cols, scored,
    case_insensitive=case_insensitive,
    numeric_tol=numeric_tol,
    ignore_blank_reference=ignore_blank_ref,
    over_offset=over_offset,
)

total_cmp = int(summary["compared"].sum()) if not summary.empty else 0
total_ok = int(summary["matched"].sum()) if not summary.empty else 0
overall = total_ok / total_cmp * 100 if total_cmp else 0.0

st.divider()
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Overall accuracy", f"{overall:.1f}%")
m2.metric("Balls matched", f"{align['matched_balls']} / {align['ref_balls']}")
m3.metric("Fields compared", f"{total_cmp:,}")
m4.metric("Wrong values", f"{int(summary['wrong_value'].sum()):,}" if not summary.empty else "0")
m5.metric("Not coded", f"{int(summary['not_coded'].sum()):,}" if not summary.empty else "0")

if align["matched_balls"] == 0:
    st.error(
        f"No balls lined up on key {align['key_cols']}. Check the match selection and the "
        "over-numbering offset in the sidebar."
    )
    st.stop()

if align["duplicate_keys_in_upload"]:
    st.warning(f"{align['duplicate_keys_in_upload']} duplicate ball rows in the upload — first kept, rest ignored.")

tab_score, tab_mis, tab_manual, tab_align, tab_map, tab_board = st.tabs(
    ["📊 Column scorecard", "🔍 Mismatches", "🔎 Manual check",
     "⚖️ Ball alignment", "🔗 Column mapping", "🏆 Scoreboard"]
)

with tab_score:
    st.dataframe(
        summary,
        width="stretch", height=560, hide_index=True,
        column_config={
            "accuracy_%": st.column_config.ProgressColumn(
                "accuracy", min_value=0, max_value=100, format="%.1f%%"
            ),
            "coded_where_ref_blank": st.column_config.NumberColumn(
                "coded_where_ref_blank",
                help="Freelancer entered a value where the reference has none. Not counted in accuracy.",
            ),
        },
    )
    weak = summary[summary["accuracy_%"] < 90]
    if not weak.empty:
        st.caption(
            "Below 90%: "
            + ", ".join(f"{r['column']} ({r['accuracy_%']:.0f}%)" for _, r in weak.iterrows())
        )

with tab_mis:
    if mismatches.empty:
        st.success("No mismatches on the scored columns.")
    else:
        c1, c2 = st.columns(2)
        col_filter = c1.multiselect("Column", sorted(mismatches["column"].unique()))
        issue_filter = c2.multiselect("Issue", sorted(mismatches["issue"].unique()))
        view = mismatches
        if col_filter:
            view = view[view["column"].isin(col_filter)]
        if issue_filter:
            view = view[view["issue"].isin(issue_filter)]
        st.caption(f"{len(view):,} of {len(mismatches):,} mismatches")
        st.dataframe(view, width="stretch", height=560, hide_index=True)

with tab_align:
    st.write(
        f"Reference **{align['ref_balls']}** balls · upload **{align['upload_balls']}** rows · "
        f"matched **{align['matched_balls']}** on key `{' + '.join(align['key_cols'])}`"
    )
    a, b = st.columns(2)
    with a:
        st.markdown("**Balls missing from the upload**")
        miss = align["missing_in_upload"]
        st.dataframe(
            miss[[c for c in ("innings_number", "over_number", "ball_in_over", "striker", "bowler") if c in miss.columns]],
            width="stretch", height=340, hide_index=True,
        )
    with b:
        st.markdown("**Extra balls in the upload**")
        st.dataframe(align["extra_in_upload"], width="stretch", height=340, hide_index=True)

with tab_manual:
    st.markdown("Walk the match ball by ball and check every column yourself.")

    labels = cc.ball_labels(align)
    verdicts = st.session_state.setdefault("verdicts", {})
    review_scope = f"{match_pick}|{upload.name}"

    nav, detail = st.columns([1, 2], gap="large")
    chosen = None

    with nav:
        only_issues = st.checkbox(
            "Only balls with issues", value=True,
            help=f"{int((labels['issues'] > 0).sum())} of {len(labels)} balls have at least one mismatch.",
        )
        walk = labels[labels["issues"] > 0] if only_issues else labels

        if walk.empty:
            st.success("No balls with issues. Untick the box above to walk every ball.")
        else:
            keys = list(walk.index)

            def ball_text(k):
                r = walk.loc[k]
                flag = f"  ⚠ {r['issues']}" if r["issues"] else "  ✅"
                return f"Inn {r['innings']} · {r['over']}.{r['ball']} · {r['striker']} vs {r['bowler']}{flag}"

            # the selectbox is the single source of truth; the buttons move its value
            sel_key = f"manual_sel::{review_scope}::{only_issues}"
            if st.session_state.get(sel_key) not in keys:
                st.session_state[sel_key] = keys[0]
            cur = keys.index(st.session_state[sel_key])

            b1, b2 = st.columns(2)
            if b1.button("◀ Previous", width="stretch", disabled=cur == 0):
                st.session_state[sel_key] = keys[cur - 1]
                st.rerun()
            if b2.button("Next ▶", width="stretch", disabled=cur >= len(keys) - 1):
                st.session_state[sel_key] = keys[cur + 1]
                st.rerun()

            chosen = st.selectbox("Ball", keys, format_func=ball_text, key=sel_key)
            cur = keys.index(chosen)
            st.caption(f"Ball {cur + 1} of {len(keys)}")
            st.progress((cur + 1) / len(keys))

            row = walk.loc[chosen]
            st.markdown(
                f"**Innings {row['innings']}, over {row['over']}.{row['ball']}**  \n"
                f"{row['striker']} facing {row['bowler']}"
            )
            if "commentary" in align["ref_aligned"].columns:
                note = align["ref_aligned"].at[chosen, "commentary"]
                if pd.notna(note):
                    st.caption(str(note))

    if chosen is not None:
        with detail:
            hide_ok = st.checkbox("Hide columns that already match", value=False)
            d = cc.ball_detail(align, chosen, scored)
            if hide_ok:
                d = d[d["status"].isin(cc.ISSUE_STATUSES)]

            icons = {
                "match": "✅ match", "wrong value": "❌ wrong value",
                "not coded": "⬜ not coded", "coded but reference blank": "➕ extra",
                "both blank": "· both blank", "skipped": "· not scored",
            }
            d["status"] = d["status"].map(lambda s: icons.get(s, s))
            st.dataframe(d, width="stretch", height=430, hide_index=True)

            st.markdown("**Your verdict on this ball**")
            v = verdicts.get((review_scope, chosen), {})
            vc1, vc2 = st.columns([1, 2])
            choice = vc1.radio(
                "Verdict", ["Not reviewed", "Freelancer correct", "Error confirmed", "Unsure"],
                index=["Not reviewed", "Freelancer correct", "Error confirmed", "Unsure"].index(
                    v.get("verdict", "Not reviewed")
                ),
                key=f"verdict::{review_scope}::{chosen}",
            )
            note = vc2.text_area(
                "Note (optional)", value=v.get("note", ""),
                key=f"note::{review_scope}::{chosen}", height=120,
            )
            if choice != "Not reviewed" or note:
                verdicts[(review_scope, chosen)] = {
                    "verdict": choice, "note": note,
                    "innings": int(row["innings"]), "over": int(row["over"]), "ball": int(row["ball"]),
                    "striker": row["striker"], "bowler": row["bowler"], "issues": int(row["issues"]),
                }
            else:
                verdicts.pop((review_scope, chosen), None)

    mine = {k: val for (scope, k), val in verdicts.items() if scope == review_scope}
    if mine:
        st.divider()
        rev = pd.DataFrame(list(mine.values()))
        counts = rev["verdict"].value_counts()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Balls reviewed", len(rev))
        c2.metric("Freelancer correct", int(counts.get("Freelancer correct", 0)))
        c3.metric("Errors confirmed", int(counts.get("Error confirmed", 0)))
        c4.metric("Unsure", int(counts.get("Unsure", 0)))
        st.dataframe(
            rev[["innings", "over", "ball", "striker", "bowler", "issues", "verdict", "note"]]
            .sort_values(["innings", "over", "ball"]),
            width="stretch", hide_index=True,
        )
        st.download_button(
            "⬇️ Download manual review notes",
            data=to_excel_bytes({"Manual review": rev}),
            file_name=f"manual_review_{(freelancer or 'freelancer').replace(' ', '_')}"
                      f"_{str(match_pick).replace(' ', '_')}.xlsx",
        )
        st.caption("Verdicts live in this browser session — download them before closing the tab.")


with tab_map:
    unmapped_ref = [c for c in cc.CODED_FIELDS if c in ref_all.columns and c not in mapping]
    unmapped_up = [c for c in up_df.columns if c not in set(mapping.values())]
    a, b = st.columns(2)
    a.markdown("**Matched columns**")
    a.dataframe(
        pd.DataFrame({"reference": list(mapping), "uploaded as": list(mapping.values())}),
        width="stretch", height=380,
    )
    b.markdown("**Coded fields with no column in the upload**")
    b.write(unmapped_ref or "None — every coded field was found.")
    b.markdown("**Uploaded columns not used**")
    b.write(unmapped_up or "None.")

with tab_board:
    st.markdown("Save each review here to track a freelancer across matches.")
    if st.button("💾 Save this result to the scoreboard", disabled=not freelancer):
        row = pd.DataFrame([{
            "reviewed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "freelancer": freelancer,
            "match": match_pick,
            "file": upload.name,
            "balls_ref": align["ref_balls"],
            "balls_matched": align["matched_balls"],
            "fields_compared": total_cmp,
            "accuracy_%": round(overall, 2),
            "wrong_values": int(summary["wrong_value"].sum()),
            "not_coded": int(summary["not_coded"].sum()),
        }])
        row.to_csv(SCOREBOARD, mode="a", header=not SCOREBOARD.exists(), index=False)
        st.success(f"Saved {freelancer} — {match_pick} at {overall:.1f}%")
    if not freelancer:
        st.caption("Enter a freelancer name on the right to enable saving.")

    if SCOREBOARD.exists():
        board = pd.read_csv(SCOREBOARD)
        st.markdown("**By freelancer**")
        agg = board.groupby("freelancer").agg(
            matches=("match", "nunique"),
            reviews=("match", "size"),
            fields_compared=("fields_compared", "sum"),
            avg_accuracy=("accuracy_%", "mean"),
            worst_match=("accuracy_%", "min"),
        ).round(2).sort_values("avg_accuracy", ascending=False)
        st.dataframe(agg, width="stretch")
        st.markdown("**Every review**")
        st.dataframe(board.sort_values("reviewed_at", ascending=False), width="stretch", hide_index=True)

st.divider()
report_name = f"QA_{(freelancer or 'freelancer').replace(' ', '_')}_{str(match_pick).replace(' ', '_')}.xlsx"
st.download_button(
    "⬇️ Download full comparison report (Excel)",
    data=to_excel_bytes({
        "Summary": summary,
        "Mismatches": mismatches,
        "Missing balls": align["missing_in_upload"].head(2000),
        "Extra balls": align["extra_in_upload"].head(2000),
        "Column mapping": pd.DataFrame({"reference": list(mapping), "uploaded_as": list(mapping.values())}),
    }),
    file_name=report_name,
    type="primary",
)
