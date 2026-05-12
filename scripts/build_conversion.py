#!/usr/bin/env python3
"""Copy src/data/annotations/conversion.yaml → src/data/conversion.json so
Astro can import it. The values describe game logic NOT present in XML
(compiled code constants documented in the legacy spreadsheet), so they're
hand-maintained in the yaml file."""
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "data" / "annotations" / "conversion.yaml"
OUT = ROOT / "src" / "data" / "conversion.json"

data = yaml.safe_load(SRC.read_text())
OUT.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
print(f"✓ wrote {OUT.relative_to(ROOT)}")
