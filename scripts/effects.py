#!/usr/bin/env python3
"""
Registry-driven effect renderer — the completeness backstop behind humanize.py.

scripts/data/helptext_registry.json is extracted from the game's own help
system (reference/Source HelpText.*.cs): for every XML field the game
renders, it records the field name, the game's TEXT template, arg semantics,
and value scaling. humanize.py keeps its curated phrasing for the fields it
already covers; for everything else its renderers call `extra_lines()` here,
which renders any *populated* registry field generically. Net effect: a new
patch field shows up on the site (in honest generic phrasing) the moment it
appears in the XML, instead of being silently dropped.

scripts/audit_coverage.py consumes HANDLED_FIELDS to verify the union of
humanize + effects coverage against the registry each patch.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from functools import lru_cache

from link_names import XML_DIR, game_name, resolve_links

_REG_PATH = Path(__file__).resolve().parent / "data" / "helptext_registry.json"
REGISTRY: dict = json.loads(_REG_PATH.read_text()) if _REG_PATH.exists() else {}

# Registry fields we deliberately do NOT render generically: icon-only
# renders that need UI context, and pure plumbing. (Description/ExtraHelp
# ARE rendered — they're plain TEXT lookups, see _TEXT_FIELDS.)
SKIP_FIELDS: dict[str, set[str]] = {
    "effectCity": {"zHelpOverride", "Name", "GenderedName"},
    "effectPlayer": {"zHelpOverride", "Name", "GenderedName"},
    "effectUnit": {"zHelpOverride", "zIcon", "Name", "GenderedName"},
    "bonus": {"zHelpOverride", "Event", "Name", "GenderedName", "bOverrideDescription"},
}

# Fields whose value is a TEXT_* key holding a ready-made help line.
_TEXT_FIELDS = {"Description", "ExtraHelp"}

# Minimal copy of the game-string markup cleanup (humanize has the full
# version; we can't import it — humanize imports us). link() resolves to
# the game's name for the token (link_names); icon() is an inline glyph and is dropped outright
# (the surrounding text already carries the word, e.g. "icon(...)Legitimacy").
_ICON_MARKUP_RE = re.compile(r"\{?icon\([A-Z0-9_]+(?:,\d+)?\)\}?")


def _clean_text(s: str) -> str:
    s = _ICON_MARKUP_RE.sub("", s.split("~")[0])
    return resolve_links(s).strip()

# What the audit may count as covered by this module.
HANDLED_FIELDS: dict[str, set[str]] = {
    section: {
        spec.get("xmlField") or key
        for key, spec in fields.items()
        if (spec.get("xmlField") or key) not in SKIP_FIELDS.get(section, set())
    }
    for section, fields in REGISTRY.items()
    if not section.startswith("_")
}

# Populated fields extra_lines() saw but could not shape-parse, keyed by
# section — build scripts may print this after a run for visibility.
UNRENDERED: dict[str, set[str]] = {}


# ────────────────────────────────────────────────────────────────────────────
# Token / label helpers (deliberately self-contained: humanize.py imports us)
# ────────────────────────────────────────────────────────────────────────────

_PREFIXES = (
    "YIELD_", "IMPROVEMENTCLASS_", "IMPROVEMENT_", "UNITTRAIT_", "UNIT_",
    "RESOURCE_", "RELIGION_", "TECH_", "LAW_", "PROJECT_", "TRAIT_",
    "SPECIALISTCLASS_", "SPECIALIST_", "FAMILYCLASS_", "FAMILY_",
    "EFFECTCITY_", "EFFECTPLAYER_", "EFFECTUNIT_", "BONUS_", "TERRAIN_TARGET_",
    "TERRAIN_", "VEGETATION_", "HEIGHT_", "PROMOTION_", "CULTURE_",
    "DIPLOMACY_", "MEMORYPLAYER_", "MEMORYFAMILY_", "STAT_", "RATING_",
)


def _title_token(token: str) -> str:
    s = token
    for p in _PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    return s.replace("_", " ").title()


def resolve_token(token: str, indexes: dict | None) -> str:
    """TOKEN → display name. Tries the entry's Name text via the loaded XML
    indexes (humanize.load_xml_indexes shape), falls back to title-casing."""
    if not token:
        return ""
    if indexes:
        text_idx = indexes.get("__text__", {})
        for fname, idx in indexes.items():
            if fname == "__text__" or not isinstance(idx, dict):
                continue
            entry = idx.get(token)
            if entry is not None and hasattr(entry, "findtext"):
                name_key = entry.findtext("Name") or entry.findtext("GenderedName") or ""
                nice = text_idx.get(name_key, "")
                if nice:
                    return _clean_text(nice)
        # Infos files not in the index (courtier.xml) still name entries TEXT_<zType>.
        nice = text_idx.get(f"TEXT_{token}", "")
        if nice:
            return _clean_text(nice)
    nice = game_name(token)
    # some names are templates filled at runtime ("{UNIT-RELIGION,1} Disciple")
    return nice if nice and "{" not in nice else _title_token(token)


_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def field_label(field: str) -> str:
    """'aiFamilyOpinion' → 'Family Opinion'; 'iWarWeariness' → 'War Weariness'."""
    s = field
    for p in ("aai", "ai", "ae", "ab", "a"):
        if s.startswith(p) and len(s) > len(p) and s[len(p)].isupper():
            s = s[len(p):]
            break
    else:
        if len(s) > 1 and s[0] in "bie" and s[1].isupper():
            s = s[1:]
    return _CAMEL_RE.sub(" ", s)


def _fmt(v: float, pct: bool = False) -> str:
    if v == int(v):
        v = int(v)
    return f"{'+' if v >= 0 else ''}{v}{'%' if pct else ''}"


def _is_pct(field: str, spec: dict) -> bool:
    if "Modifier" in field or "Percent" in field or field.endswith("Prob"):
        return True
    tpl = spec.get("template") or ""
    return "%" in tpl


# ────────────────────────────────────────────────────────────────────────────
# Bare (First, Second) tuples
# ────────────────────────────────────────────────────────────────────────────

# effectUnit fields stored as a bare <First>/<Second> tuple with no <Pair>
# wrapper. _render_field never saw them (no Pair, no text), so they rendered
# nothing; that hid the Tactician's stun and the Grappler's immobilize once
# patch 26433529 moved both from bStun/bImmobilize into AttackApplyEffectUnitTurns.
TUPLE_FIELDS = frozenset({
    "AttackApplyEffectUnitTurns", "AttackerApplyEffectUnitTurns",
    "RemoveApplyEffectUnitTurns", "SelfApplyEffectUnitTurns",
    "UnitTraitFormation", "bApplyEffectUnitAdjacentOnly",
})


def _turns(n: int) -> str:
    return f"{n} Turn" if n == 1 else f"{n} Turns"


def _tuple_lines(entry: ET.Element, exclude, indexes: dict | None) -> list[str]:
    """The game's lines for the tuple fields, as HelpText.Unit.cs builds them
    (buildEffectUnitHelp). Attacked units get turns−1: the count includes the
    turn the effect lands, and the help names only the turns after it."""
    def tup(field):
        el = entry.find(field)
        if el is None or field in exclude:
            return None, 0
        return (el.findtext("First") or "").strip(), int(el.findtext("Second") or 0)

    me = entry.findtext("zType") or ""
    adj = "adjacent " if (entry.findtext("bApplyEffectUnitAdjacentOnly") or "0") == "1" else ""
    name = lambda tok: resolve_token(tok, indexes)
    out: list[str] = []

    def timed(who, eff, n, minus_one=True):
        base = f"Applies {name(eff)} to {adj}{who}"
        if n == 0 or eff == me:
            return base
        if n == 1:
            return f"{base} until the start of their own turn"
        return f"{base} for {_turns(n - 1 if minus_one else n)}"

    eff, n = tup("AttackApplyEffectUnitTurns")
    eff_a, n_a = tup("AttackerApplyEffectUnitTurns")
    if eff:
        if eff == eff_a and n == n_a:
            out.append(timed("Units during combat", eff, n))
        else:
            out.append(timed("attacked Units", eff, n))
    elif eff_a:
        # the game passes the attacker's count through unreduced
        out.append(timed("attacking Units", eff_a, n_a, minus_one=False))

    eff, n = tup("RemoveApplyEffectUnitTurns")
    if n > 0:
        out.append(f"Replace with {name(eff)} after {_turns(n)}" if eff
                   else f"Removed after {_turns(n)}")

    eff, _ = tup("SelfApplyEffectUnitTurns")
    if eff:
        out.append(f"Can apply {name(eff)}")

    trait, _ = tup("UnitTraitFormation")
    if trait:
        out.append(f"Can {name(me)} against {name(trait)} Units.")
    return out


@lru_cache(maxsize=None)
def _tech_prereqs(filename: str) -> dict[str, str]:
    root = ET.parse(XML_DIR / filename).getroot()
    return {e.findtext("zType"): e.findtext("TechPrereq") for e in root.findall("Entry")
            if e.findtext("zType") and e.findtext("TechPrereq")}


# aeVoidTechPrereq* lists name what may be built early; the game's line adds
# the tech being skipped, and drops entries that have no tech to skip.
VOID_TECH_FIELDS = {
    "aeVoidTechPrereqImprovementClass": "improvementClass.xml",
    "aeVoidTechPrereqProject": "project.xml",
}


def _void_tech_lines(el: ET.Element, field: str, indexes: dict | None) -> list[str]:
    techs = _tech_prereqs(VOID_TECH_FIELDS[field])
    return [f"Can build {resolve_token(z.text, indexes)} without {resolve_token(techs[z.text], indexes)}"
            for z in el.findall("zValue") if z.text in techs]


# ────────────────────────────────────────────────────────────────────────────
# Generic shape renderers
# ────────────────────────────────────────────────────────────────────────────

def _render_field(el: ET.Element, field: str, spec: dict, indexes: dict | None) -> list[str]:
    scale = spec.get("valueScale") or 1
    pct = _is_pct(field, spec)
    label = field_label(field)
    out: list[str] = []

    pairs = el.findall("Pair")
    subpairs = [p for p in pairs if p.find("SubPair") is not None]

    if subpairs:
        # aai*: outer index + per-yield subpairs → "+0.5 Orders / Pastures"
        for p in subpairs:
            outer = resolve_token(p.findtext("zIndex") or "", indexes)
            for sp in p.findall("SubPair"):
                sub = resolve_token(sp.findtext("zSubIndex") or "", indexes)
                v = float(sp.findtext("iValue") or 0) * scale
                out.append(f"{_fmt(v, pct)} {sub} / {outer}")
        return out

    if pairs:
        for p in pairs:
            tok = p.findtext("zIndex") or p.findtext("First") or ""
            name = resolve_token(tok, indexes)
            iv = p.findtext("iValue")
            bv = p.findtext("bValue")
            zv = p.findtext("zValue") or p.findtext("Second")
            if iv is not None:
                v = float(iv) * scale
                out.append(f"{_fmt(v, pct)} {label} / {name}" if name else f"{_fmt(v, pct)} {label}")
            elif bv is not None and bv == "1":
                out.append(f"{label}: {name}")
            elif zv:
                out.append(f"{label}: {name} → {resolve_token(zv, indexes)}")
            elif name:
                # Bare <First> list (AddCourtier: the pair names the thing granted).
                line = _fill_template(spec, name)
                out.append(line if line else f"{label}: {name}")
        return out

    zvals = [z.text for z in el.findall("zValue") if z.text]
    if zvals:
        names = ", ".join(resolve_token(z, indexes) for z in zvals)
        line = _fill_template(spec, names)
        return [line if line else f"{label}: {names}"]

    text = (el.text or "").strip()
    if text:
        if re.fullmatch(r"-?\d+", text):
            v = float(text) * scale
            if field.startswith("b"):
                if text != "1":
                    return []
                line = _fill_template(spec, "")
                return [line if line else label]
            line = _fill_template(spec, _fmt(v, pct))
            return [line if line else f"{_fmt(v, pct)} {label}"]
        return [f"{label}: {resolve_token(text, indexes)}"]

    return []


_SLOT_RE = re.compile(r"\{(\d+)(?:_([a-zA-Z]+))?\}")
_COND_RE = re.compile(r"\{true_\d+:([^:}]*):([^}]*)\}")


def _fill_template(spec: dict, value: str) -> str | None:
    """Substitute into the game's template when it's simple enough (no
    branch markup). The first numeric slot gets `value`; remaining slots
    fall back to their hint suffix ({1_road} → "Road"). Returns None when
    the template can't be applied cleanly — caller falls back to the
    generic '<value> <label>' phrasing."""
    tpl = spec.get("template")
    if not tpl or "<" in tpl:
        return None
    # Resolve {true_N:a:b} conditionals to the false branch (steady-state wording)
    tpl = _COND_RE.sub(lambda m: m.group(2), tpl)

    used_value = False

    def sub(m: "re.Match[str]") -> str:
        nonlocal used_value
        if value and not used_value:
            used_value = True
            return value
        hint = m.group(2) or ""
        if not hint:
            return "\x00"
        if hint == "turnScale":
            return "turn"
        # camel-split, drop markup-ish suffix words: harvestLink → "Harvest"
        words = _CAMEL_RE.sub(" ", hint).title().split()
        words = [w for w in words if w not in ("Link", "Icon")]
        return " ".join(words) if words else "\x00"

    out = _SLOT_RE.sub(sub, tpl)
    if "\x00" in out or "{" in out:  # bare un-hinted slot left — not safe
        return None
    out = _clean_text(out)
    # A percent value filled into a "{0_value}%" slot would print "+10%%".
    out = out.replace("%%", "%")
    return re.sub(r"\s{2,}", " ", out).strip() or None


def extra_lines(
    entry: ET.Element,
    section: str,
    exclude: frozenset | set = frozenset(),
    indexes: dict | None = None,
) -> list[str]:
    """Render every populated registry field of `entry` not in `exclude`.

    `section` is one of effectCity/effectPlayer/effectUnit/bonus. `exclude`
    is the caller's curated-coverage set (humanize renders those itself).
    """
    reg = REGISTRY.get(section)
    if not reg:
        return []
    seen_fields: set[str] = set()
    out: list[str] = []
    if section == "effectUnit":
        out.extend(_tuple_lines(entry, set(exclude) | SKIP_FIELDS.get(section, set()), indexes))
        seen_fields |= TUPLE_FIELDS
    for key in sorted(reg):
        spec = reg[key]
        field = spec.get("xmlField") or key
        if field in seen_fields or field in exclude or field in SKIP_FIELDS.get(section, set()):
            continue
        if spec.get("qualifies"):
            # Modifies another field's line (e.g. bIgnoreDelayTurns); no line of its own.
            continue
        seen_fields.add(field)
        el = entry.find(field)
        if el is None:
            continue
        populated = bool((el.text or "").strip()) or len(el) > 0
        if not populated:
            continue
        if field in _TEXT_FIELDS:
            # TEXT_* key → ready-made help line (needs the text index).
            # Skip self-referential help: some entries point ExtraHelp at
            # their own Name key (e.g. the Tamil supremacy effectCities),
            # which would render the entry's NAME as a phantom effect line.
            key = (el.text or "").strip()
            if key and key == (entry.findtext("Name") or "").strip():
                continue
            if indexes:
                nice = indexes.get("__text__", {}).get(key, "")
                if nice:
                    out.append(_clean_text(nice))
            continue
        if field in VOID_TECH_FIELDS:
            lines = _void_tech_lines(el, field, indexes)
            out.extend(lines)
            continue
        lines = _render_field(el, field, spec, indexes)
        if lines:
            out.extend(lines)
        else:
            UNRENDERED.setdefault(section, set()).add(field)
    return out
