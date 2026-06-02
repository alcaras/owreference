#!/usr/bin/env python3
"""
Build src/data/harvest_events.json from eventStory*.xml + eventOption*.xml
+ bonus*.xml + the text-* string tables.

A "Harvest Event" is any EventStory with Class=EVENTCLASS_HARVESTING. It fires
when a Worker finishes gathering a tile Resource. For each we capture:

  - title / narrative body
  - the resource that triggered it (SUBJECT_RESOURCE_*) + its icon slug
  - each player option's text and the *humanized* reward (real yield numbers,
    not the raw BONUS_* token) so the page can colour chips like the Missions tab.

Reward humanization reuses the small helpers from build_missions.py and adds the
extra bonus fields that event bonuses use (culture-by-level, add-resource,
ratings, happiness, courtiers, nested aeBonuses). Event bonuses live in the
bonus-event*.xml DLC files, NOT just bonus.xml — index them all.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from humanize import _strip_link_templates  # noqa: E402
from build_missions import pairs, _trim, _tok, _fallback_label, _yld, _txt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
XML_DIR = ROOT / "reference" / "XML" / "Infos"
OUT = ROOT / "src" / "data" / "harvest_events.json"


EVENTSTORY_FILES = [
    "eventStory.xml",
    "eventStory-btt.xml",
    "eventStory-eoti.xml",
    "eventStory-sap.xml",
    "eventStory-wd.xml",
    "eventStory-wog.xml",
]

EVENTOPTION_FILES = [
    "eventOption.xml",
    "eventOption-btt.xml",
    "eventOption-eoti.xml",
    "eventOption-sap.xml",
    "eventOption-wd.xml",
    "eventOption-wog.xml",
]

# Every bonus table — event bonuses are split across the DLC files.
BONUS_FILES = [
    "bonus.xml",
    "bonus-event.xml",
    "bonus-event-btt.xml",
    "bonus-event-eoti.xml",
    "bonus-event-sap.xml",
    "bonus-event-wd.xml",
    "bonus-event-wog.xml",
]

TEXT_FILES = [
    "text-eventStory.xml",
    "text-eventStory-btt.xml",
    "text-eventStory-eoti.xml",
    "text-eventStory-sap.xml",
    "text-eventStoryTitle.xml",
    "text-eventStoryTitle-btt.xml",
    "text-eventStoryTitle-sap.xml",
    "text-eventStoryTitle-hittite.xml",
    "text-eventOption.xml",
    "text-eventOption-btt.xml",
    "text-eventOption-sap.xml",
    "text-eventOption-hittite.xml",
    "text-eventStory-hittite.xml",
    "text-eventStory-hittite-2.xml",
    # entity-name tables for nicer reward labels
    "text-infos.xml",
    "text-trait.xml",
    "text-unit.xml",
    "text-courtier.xml",
    "text-rating.xml",
]


def parse_xml(name: str) -> ET.Element | None:
    p = XML_DIR / name
    if not p.exists():
        return None
    try:
        return ET.parse(p).getroot()
    except ET.ParseError:
        return None


def load_texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for fn in TEXT_FILES:
        root = parse_xml(fn)
        if root is None:
            continue
        for entry in root.findall("Entry"):
            k = entry.findtext("zType") or ""
            en = (entry.findtext("en-US") or "").split("~")[0].strip()
            if k:
                out.setdefault(k, en)
    return out


def index_bonuses() -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for fn in BONUS_FILES:
        root = parse_xml(fn)
        if root is None:
            continue
        for entry in root.findall("Entry"):
            zt = entry.findtext("zType") or ""
            if zt:
                out.setdefault(zt, entry)
    return out


def resource_icon_map() -> dict[str, dict[str, str]]:
    """SUBJECT_RESOURCE suffix → {name, icon} resolved from resource.xml.

    Marble/Ore reuse another resource's sprite via zIconName (RESOURCE_STONE /
    RESOURCE_IRON), so the icon slug is NOT always the resource's own name."""
    out: dict[str, dict[str, str]] = {}
    root = parse_xml("resource.xml")
    texts = None
    if root is None:
        return out
    for entry in root.findall("Entry"):
        zt = entry.findtext("zType") or ""
        if not zt.startswith("RESOURCE_"):
            continue
        suffix = zt.replace("RESOURCE_", "")
        icon_tok = entry.findtext("zIconName") or zt
        out[suffix] = {
            "icon": icon_tok.replace("RESOURCE_", "").lower(),
            "name": suffix.replace("_", " ").title(),
        }
    return out


# Match game placeholders like {CITY-1}, {RESOURCE_GOLD}, etc.
_PLACEHOLDER_RE = re.compile(r"\{([A-Z][A-Z0-9_]*)(?:[-,][^{}]*)?\}")


def clean_event_text(s: str) -> str:
    s = _strip_link_templates(s)

    def repl(m):
        tok = m.group(1)
        if tok.startswith("CITY"):
            return "our city"
        if tok.startswith("PLAYER"):
            return "our people"
        if tok.startswith("UNIT"):
            return "our scouts"
        if tok.startswith("LEADER"):
            return "our leader"
        if tok.startswith("CAPITAL"):
            return "our capital"
        if tok.startswith("CHARACTER"):
            return "the subject"
        if tok.startswith("FAMILY"):
            return "the family"
        if tok.startswith("YIELD_"):
            return tok.replace("YIELD_", "").title()
        if tok.startswith("RESOURCE_"):
            return tok.replace("RESOURCE_", "").replace("_", " ").title()
        return tok.replace("_", " ").title()

    return _PLACEHOLDER_RE.sub(repl, s)


# ── reward humanizer ────────────────────────────────────────────────────────
# Superset of build_missions.humanize_bonus: also covers aaiCultureYield,
# AddResource, aiRatings, iHappinessLevels, iLegitimacy, MakeCourtier and
# recursive aeBonuses — the fields harvest/event bonuses lean on.

def _name(text: dict, key: str, fallback_tok: str, *prefixes: str) -> str:
    return text.get(key) or _tok(fallback_tok, *prefixes)


def humanize_bonus(bonus_id: str, idx: dict, text: dict, _seen: set | None = None) -> list[dict]:
    """Structured reward list (see build_missions._yld / _txt). Yields are
    display-scale (shown raw in-game) — no /10."""
    if not bonus_id:
        return []
    _seen = _seen or set()
    if bonus_id in _seen:  # guard against pathological recursion
        return []
    _seen.add(bonus_id)

    b = idx.get(bonus_id)
    if b is None:
        return [_txt(_fallback_label(bonus_id))]
    out: list[dict] = []

    base = {y: v for y, v in pairs(b, "aiGlobalYieldsBase")}
    per = {y: v for y, v in pairs(b, "aiGlobalYieldsPer")}
    for y in list(base) + [k for k in per if k not in base]:
        out.append(_yld(y, base=base.get(y, 0), per=per.get(y, 0)))
    for y, v in pairs(b, "aiCityYields"):
        out.append(_yld(y, each=v))

    # Culture-by-city-level: render the min–max range (display-scale).
    culture_vals: list[int] = []
    for pair in b.findall("aaiCultureYield/Pair"):
        for sp in pair.findall("SubPair"):
            iv = int(sp.findtext("iValue") or "0")
            if iv:
                culture_vals.append(iv)
    if culture_vals:
        lo, hi = min(culture_vals), max(culture_vals)
        rng = f"{lo}" if lo == hi else f"{lo}–{hi}"
        out.append({"text": f"+{rng} Culture (by city culture)", "yield": "culture"})

    add_res = b.findtext("AddResource")
    if add_res:
        out.append(_txt(f"Adds {_name(text, 'TEXT_' + add_res, add_res, 'RESOURCE_')}"))

    for r, v in pairs(b, "aiRatings"):
        out.append(_txt(f"{'+' if v >= 0 else ''}{v} {_name(text, 'TEXT_' + r, r, 'RATING_')}"))

    hap = int(b.findtext("iHappinessLevels") or "0")
    if hap:
        out.append(_txt(f"{'+' if hap >= 0 else ''}{hap} Happiness level{'s' if abs(hap) != 1 else ''}"))

    leg = int(b.findtext("iLegitimacy") or "0")
    if leg:
        out.append(_txt(f"{'+' if leg >= 0 else ''}{leg} Legitimacy"))

    xp = int(b.findtext("iXPCharacter") or "0")
    if xp:
        out.append(_txt(f"+{xp} XP to the character"))

    cour = b.findtext("MakeCourtier")
    if cour:
        out.append(_txt(f"Gain a {_name(text, 'TEXT_' + cour, cour, 'COURTIER_')}"))
    for pair in b.findall("AddCourtier/Pair"):
        ct = pair.findtext("First") or ""
        if ct:
            out.append(_txt(f"Gain a {_name(text, 'TEXT_' + ct, ct, 'COURTIER_')}"))

    for sp in b.findall("aeAddSpecialistClasses/zValue"):
        out.append(_txt(f"Gain a {_name(text, 'TEXT_' + (sp.text or ''), sp.text or '', 'SPECIALISTCLASS_')}"))

    for pr in b.findall("aeAddProjects/zValue"):
        out.append(_txt(f"Begin project: {_name(text, 'TEXT_' + (pr.text or ''), pr.text or '', 'PROJECT_')}"))

    imp = b.findtext("SetImprovement")
    if imp:
        out.append(_txt(f"Build {_name(text, 'TEXT_' + imp, imp, 'IMPROVEMENT_')} on the tile"))

    if (b.findtext("bKillUnit") or "0") == "1":
        out.append(_txt("A unit is killed"))

    for t in b.findall("aeAddTraits/zValue"):
        tr = t.text or ""
        out.append(_txt(f"Gain trait: {_name(text, 'TEXT_' + tr, tr, 'TRAIT_')}"))

    for u, v in pairs(b, "aiUnits"):
        out.append(_txt(f"+{v} {_name(text, 'TEXT_' + u, u, 'UNIT_')}"))
    for u, v in pairs(b, "aiBonusUnits"):
        out.append(_txt(f"+{v} {_tok(u, 'BONUSUNITCLASS_')} unit"))

    reb = int(b.findtext("iRebelUnits") or "0")
    if reb:
        out.append(_txt(f"{reb} rebel unit{'s' if reb != 1 else ''} appear"))

    rel = b.findtext("AddLeaderRelationship")
    if rel:
        out.append(_txt(f"Leader relationship: {_tok(rel, 'RELATIONSHIP_')}"))
    amb = b.findtext("Ambition")
    if amb:
        out.append(_txt(f"Progress ambition: {_tok(amb, 'GOAL_')}"))

    # Nested bonuses (containers like *_OPTION_*_CITY group several payloads).
    for bz in b.findall("aeBonuses/zValue"):
        out += humanize_bonus(bz.text or "", idx, text, _seen)
    for bz in b.findall("aeAllCityBonuses/zValue"):
        out += [{**r, "text": r["text"] + " (every city)"} for r in humanize_bonus(bz.text or "", idx, text, _seen)]

    return out or [_txt(_fallback_label(bonus_id))]


def load_eventstories() -> list[tuple[str, ET.Element]]:
    out: list[tuple[str, ET.Element]] = []
    for fn in EVENTSTORY_FILES:
        root = parse_xml(fn)
        if root is None:
            continue
        for entry in root.findall("Entry"):
            zt = entry.findtext("zType") or ""
            cls = entry.findtext("Class") or ""
            if zt and cls == "EVENTCLASS_HARVESTING":
                out.append((zt, entry))
    return out


def load_options() -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for fn in EVENTOPTION_FILES:
        root = parse_xml(fn)
        if root is None:
            continue
        for entry in root.findall("Entry"):
            zt = entry.findtext("zType") or ""
            if zt:
                out.setdefault(zt, entry)
    return out


def nice_title(zt: str, raw: str) -> str:
    t = clean_event_text(raw)
    if t:
        return t
    return zt.replace("EVENTSTORY_HARVEST_", "").replace("EVENTSTORY_", "").replace("_", " ").title()


def main() -> int:
    texts = load_texts()
    options_idx = load_options()
    bonus_idx = index_bonuses()
    res_map = resource_icon_map()
    stories = load_eventstories()

    items: list[dict] = []
    for zt, entry in stories:
        title = nice_title(zt, texts.get(entry.findtext("Name") or "", ""))
        body = clean_event_text(texts.get(entry.findtext("Text") or "", ""))

        # Trigger resource: SUBJECT_RESOURCE_<X> (skip the bare SUBJECT_RESOURCE).
        resource = ""
        resource_icon = ""
        for sv in entry.findall("aeSubjects/zValue"):
            t = sv.text or ""
            if t.startswith("SUBJECT_RESOURCE_"):
                suffix = t.replace("SUBJECT_RESOURCE_", "")
                meta = res_map.get(suffix, {"name": suffix.replace("_", " ").title(),
                                            "icon": suffix.lower()})
                resource = meta["name"]
                resource_icon = meta["icon"]
                break

        author = entry.findtext("zAuthor") or ""
        bg = entry.findtext("zBackgroundName") or ""

        def reward_strings(bonus_tokens: list[str]) -> list[dict]:
            out: list[dict] = []
            for tok in bonus_tokens:
                out += humanize_bonus(tok, bonus_idx, texts)
            # de-dup by display text while preserving order
            seen, uniq = set(), []
            for r in out:
                if r["text"] not in seen:
                    seen.add(r["text"])
                    uniq.append(r)
            return uniq

        option_objs: list[dict] = []
        # Legacy schema: <aeOptions><zValue>EVENTOPTION_*</zValue></aeOptions>
        for ov in entry.findall("aeOptions/zValue"):
            opt_id = ov.text or ""
            if not opt_id:
                continue
            opt_entry = options_idx.get(opt_id)
            if opt_entry is None:
                continue
            opt_text = clean_event_text(texts.get(opt_entry.findtext("Text") or "", "")) \
                or opt_id.split("_OPTION_")[-1]
            toks = [b.text or "" for b in opt_entry.findall("aeBonuses/zValue") if (b.text or "").strip()]
            option_objs.append({"id": opt_id, "text": opt_text, "rewards": reward_strings(toks)})
        # Inline (newer DLC) schema: <EventOption>... with <SubjectBonuses><Pair>
        for oe in entry.findall("EventOptions/EventOption") + entry.findall("EventOption"):
            opt_text_key = oe.findtext("Text") or ""
            opt_text = clean_event_text(texts.get(opt_text_key, "")) or opt_text_key
            toks = [pair.findtext("Second") or "" for pair in oe.findall("SubjectBonuses/Pair")
                    if (pair.findtext("Second") or "").strip()]
            option_objs.append({"id": opt_text_key, "text": opt_text, "rewards": reward_strings(toks)})

        items.append({
            "id": zt,
            "slug": zt.replace("EVENTSTORY_HARVEST_", "").replace("EVENTSTORY_", "").lower(),
            "title": title,
            "body": body,
            "resource": resource,
            "resourceIcon": resource_icon,
            "author": author,
            "background": bg,
            "options": option_objs,
        })

    items.sort(key=lambda x: x["title"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    n_res = len({i["resource"] for i in items if i["resource"]})
    print(f"✓ wrote {OUT.relative_to(ROOT)} — {len(items)} harvest events, {n_res} resources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
