#!/usr/bin/env python3
"""
Build src/data/missions.json — Rally Troops, Hold Court, Steal Research.

Source XMLs:
  mission.xml          — mission metadata (prereqs, cost, dice weights, subject)
  missionResult.xml    — each outcome (success/event/etc.) and the bonus it grants
  bonus.xml            — the actual yield rewards (base + per-rating scaling)
  text-mission.xml     — human-friendly names + descriptions

These three missions all share the dice-weighted outcome structure. We
fold their XML into one JSON keyed by mission slug, ready for the page.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import _strip_link_templates  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "missions.json"

MISSIONS = [
    ("rally",          "MISSION_RALLY_TROOPS"),
    ("hold-court",     "MISSION_HOLD_COURT"),
    ("steal-research", "MISSION_STEAL_RESEARCH"),
]


def parse(name: str) -> ET.Element:
    return ET.parse(XML_DIR / name).getroot()


def load_text(*filenames: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in filenames:
        p = XML_DIR / fn
        if not p.exists():
            continue
        for e in ET.parse(p).getroot().findall("Entry"):
            k = e.findtext("zType") or ""
            en = (e.findtext("en-US") or "").split("~")[0].strip()
            if k:
                out[k] = _strip_link_templates(en)
    return out


def index(name: str) -> dict[str, ET.Element]:
    return {e.findtext("zType"): e for e in parse(name).findall("Entry") if e.findtext("zType")}


def yield_pairs(e: ET.Element, *tags: str) -> list[dict]:
    out: list[dict] = []
    for tag in tags:
        for pair in e.findall(f"{tag}/Pair"):
            y = (pair.findtext("zIndex") or "").replace("YIELD_", "")
            v = int(pair.findtext("iValue") or "0")
            out.append({"yield": y.lower(), "label": y.title(), "value": v, "scope": tag})
    return out


def main() -> int:
    text = load_text(
        "text-mission.xml", "text-missionResult.xml", "text-infos.xml",
        "text-tech.xml", "text-subject.xml",
    )
    missions_idx = index("mission.xml")
    results_idx = index("missionResult.xml")
    bonus_idx = index("bonus.xml")

    out: list[dict] = []
    for slug, mid in MISSIONS:
        m = missions_idx.get(mid)
        if m is None:
            print(f"⚠ missing mission {mid}", file=sys.stderr)
            continue

        name = text.get(m.findtext("Name") or "", mid.replace("MISSION_", "").title())
        desc = text.get(m.findtext("Description") or "", "")
        turns = int(m.findtext("iMissionTurns") or "0")
        tech_prereq = m.findtext("TechPrereq")
        tech_name = (
            text.get(f"TEXT_{tech_prereq}", tech_prereq.replace("TECH_", "").replace("_", " ").title())
            if tech_prereq else None
        )
        subject = (m.findtext("SubjectCharacter") or "").replace("SUBJECT_", "")
        subject_label = subject.replace("_", " ").title() if subject else ""

        cost = []
        for pair in m.findall("aiYieldCost/Pair"):
            y = (pair.findtext("zIndex") or "").replace("YIELD_", "")
            v = int(pair.findtext("iValue") or "0")
            # Game stores yields ×10 for display, except Orders which are 1:1
            display = v / 10 if y not in ("ORDERS",) else v
            cost.append({"yield": y.lower(), "label": y.title(), "value": display})

        # Outcomes: aiResultDie holds {result_id: dice_weight}. Probability =
        # weight / total. Each result gets enriched with its bonus reward.
        outcomes_raw = m.findall("aiResultDie/Pair")
        total_weight = sum(int(p.findtext("iValue") or "0") for p in outcomes_raw)

        outcomes: list[dict] = []
        for p in outcomes_raw:
            rid = p.findtext("zIndex") or ""
            weight = int(p.findtext("iValue") or "0")
            result = results_idx.get(rid)
            outcome: dict = {
                "id": rid,
                "weight": weight,
                "probability": (weight / total_weight) if total_weight else 0,
                "name": text.get(
                    (result.findtext("Name") if result is not None else "") or "",
                    rid.replace("MISSIONRESULT_", "").replace("_", " ").title(),
                ),
                "description": text.get(
                    (result.findtext("Description") if result is not None else "") or "",
                    "",
                ),
                "rewards": [],
                "ratingModifier": [],
            }
            if result is not None:
                # Rating modifier on the result (e.g., Steal Research +24 Wisdom influence)
                for rp in result.findall("aiRatingModifier/Pair"):
                    r = (rp.findtext("zIndex") or "").replace("RATING_", "")
                    v = int(rp.findtext("iValue") or "0")
                    outcome["ratingModifier"].append({"rating": r.lower(), "label": r.title(), "value": v})

                # Resolve the bonus → yield rewards (base + per-rating scaling)
                bonus_id = result.findtext("TargetBonus")
                bonus = bonus_idx.get(bonus_id) if bonus_id else None
                if bonus is not None:
                    outcome["rewards"] = (
                        yield_pairs(bonus, "aiGlobalYieldsBase", "aiOtherYieldsBase", "aiYieldsBase")
                        + yield_pairs(bonus, "aiGlobalYieldsPer", "aiOtherYieldsPer", "aiYieldsPer")
                    )
                    if bonus.findtext("bRandomCourtier") == "1":
                        outcome["rewards"].append({"label": "Gain a random Courtier", "value": None, "scope": "Special"})

            outcomes.append(outcome)

        out.append({
            "slug": slug,
            "id": mid,
            "name": name,
            "description": desc,
            "turns": turns,
            "subject": subject_label,
            "techPrereq": (
                {"id": tech_prereq, "label": tech_name, "slug": tech_prereq.replace("TECH_", "").lower().replace("_", "-")}
                if tech_prereq else None
            ),
            "cost": cost,
            "outcomes": outcomes,
            "totalDiceWeight": total_weight,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(out)} missions")
    for m in out:
        cost_str = ", ".join(f"{c['value']} {c['label']}" for c in m["cost"])
        print(f"  · {m['name']:20} {m['turns']} turn · {len(m['outcomes'])} outcomes · cost {cost_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
