"""Shared definition of "trait removal" events — every story that can take a
trait OFF a character, indexed by the trait it removes.

A trait can leave a character two ways, and both count here:

  direct    an option's bonus lists the trait in aeRemoveTraits
  replaced  an option's bonus ADDS a trait whose aeTraitReplaces names it —
            e.g. gaining Inspiring clears Bitter, gaining Blessed clears Cursed

Both paths must also look one level down through `aiEventOptionProb`. Several
options present a single choice in the UI that internally expands into
per-trait variants (Pushed Too Far → removes Bitter / Cruel / Intolerant; The
Pále → Bitter / Miserable / Mourning). Those variants are where the removal
actually lives, so an option-only walk misses them entirely.

Selection among those variants is NOT the random gamble the weights suggest:
PlayerBonus.canDoBonusSingle (PlayerBonus.cs:2912) rejects a removal bonus
unless `pCharacter.isTrait(...)`, so only variants matching a trait the
character actually has are eligible — the weight only breaks ties when a
character has several.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET


def replacement_map(trait_files: list[ET.Element]) -> dict[str, list[str]]:
    """trait id → the traits it displaces via aeTraitReplaces."""
    out: dict[str, list[str]] = {}
    for root in trait_files:
        for e in root.findall("Entry"):
            z = e.findtext("zType")
            if not z:
                continue
            rep = [x.text for x in e.findall("aeTraitReplaces/zValue") if x.text]
            if rep:
                out[z] = rep
    return out


def _walk_options(story: ET.Element, eopt_idx: dict):
    """Yield (option, is_variant) for a story's options AND their
    aiEventOptionProb sub-options (one level — the game does not nest deeper)."""
    for ref in story.findall("aeOptions/zValue"):
        opt = eopt_idx.get(ref.text or "")
        if opt is None:
            continue
        yield opt, False
        for pair in opt.findall("aiEventOptionProb/Pair"):
            if int(pair.findtext("iValue") or "0") <= 0:
                continue
            sub = eopt_idx.get(pair.findtext("zIndex") or "")
            if sub is not None:
                yield sub, True


def removals(story: ET.Element, eopt_idx: dict, bonus_idx: dict,
             replaces: dict[str, list[str]]) -> dict[str, dict]:
    """{removed trait id: {"direct": bool, "via": [granting trait ids],
                            "variant": bool}} for one story."""
    found: dict[str, dict] = {}

    def note(trait: str, *, direct: bool, via: str | None, variant: bool):
        row = found.setdefault(trait, {"direct": False, "via": [], "variant": False})
        if direct:
            row["direct"] = True
        if via and via not in row["via"]:
            row["via"].append(via)
        if variant:
            row["variant"] = True

    for opt, is_variant in _walk_options(story, eopt_idx):
        for ref in opt.findall("aeBonuses/zValue"):
            b = bonus_idx.get(ref.text or "")
            if b is None:
                continue
            for t in b.findall("aeRemoveTraits/zValue"):
                if t.text:
                    note(t.text, direct=True, via=None, variant=is_variant)
            for t in b.findall("aeAddTraits/zValue"):
                for displaced in replaces.get(t.text or "", []):
                    note(displaced, direct=False, via=t.text, variant=is_variant)
    return found
