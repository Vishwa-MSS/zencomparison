"""
Build a synthetic 'freelancer' sheet from the reference so the comparison can be
exercised without waiting for a real one. Deliberately introduces the mistakes we
expect in the wild: renamed headers, 1-based overs, wrong values, blanks,
a dropped ball and a duplicated ball.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

APP_DIR = Path(__file__).parent
MATCH = sys.argv[1] if len(sys.argv) > 1 else "Match 4"
OUT = APP_DIR / "sample_freelancer_upload.xlsx"

ref = pd.read_csv(APP_DIR / "ZCD_IPL2026_balls.csv", low_memory=False)
ref.columns = [str(c).lstrip("﻿") for c in ref.columns]
m = ref[ref["match_name"] == MATCH].copy().reset_index(drop=True)

keep = [
    "innings_number", "over_number", "ball_in_over", "striker", "non_striker", "bowler",
    "runs_off_bat", "extra_runs", "is_wide", "is_no_ball", "is_boundary",
    "wicket_type", "dismissed_player", "bowler_style", "bowling_angle",
    "delivery_type", "foot_movement", "shot_connection", "stroke",
    "pitch_zone", "stump_zone", "batter_impact_line",
    "wagon_wheel_x", "wagon_wheel_y", "fielder_position", "fielder_action",
]
f = m[[c for c in keep if c in m.columns]].copy()

rng = np.random.default_rng(7)

# 1-based over numbering, the most common freelancer habit
f["over_number"] = f["over_number"] + 1

# wrong values on a few judgement columns
for col, rate in [("pitch_zone", 0.12), ("stroke", 0.18), ("delivery_type", 0.09),
                  ("foot_movement", 0.06), ("shot_connection", 0.15)]:
    idx = rng.choice(f.index, size=int(len(f) * rate), replace=False)
    pool = f[col].dropna().unique()
    f.loc[idx, col] = rng.choice(pool, size=len(idx))

# fields simply left uncoded
for col, rate in [("fielder_position", 0.10), ("stump_zone", 0.05)]:
    idx = rng.choice(f.index, size=int(len(f) * rate), replace=False)
    f.loc[idx, col] = np.nan

# coordinates entered by eye - close but not exact
jitter = rng.normal(0, 3, size=len(f))
f["wagon_wheel_x"] = (pd.to_numeric(f["wagon_wheel_x"], errors="coerce") + jitter).round(2)

# casing and spacing drift
f["stroke"] = f["stroke"].astype("object").map(lambda v: f"  {str(v).upper()} " if pd.notna(v) else v)

# renamed headers
f = f.rename(columns={
    "innings_number": "Innings", "over_number": "Over", "ball_in_over": "Ball",
    "striker": "Batsman", "non_striker": "Non Striker", "bowler": "Bowler",
    "runs_off_bat": "Bat Runs", "extra_runs": "Extras", "pitch_zone": "Length",
    "stump_zone": "Line", "stroke": "Shot", "foot_movement": "Footwork",
    "delivery_type": "Ball Type", "fielder_position": "Fielding Position",
    "wagon_wheel_x": "Wagon X", "wagon_wheel_y": "Wagon Y",
})

# one ball dropped, one duplicated, plus a junk column
f = f.drop(index=f.index[40]).reset_index(drop=True)
f = pd.concat([f, f.iloc[[10]]], ignore_index=True)
f["Coder Notes"] = ""

# Real freelancer workbooks carry several sheets; only 'balls' should be compared.
# The decoys deliberately contain look-alike columns to prove the wrong sheet isn't picked.
info = pd.DataFrame({
    "Field": ["Match", "Coder", "Coded on", "Version"],
    "Value": [MATCH, "Test Coder", "2026-09-01", "v2"],
})
squads = pd.DataFrame({
    "Innings": [1, 1, 2, 2],
    "Over": [0, 0, 0, 0],
    "Ball": [1, 2, 1, 2],
    "Batsman": ["DECOY A", "DECOY B", "DECOY C", "DECOY D"],
})

with pd.ExcelWriter(OUT, engine="xlsxwriter") as xl:
    info.to_excel(xl, sheet_name="Match Info", index=False)
    squads.to_excel(xl, sheet_name="Squads", index=False)
    f.to_excel(xl, sheet_name="balls", index=False)
    f.head(20).to_excel(xl, sheet_name="Summary", index=False)

print(f"wrote {OUT}")
print(f"  sheets: Match Info, Squads, balls ({len(f)} rows x {len(f.columns)} cols), Summary")
print(f"  balls sheet built from {MATCH}")
