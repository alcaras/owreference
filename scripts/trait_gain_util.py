"""Shared definition of "trait acquisition" — every way a character can GAIN a
trait, indexed by the trait gained. The mirror of trait_removal_util.

Five routes live in the bonus payload, and they are worth keeping apart because
they differ in how much control you have:

  direct    aeAddTraits — the option grants it outright. Pick the option, get
            the trait.
  chance    aiTraitProbDelay — an N% roll, resolved on a later turn
            (Character.doTraitProbDelay), not when you click.
  random    aeRandomTrait / aeRandomTraitDelay — one trait drawn from a pool.
            Character.doRandomTrait (Character.cs:7117) rolls 1..1000 for every
            pool member that passes canAddTrait and keeps the highest, so the
            draw is uniform over the *currently valid* members — the odds are
            1/valid, NOT 1/poolSize, and shrink as the character collects the
            pool.
  religion  aeAddTraitReligion — grants a trait keyed to the character's religion.
  auto      the same fields reached from the STORY's own aeBonuses rather than
            an option: the event grants it with no choice involved.

All five must also look one level down through `aiEventOptionProb`, exactly as
removal does: several options present one button that internally expands into
per-trait variants, and the grant lives in the variant. Bonuses also nest via
`aeBonuses`, so the walk recurses (with a seen-set — the data has cycles).

Eligibility, and why a listed event may still not offer you the trait:
PlayerBonus.canDoBonusSingle (PlayerBonus.cs:2862) rejects an add-trait bonus
unless Game.canAddTrait passes (Game.cs:10506), which checks — in order —
GameContentRequired, canAddTraitNoFallback, the trait's own aeTraitInvalid
against what the character already has, general/explorer EffectUnit validity,
bRemoveDeath vs. a dead character, iMinAge, and bNoSpouse. So a trait with a
high min age or a long aeTraitInvalid list is much harder to land than its
event count suggests, which is why the pages surface those preconditions
alongside the count.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict


def _zv(e: ET.Element, tag: str) -> list[str]:
    return [x.text for x in e.findall(f"{tag}/zValue") if x.text]


def _zv_indexed(e: ET.Element, tag: str) -> list[str]:
    """Like _zv but KEEPS empty slots — position is the subject index, so an
    empty <zValue/> is a real gap that must not shift later entries."""
    return [(x.text or "") for x in e.findall(f"{tag}/zValue")]


def grants_of_bonus(bonus_id: str, bonus_idx: dict,
                    _seen: set | None = None) -> dict[str, list]:
    """{route: [payload]} for one bonus, following nested aeBonuses.

    payloads: direct/auto → trait id; chance → (trait id, percent);
    random → (trait id, full pool); religion → (trait id, religion id).
    """
    out: dict[str, list] = defaultdict(list)
    seen = _seen if _seen is not None else set()
    if bonus_id in seen:
        return out
    seen.add(bonus_id)
    b = bonus_idx.get(bonus_id)
    if b is None:
        return out

    for t in _zv(b, "aeAddTraits"):
        out["direct"].append(t)
    for p in b.findall("aiTraitProbDelay/Pair"):
        t, v = p.findtext("zIndex"), p.findtext("iValue")
        if t and v and int(v) > 0:
            out["chance"].append((t, int(v)))
    for tag in ("aeRandomTrait", "aeRandomTraitDelay"):
        pool = _zv(b, tag)
        for t in pool:
            out["random"].append((t, pool))
    for p in b.findall("aeAddTraitReligion/Pair"):
        rel, t = p.findtext("zIndex"), p.findtext("zValue")
        if t:
            out["religion"].append((t, rel))

    for ref in _zv(b, "aeBonuses"):
        for route, rows in grants_of_bonus(ref, bonus_idx, seen).items():
            out[route] += rows
    return out


def option_bonuses(opt: ET.Element, eopt_idx: dict):
    """Yield (subject index, bonus id, is_variant) for an option and its
    aiEventOptionProb sub-options (one level — the game does not nest deeper).

    The index is load-bearing, not bookkeeping: aeBonuses is POSITIONAL against
    the story's subject list — PlayerEvent.isValidEventOptionSubject reads
    `maeBonuses[iSubjectIndex]` (PlayerEvent.cs:6710), and the story-level form
    does the same at PlayerEvent.cs:11987. So slot 2 of the list grants to
    subject 2, which may well be the RIVAL's leader rather than yours.
    Reporting "this option grants Gracious" without saying who receives it is
    wrong often enough to matter: EVENTOPTION_CALAMITIES_DROUGHT_FEAST_OR_FAMINE_GIFT
    grants Gracious to SUBJECT_LEADER_THEM and Compassionate to SUBJECT_LEADER_US
    from the very same click.

    A bonus's own nested aeBonuses stay with the same subject — PlayerBonus
    threads the identical pCharacter through (PlayerBonus.cs:4813) — so the
    index attaches at the top level only.
    """
    for i, ref in enumerate(_zv_indexed(opt, "aeBonuses")):
        if ref:
            yield i, ref, None
    pairs = [(p.findtext("zIndex") or "", int(p.findtext("iValue") or "0"))
             for p in opt.findall("aiEventOptionProb/Pair")]
    total = sum(w for _, w in pairs if w > 0)
    for sub_id, w in pairs:
        if w <= 0:
            continue
        sub = eopt_idx.get(sub_id)
        if sub is None:
            continue
        for i, ref in enumerate(_zv_indexed(sub, "aeBonuses")):
            if ref:
                # Exactly ONE variant fires, so the caller must report the odds
                # rather than listing every variant's payload as if it all
                # happened. weight/total is the draw chance for this branch.
                yield i, ref, {"weight": w, "total": total, "sub": sub_id}


def preconditions(trait: ET.Element, trait_name) -> dict:
    """The canAddTrait gates that are visible in trait.xml, as display data.

    Everything here is a hard NO for gaining the trait, so it belongs next to
    the list of events that would otherwise look available.
    """
    out: dict = {}
    if (age := trait.findtext("iMinAge")):
        if int(age):
            out["minAge"] = int(age)
    blocked = [trait_name(t) for t in _zv(trait, "aeTraitInvalid")]
    if blocked:
        out["blockedBy"] = blocked
    if trait.findtext("bNoSpouse") == "1":
        out["noSpouse"] = True
    if trait.findtext("bRemoveDeath") == "1":
        out["livingOnly"] = True
    if (dlc := trait.findtext("GameContentRequired")):
        out["dlc"] = dlc
    return out
