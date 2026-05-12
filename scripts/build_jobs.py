#!/usr/bin/env python3
"""
Build src/data/jobs.json from job.xml + council.xml.

Each job in job.xml is one of three families:
  • Council slots (Ambassador, Chancellor, Spymaster, Grand Vizier) — bonus
    yields scale with the assigned character's ratings, defined in council.xml
    via aaiRatingYieldCity and aaiRatingYieldGlobal.
  • Slot flags (bGeneral, bGovernor, bAgent, bExplorer) — generic command roles
    with a flat assignment opinion modifier.

We render each job as: name, slot type, prereq tech (Council jobs), trait
prereqs, assignment opinion, and an `effects` list of humanized rating-yield
bonuses for Council jobs.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import (  # noqa: E402
    yield_name, _lookup_name, fmt_decimal,
)

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "jobs.json"


# Plain-English label for each iconic job entry. The job.xml Name fields
# point at GENDERED_TEXT_* tokens that take an extra resolve step — easier
# to hard-map the small fixed list of jobs.
JOB_LABELS: dict[str, str] = {
    "JOB_AMBASSADOR":   "Ambassador",
    "JOB_CHANCELLOR":   "Chancellor",
    "JOB_SPYMASTER":    "Spymaster",
    "JOB_GENERAL":      "General",
    "JOB_EXPLORER":     "Explorer",
    "JOB_GOVERNOR":     "Governor",
    "JOB_AGENT":        "Agent",
    "JOB_GRAND_VIZIER": "Grand Vizier",
}


RATING_LABELS: dict[str, str] = {
    "RATING_WISDOM":     "Wisdom",
    "RATING_CHARISMA":   "Charisma",
    "RATING_COURAGE":    "Courage",
    "RATING_DISCIPLINE": "Discipline",
}


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
                out[k] = en
    return out


def slot_type(entry: ET.Element) -> str:
    """Classify a job entry into a high-level slot family."""
    if entry.findtext("Council"):
        return "Council"
    if entry.findtext("bGeneral") == "1":
        return "General"
    if entry.findtext("bGovernor") == "1":
        return "Governor"
    if entry.findtext("bAgent") == "1":
        return "Agent"
    if entry.findtext("bExplorer") == "1":
        return "Explorer"
    return "Misc"


def humanize_rating_yields(council_entry: ET.Element, scope: str) -> list[str]:
    """Render aaiRatingYieldCity / aaiRatingYieldGlobal as 'Rating → +N Yield'."""
    out: list[str] = []
    tag = "aaiRatingYieldCity" if scope == "City" else "aaiRatingYieldGlobal"
    for pair in council_entry.findall(f"{tag}/Pair"):
        rating = RATING_LABELS.get(pair.findtext("zIndex") or "", pair.findtext("zIndex") or "")
        for sp in pair.findall("SubPair"):
            y = yield_name(sp.findtext("zSubIndex"))
            v = int(sp.findtext("iValue") or "0")
            # The aaiRatingYieldCity field is "+N yield per rating point" — already
            # a percentage on the per-city yield in-game, so leave as raw int.
            suffix = "/City" if scope == "City" else ""
            out.append(f"+{v} {y}{suffix} per {rating}")
    return out


def humanize_opinion_pairs(council_entry: ET.Element, tag: str, label: str) -> list[str]:
    """Render aiPlayerOpinion / aiTribeOpinion / aiReligionOpinion / aiFamilyOpinion."""
    out: list[str] = []
    for pair in council_entry.findall(f"{tag}/Pair"):
        rating = RATING_LABELS.get(pair.findtext("zIndex") or "", pair.findtext("zIndex") or "")
        v = int(pair.findtext("iValue") or "0")
        out.append(f"+{v} {label} Opinion per {rating}")
    return out


def main() -> int:
    text_infos = load_text("text-infos.xml", "text-concept.xml")

    job_entries = parse("job.xml").findall("Entry")
    council_idx = {e.findtext("zType"): e for e in parse("council.xml").findall("Entry") if e.findtext("zType")}

    jobs: list[dict] = []

    for je in job_entries:
        zid = je.findtext("zType") or ""
        if not zid:
            continue

        name = JOB_LABELS.get(zid, zid.replace("JOB_", "").title())
        st = slot_type(je)

        opinion = je.findtext("iOpinion")
        opinion_val = int(opinion) if opinion and opinion != "0" else 0

        gcr = je.findtext("GameContentRequired") or ""

        effects: list[str] = []
        trait_prereqs: list[str] = []
        tech_prereq: str = ""
        xp: int = 0
        mission: str = ""

        # If this job has an associated Council slot, fold those bonuses in.
        council_id = je.findtext("Council") or ""
        ce = council_idx.get(council_id) if council_id else None
        if ce is not None:
            # Tech prereq (EFFECTPLAYER_TECH_ARISTOCRACY → "Aristocracy")
            ep = ce.findtext("EffectPlayerPrereq") or ""
            if ep.startswith("EFFECTPLAYER_TECH_"):
                tech_prereq = ep.replace("EFFECTPLAYER_TECH_", "").replace("_", " ").title()

            xp_raw = ce.findtext("iXP") or "0"
            xp = int(xp_raw) if xp_raw else 0

            council_op = ce.findtext("iOpinion") or "0"
            if council_op and council_op != "0":
                opinion_val = max(opinion_val, int(council_op))

            mission = (ce.findtext("AssignMission") or "").replace("MISSION_", "").title()

            # Trait prereqs (any of these archetypes can fill the slot)
            for pair in ce.findall("abTraitPrereq/Pair"):
                tid = pair.findtext("zIndex") or ""
                if (pair.findtext("bValue") or "0") == "1":
                    trait_prereqs.append(tid.replace("TRAIT_", "").replace("_ARCHETYPE", "").title())

            # Rating-scaled yields — both global and per-city
            effects.extend(humanize_rating_yields(ce, "Global"))
            effects.extend(humanize_rating_yields(ce, "City"))

            # Rating-scaled opinion modifiers (Ambassador: +3 Player Opinion / Charisma)
            effects.extend(humanize_opinion_pairs(ce, "aiPlayerOpinion", "Foreign Leader"))
            effects.extend(humanize_opinion_pairs(ce, "aiTribeOpinion", "Tribal"))
            effects.extend(humanize_opinion_pairs(ce, "aiReligionOpinion", "Religion"))
            effects.extend(humanize_opinion_pairs(ce, "aiFamilyOpinion", "Family"))

        jobs.append({
            "id": zid,
            "slug": zid.replace("JOB_", "").lower(),
            "name": name,
            "slotType": st,
            "council": council_id,
            "techPrereq": tech_prereq,
            "traitPrereqs": sorted(trait_prereqs),
            "iOpinion": opinion_val,
            "iXP": xp,
            "mission": mission,
            "dlc": gcr,
            "effects": effects,
        })

    # Sort: Council jobs first (alphabetical), then General/Governor/Agent/Explorer
    SLOT_ORDER = ["Council", "General", "Governor", "Agent", "Explorer", "Misc"]
    jobs.sort(key=lambda j: (SLOT_ORDER.index(j["slotType"]), j["name"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(jobs, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(jobs)} jobs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
