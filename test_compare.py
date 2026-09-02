"""Smoke test: run the comparison against the synthetic freelancer sheet."""
from pathlib import Path

import pandas as pd

import compare_core as cc

APP_DIR = Path(__file__).parent
MATCH = "Match 4"

ref = pd.read_csv(APP_DIR / "ZCD_IPL2026_balls.csv", low_memory=False)
ref.columns = [str(c).lstrip("﻿") for c in ref.columns]
ref_match = ref[ref["match_name"] == MATCH].copy()
up = pd.read_excel(APP_DIR / "sample_freelancer_upload.xlsx", sheet_name="balls")

mapping = cc.build_column_map(list(ref.columns), list(up.columns))
key = cc.pick_key(mapping)
offset = cc.detect_over_offset(ref_match, up, mapping["over_number"])
guess = cc.guess_match(up, ref, mapping)

print(f"key            : {key}")
print(f"over offset    : {offset}  (expected 1)")
print(f"guessed match  : {guess}  (expected {MATCH})")
print(f"mapped columns : {len(mapping)}")
unmapped = [c for c in up.columns if c not in set(mapping.values())]
print(f"unmapped upload: {unmapped}")

scored = [c for c in cc.CODED_FIELDS if c in mapping and c not in key]
summary, mis, align = cc.compare(
    ref_match, up, mapping, key, scored,
    case_insensitive=True, numeric_tol=0.0, ignore_blank_reference=True, over_offset=offset,
)

print("\n--- alignment ---")
print(f"ref {align['ref_balls']}  upload {align['upload_balls']}  matched {align['matched_balls']}")
print(f"missing in upload: {len(align['missing_in_upload'])} (expected 1)")
print(f"extra in upload  : {len(align['extra_in_upload'])} (expected 0)")
print(f"duplicate keys   : {align['duplicate_keys_in_upload']} (expected 1)")

print("\n--- scorecard ---")
print(summary.to_string(index=False))

tot_c, tot_m = summary["compared"].sum(), summary["matched"].sum()
print(f"\noverall: {tot_m / tot_c * 100:.2f}%  ({tot_m}/{tot_c})")

print(f"\nmismatch rows: {len(mis)}")
print(mis.head(12).to_string(index=False))

print("\n--- wagon_wheel_x with tolerance 5 ---")
s2, _, _ = cc.compare(ref_match, up, mapping, key, ["wagon_wheel_x"],
                      numeric_tol=5.0, over_offset=offset)
print(s2.to_string(index=False))
