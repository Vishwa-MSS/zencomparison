"""
Core comparison logic for the ZCD freelancer coding-QA tool.

Kept separate from the Streamlit UI so it can be unit-tested or driven from a CLI.
"""
from __future__ import annotations

import math
import re

import pandas as pd

# --------------------------------------------------------------------------
# Column name handling
# --------------------------------------------------------------------------


def norm_col(name) -> str:
    """Normalise a column header for fuzzy matching: 'Over Number' -> 'overnumber'."""
    return re.sub(r"[^a-z0-9]", "", str(name).strip().lower())


# Alternative headers freelancers commonly use, keyed by our canonical name.
COLUMN_ALIASES = {
    "innings_number": ["inning", "innings", "inningno", "inningsno", "inn", "inningnumber"],
    "over_number": ["over", "overno", "overnum", "overs"],
    "ball_in_over": ["ball", "ballno", "ballnum", "balloftheover", "ballinovers", "deliveryinover"],
    "ball_number": ["deliveryno", "deliverynumber"],
    "over_ball": ["overdotball", "oversballs", "overandball"],
    "striker": ["batsman", "batter", "onstrike", "strikerbatsman", "batsmanonstrike"],
    "non_striker": ["nonstrikerbatsman", "nonstrikebatsman", "batsman2"],
    "bowler": ["bowlername"],
    "runs_off_bat": ["batruns", "runsoffthebat", "batsmanruns", "runsbat"],
    "extra_runs": ["extras", "extrarun"],
    "wicket_type": ["dismissaltype", "howout", "wicket", "modeofdismissal"],
    "dismissed_player": ["playerdismissed", "batsmanout", "outbatsman"],
    "delivery_type": ["balltype", "variation"],
    "foot_movement": ["footwork"],
    "shot_connection": ["connection", "contact"],
    "stroke": ["shot", "shottype", "shotplayed"],
    "pitch_zone": ["length", "lengthzone", "pitchlength"],
    "stump_zone": ["line", "linezone", "stumpline"],
    "batter_impact_line": ["impactline", "batterimpact"],
    "batter_stump_zone": ["batterstumpline", "impactstumpzone"],
    "bowler_style": ["bowlingstyle", "bowlertype"],
    "bowler_hand": ["bowlingarm", "bowlerarm", "bowlinghand"],
    "striker_hand": ["battinghand", "batterhand", "batsmanhand"],
    "bowling_angle": ["angle", "overroundthewicket", "aroundthewicket"],
    "bowling_end": ["end", "bowlingfromend"],
    "fielder_position": ["fieldingposition", "position", "fieldposition"],
    "fielder_action": ["fieldingaction", "fieldaction"],
    "wagon_wheel_x": ["wagonx", "wwx", "shotx", "shotzonex"],
    "wagon_wheel_y": ["wagony", "wwy", "shoty", "shotzoney"],
    "air_movement": ["aerial", "groundorair"],
    "spin_direction": ["spintype", "spin"],
    "match_name": ["match", "matchno", "matchnumber", "gamename"],
}

# Ball-level fields a human actually codes. These are the defaults that get scored;
# everything else in the export is derived metadata and would skew the number unfairly.
CODED_FIELDS = [
    # what physically happened
    "striker", "non_striker", "bowler",
    "runs_off_bat", "extra_runs", "wide_runs", "no_ball_runs", "bye_runs", "leg_bye_runs",
    "is_legal_delivery", "is_wide", "is_no_ball", "is_bye", "is_leg_bye",
    "is_boundary", "is_free_hit",
    "wicket_type", "dismissed_player", "dismissed_by", "caught_by",
    "stumped_by", "run_out_fielder_1",
    # bowling judgement
    "bowler_hand", "bowler_style", "bowling_end", "bowling_angle",
    "delivery_type", "spin_direction", "pitch_zone", "stump_zone", "bounce_category",
    # batting judgement
    "striker_hand", "foot_movement", "air_movement", "control",
    "shot_connection", "stroke", "batter_impact_line", "batter_stump_zone",
    # fielding / wagon wheel
    "wagon_wheel_x", "wagon_wheel_y", "fielder", "fielder_position", "fielder_action",
]

KEY_CANDIDATES = [
    ["innings_number", "over_number", "ball_in_over"],
    ["innings_number", "ball_number"],
    ["innings_number", "over_ball"],
]


def build_column_map(ref_cols, up_cols) -> dict:
    """Map reference column -> uploaded column, by exact normalised name then by alias."""
    up_by_norm = {}
    for c in up_cols:
        up_by_norm.setdefault(norm_col(c), c)

    mapping = {}
    for ref_c in ref_cols:
        n = norm_col(ref_c)
        if n in up_by_norm:
            mapping[ref_c] = up_by_norm[n]
            continue
        for alias in COLUMN_ALIASES.get(ref_c, []):
            if alias in up_by_norm:
                mapping[ref_c] = up_by_norm[alias]
                break
    return mapping


def pick_key(mapping: dict) -> list | None:
    """Choose the first key set whose every column is mapped in the upload."""
    for cand in KEY_CANDIDATES:
        if all(c in mapping for c in cand):
            return cand
    return None


# --------------------------------------------------------------------------
# Value handling
# --------------------------------------------------------------------------

BLANKS = {"", "nan", "none", "null", "na", "n/a", "-", "--", "nil", "nat"}
TRUES = {"true", "yes", "y", "1", "1.0", "t"}
FALSES = {"false", "no", "n", "0", "0.0", "f"}


def infer_kind(series: pd.Series) -> str:
    """Decide how a reference column should be compared: bool, num or text."""
    s = series.dropna()
    if s.empty:
        return "text"
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_numeric_dtype(series):
        return "num"
    vals = {str(v).strip().lower() for v in s.unique()[:50]}
    if vals and vals <= (TRUES | FALSES):
        return "bool"
    return "text"


def canon_text(series: pd.Series, case_insensitive: bool = True) -> pd.Series:
    s = series.astype("object").map(
        lambda v: "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)
    )
    s = s.str.strip().str.replace(r"\s+", " ", regex=True)
    s = s.mask(s.str.lower().isin(BLANKS), "")
    return s.str.lower() if case_insensitive else s


def canon_bool(series: pd.Series) -> pd.Series:
    s = canon_text(series, case_insensitive=True)
    return s.map(lambda v: "TRUE" if v in TRUES else ("FALSE" if v in FALSES else v))


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


def _num_token(v):
    if pd.isna(v):
        return ""
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:g}"


def _display(v) -> str:
    """Render one cell for the mismatch report: blanks empty, 4.0 as '4'."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v):
        return ""
    if isinstance(v, float) and float(v).is_integer():
        return str(int(v))
    return str(v).strip()


def _key_series(df: pd.DataFrame, cols, rename=None) -> pd.Series:
    """Build one joinable string key from the key columns, tolerant of 2 vs 2.0 vs ' 2 '."""
    rename = rename or {}
    parts = []
    for c in cols:
        src = rename.get(c, c)
        num = pd.to_numeric(df[src], errors="coerce")
        parts.append(num.map(_num_token) if num.notna().any() else canon_text(df[src]))
    return pd.Series(["|".join(t) for t in zip(*parts)], index=df.index)


def detect_over_offset(ref: pd.DataFrame, up: pd.DataFrame, up_over_col: str) -> int:
    """Freelancers often number overs 1-20 while the export uses 0-19. Offset to subtract."""
    try:
        r_min = pd.to_numeric(ref["over_number"], errors="coerce").min()
        u_min = pd.to_numeric(up[up_over_col], errors="coerce").min()
        diff = int(u_min - r_min)
    except (ValueError, TypeError):
        return 0
    return diff if diff in (1, -1) else 0


def compare(
    ref: pd.DataFrame,
    up: pd.DataFrame,
    mapping: dict,
    key_cols: list,
    columns: list,
    *,
    case_insensitive: bool = True,
    numeric_tol: float = 0.0,
    ignore_blank_reference: bool = True,
    over_offset: int = 0,
):
    """
    Align the uploaded sheet to the reference on `key_cols`, then compare `columns`.

    Returns (summary_df, mismatch_df, alignment_dict).
    """
    ref = ref.copy()
    up = up.copy()

    if over_offset and "over_number" in key_cols:
        up_over = mapping["over_number"]
        up[up_over] = pd.to_numeric(up[up_over], errors="coerce") - over_offset

    ref["_key"] = _key_series(ref, key_cols)
    up["_key"] = _key_series(up, key_cols, rename={c: mapping[c] for c in key_cols})

    n_upload_rows = len(up)
    dup_up = int(up["_key"].duplicated().sum())
    up = up.drop_duplicates("_key", keep="first")

    ref_keys = set(ref["_key"])
    up_keys = set(up["_key"])
    matched_keys = ref_keys & up_keys

    ref_m = ref[ref["_key"].isin(matched_keys)].set_index("_key").sort_index()
    up_m = up[up["_key"].isin(matched_keys)].set_index("_key").sort_index()
    up_m = up_m.reindex(ref_m.index)

    # context columns carried into the mismatch report so every row is identifiable
    ctx_cols = [
        c for c in ("innings_number", "over_number", "ball_in_over", "striker", "bowler")
        if c in ref_m.columns
    ]

    rows = []
    mismatches = []
    statuses = {}

    for col in columns:
        if col not in mapping or col not in ref_m.columns:
            continue
        a_raw = ref_m[col]
        b_raw = up_m[mapping[col]]
        kind = infer_kind(ref[col])

        if kind == "num":
            a = pd.to_numeric(a_raw, errors="coerce")
            b = pd.to_numeric(b_raw, errors="coerce")
            a_blank, b_blank = a.isna(), b.isna()
            equal = ((a - b).abs() <= numeric_tol).fillna(False) | (a_blank & b_blank)
        else:
            a = canon_bool(a_raw) if kind == "bool" else canon_text(a_raw, case_insensitive)
            b = canon_bool(b_raw) if kind == "bool" else canon_text(b_raw, case_insensitive)
            a_blank, b_blank = a.eq(""), b.eq("")
            equal = a == b

        considered = ~a_blank if ignore_blank_reference else pd.Series(True, index=a_raw.index)
        n_cons = int(considered.sum())
        n_ok = int((equal & considered).sum())
        n_missing = int((considered & ~equal & b_blank).sum())   # freelancer left it empty
        n_wrong = int((considered & ~equal & ~b_blank).sum())    # freelancer coded something else

        # Over-coding: reference is blank but the freelancer entered something. Reported
        # even when blank references are skipped, so the skip option can never hide it.
        over_coded = a_blank & ~b_blank
        n_over = int(over_coded.sum())

        rows.append({
            "column": col,
            "uploaded_as": mapping[col],
            "type": kind,
            "compared": n_cons,
            "matched": n_ok,
            "wrong_value": n_wrong,
            "not_coded": n_missing,
            "accuracy_%": round(n_ok / n_cons * 100, 2) if n_cons else float("nan"),
            "coded_where_ref_blank": n_over,
            "ref_blank_skipped": int(a_blank.sum()) if ignore_blank_reference else 0,
        })

        # per-ball verdict for this column, used by the manual row-by-row review
        st_col = pd.Series("skipped", index=a_raw.index, dtype=object)
        st_col[considered & equal] = "match"
        st_col[considered & ~equal & b_blank] = "not coded"
        st_col[considered & ~equal & ~b_blank] = "wrong value"
        st_col[a_blank & b_blank] = "both blank"
        st_col[over_coded] = "coded but reference blank"
        statuses[col] = st_col

        bad = (considered & ~equal) | (over_coded if ignore_blank_reference else False)
        if bad.any():
            blk = ref_m.loc[bad, ctx_cols].copy()
            blk["column"] = col
            # stringify: the report stacks columns of different dtypes into one
            # object column, which Arrow (and therefore st.dataframe) cannot serialise
            blk["reference_value"] = [_display(v) for v in a_raw[bad].values]
            blk["uploaded_value"] = [_display(v) for v in b_raw[bad].values]
            blk["issue"] = [
                "coded but reference blank" if ab
                else ("not coded" if bb else "wrong value")
                for ab, bb in zip(a_blank[bad].values, b_blank[bad].values)
            ]
            mismatches.append(blk.reset_index(drop=True))

    summary = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not summary.empty:
        summary = summary.sort_values("accuracy_%", na_position="last").reset_index(drop=True)

    mismatch_df = pd.concat(mismatches, ignore_index=True) if mismatches else pd.DataFrame()
    if not mismatch_df.empty:
        sort_by = [c for c in ("innings_number", "over_number", "ball_in_over") if c in mismatch_df.columns]
        if sort_by:
            mismatch_df = mismatch_df.sort_values(sort_by + ["column"]).reset_index(drop=True)

    alignment = {
        "ref_balls": len(ref),
        "upload_balls": n_upload_rows,
        "matched_balls": len(matched_keys),
        "missing_in_upload": ref[ref["_key"].isin(ref_keys - up_keys)].drop(columns=["_key"]),
        "extra_in_upload": up[up["_key"].isin(up_keys - ref_keys)].drop(columns=["_key"]),
        "duplicate_keys_in_upload": dup_up,
        "key_cols": key_cols,
        "over_offset": over_offset,
        # aligned frames + per-ball/per-column status, for the manual review tab
        "ref_aligned": ref_m,
        "up_aligned": up_m,
        "status": pd.DataFrame(statuses, index=ref_m.index) if statuses else pd.DataFrame(index=ref_m.index),
        "column_map": {c: mapping[c] for c in columns if c in mapping},
    }
    return summary, mismatch_df, alignment


ISSUE_STATUSES = ("wrong value", "not coded", "coded but reference blank")


def ball_detail(alignment: dict, key: str, columns=None) -> pd.DataFrame:
    """Column-by-column reference vs upload for one ball, for manual review."""
    ref_m, up_m, status = alignment["ref_aligned"], alignment["up_aligned"], alignment["status"]
    cmap = alignment["column_map"]
    cols = list(columns) if columns is not None else list(status.columns)

    return pd.DataFrame([
        {
            "column": c,
            "reference": _display(ref_m.at[key, c]),
            "uploaded": _display(up_m.at[key, cmap[c]]),
            "status": status.at[key, c],
        }
        for c in cols if c in cmap
    ])


def ball_labels(alignment: dict) -> pd.DataFrame:
    """One row per aligned ball: sort order, a human label, and its issue count."""
    ref_m, status = alignment["ref_aligned"], alignment["status"]
    issues = status.isin(ISSUE_STATUSES).sum(axis=1) if not status.empty else pd.Series(0, index=ref_m.index)

    def col(name, default=""):
        return ref_m[name] if name in ref_m.columns else pd.Series(default, index=ref_m.index)

    out = pd.DataFrame({
        "innings": pd.to_numeric(col("innings_number", 0), errors="coerce").fillna(0).astype(int),
        "over": pd.to_numeric(col("over_number", 0), errors="coerce").fillna(0).astype(int),
        "ball": pd.to_numeric(col("ball_in_over", 0), errors="coerce").fillna(0).astype(int),
        "striker": col("striker").astype(str),
        "bowler": col("bowler").astype(str),
        "issues": issues.astype(int),
    }, index=ref_m.index)
    return out.sort_values(["innings", "over", "ball"])


def guess_match(up: pd.DataFrame, ref_all: pd.DataFrame, mapping: dict) -> str | None:
    """
    Work out which match an uploaded sheet belongs to.

    Prefers an explicit match_name/match_id column; otherwise scores every match by how
    much its striker+bowler name set overlaps the upload's.
    """
    for col in ("match_id", "match_name"):
        src = mapping.get(col)
        if src and src in up.columns:
            vals = canon_text(up[src]).replace("", pd.NA).dropna().unique()
            if len(vals) == 1:
                hit = ref_all[canon_text(ref_all[col]) == vals[0]]
                if not hit.empty:
                    return hit["match_name"].iloc[0]

    name_cols = [mapping[c] for c in ("striker", "bowler", "non_striker") if c in mapping]
    if not name_cols:
        return None
    up_names = set()
    for c in name_cols:
        up_names |= set(canon_text(up[c]).replace("", pd.NA).dropna())
    if not up_names:
        return None

    best, best_score = None, 0.0
    for match_name, grp in ref_all.groupby("match_name"):
        ref_names = set(canon_text(grp["striker"])) | set(canon_text(grp["bowler"]))
        ref_names.discard("")
        if not ref_names:
            continue
        score = len(up_names & ref_names) / len(up_names)
        if score > best_score:
            best, best_score = match_name, score
    return best if best_score >= 0.5 else None
