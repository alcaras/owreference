#!/usr/bin/env python3
"""
One-time: extract the human-curated bonus/shrine/UU/leader descriptions from
the legacy xlsx into src/data/annotations/nations.yaml. After this, the yaml
is the source of truth for those fields; we don't re-read the xlsx.
"""
from pathlib import Path
import re
import openpyxl
import yaml

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "Old World Reference Spreadsheet.xlsx"
OUT = ROOT / "src" / "data" / "annotations" / "nations.yaml"

# Spreadsheet column → nation slug
COL_TO_SLUG = {
    2: "assyria",  3: "babylonia", 4: "carthage", 5: "egypt",
    6: "greece",   7: "hittite",   8: "persia",   9: "rome",
    10: "kush",    11: "aksum",    12: "maurya",  13: "tamil",
    14: "yuezhi",
}

ROW_LAYOUT = {
    "bonuses": [3, 4, 5],     # Bonus 1/2/3
    "shrines": [8, 9, 10, 11],  # Shrine 1/2/3/4
}


def cell(ws, row, col) -> str:
    v = ws.cell(row=row, column=col).value
    return "" if v is None else str(v).strip()


def main() -> None:
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["👑 Nations"]

    out: dict = {"nations": {}}
    for col, slug in COL_TO_SLUG.items():
        bonuses = [cell(ws, r, col) for r in ROW_LAYOUT["bonuses"]]
        shrines = [cell(ws, r, col) for r in ROW_LAYOUT["shrines"]]
        uu = {
            "names": cell(ws, 13, col),
            "traits": cell(ws, 14, col),
            "cost": cell(ws, 15, col),
            "upkeep": cell(ws, 16, col),
            "moveSight": cell(ws, 17, col),
            "u6Card": cell(ws, 18, col),
            "u8Card": cell(ws, 19, col),
        }
        leader = {
            "name": cell(ws, 32, col),
            "spouse": cell(ws, 33, col),
            "heir1": cell(ws, 34, col),
            "heir2": cell(ws, 35, col),
        }
        out["nations"][slug] = {
            "bonuses": [b for b in bonuses if b],
            "shrines": [s for s in shrines if s],
            "uniqueUnit": {k: v for k, v in uu.items() if v},
            "leader": {k: v for k, v in leader.items() if v},
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "# Seeded from the legacy spreadsheet on first build.\n"
        "# After this, edit by hand — the xlsx is no longer consulted.\n"
        "# Re-running this script will OVERWRITE local edits.\n\n"
        + yaml.safe_dump(out, sort_keys=True, allow_unicode=True, width=120)
    )
    print(f"✓ wrote {OUT.relative_to(ROOT)} ({len(out['nations'])} nations)")


if __name__ == "__main__":
    main()
