# ZEN Comparison

Checks freelancer ball-by-ball coding against the correct ZCD data, column by column.

## Run it

Double-click **`run.bat`**. It opens at http://localhost:8501.

## How it works

**Left** — the correct data, filtered to one match (filter by team, then match, then innings).
**Right** — upload the freelancer's Excel/CSV for that match.
**Below** — accuracy per column, every mismatch, a manual row-by-row checker, and a
running scoreboard per freelancer.

### Manual check

The automated score tells you *how much* disagrees. The **🔎 Manual check** tab is for
deciding *who was right*. It walks the match one ball at a time:

- **Only balls with issues** (on by default) skips the balls that already agree
- ◀ Previous / Next ▶, or jump straight to any ball from the dropdown
- For the selected ball you get every scored column side by side — reference value,
  uploaded value, and a status (✅ match, ❌ wrong value, ⬜ not coded, ➕ extra).
  **Hide columns that already match** narrows it to just the disputed ones
- The reference commentary for that ball is shown, so you can adjudicate without
  opening the video
- Record a verdict per ball — *Freelancer correct* / *Error confirmed* / *Unsure* —
  plus a free-text note

Verdicts roll up into counters at the bottom and export via **⬇️ Download manual review
notes**. They live in the browser session only, so download before closing the tab.

### It handles the messy parts automatically

| Problem | What happens |
|---|---|
| Workbook has many sheets | The sheet named **balls** is the one compared; others are ignored. Loose match on case/spacing (`Balls`, `BALLS`, `ball by ball`). If there is no such sheet you're warned and asked to pick one. |
| Freelancer renamed the headers | `Length` → `pitch_zone`, `Shot` → `stroke`, `Batsman` → `striker` … matched by name and alias. Extra columns are ignored. |
| Freelancer numbered overs 1–20 | Detected; the export uses 0–19. Override in the sidebar. |
| Wrong match uploaded | Detected from the player names, with a one-click switch. |
| `  DRIVE ` vs `Drive` | Treated as equal (toggle in sidebar). |
| Balls missing or duplicated | Rows are joined on innings + over + ball, never on row position. Missing/extra balls are listed separately. |
| Wagon-wheel coordinates | Set a numeric tolerance (2–5) so near-enough counts as correct. |
| Narrow screen | **Stack panes vertically** in the sidebar puts the upload box under the reference table. Collapsing the sidebar also gains width. |

### What gets scored

The **Coded fields** preset scores only the ~45 fields a human actually enters — deliveries,
shots, zones, fielding, wagon wheel. Derived columns (`over_totalRuns`, `inning_*`,
`commentary`, timestamps) are excluded so they can't inflate or deflate the number.
Switch to *All matching columns* or *Custom* in the sidebar to change that.

Each column reports three distinct failures, which matter differently:

- **wrong_value** — coded something, but not what the reference says
- **not_coded** — left blank where the reference has a value
- **coded_where_ref_blank** — entered a value where the reference has none (shown but not scored)

Columns the reference itself leaves blank are skipped by default, so a field like
`control` (31% filled) doesn't drag a freelancer's score down.

## Files

| File | Purpose |
|---|---|
| `app.py` | The Streamlit interface |
| `compare_core.py` | Matching + comparison logic (no UI, so it's testable) |
| `ZCD_IPL2026_balls.csv` | Reference data — 17,520 balls, 74 matches, 132 columns |
| `scoreboard.csv` | Created on first save; freelancer history |
| `run.bat` | Launcher |
| `make_test_file.py` | Builds a synthetic 4-sheet freelancer workbook with known errors |
| `test_compare.py` / `test_app.py` | Smoke tests for the logic and the UI |

## Giving freelancers the right shape

The left pane has **⬇️ Blank coding template for this match** — the match's balls with
the coded columns emptied. If they code into that, the alignment is exact and the
comparison is purely about their judgement.

## Adding another tournament

Drop any ZCD export (`.csv` or `.xlsx`) into this folder; it appears in the sidebar's
reference-file dropdown. It needs `match_name`, `team1`, `team2`, `innings_number`,
`over_number`, `ball_in_over`.

## Tests

```
.venv\Scripts\python.exe make_test_file.py "Match 4"
.venv\Scripts\python.exe test_compare.py
.venv\Scripts\python.exe test_app.py
```
