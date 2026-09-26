// Lines that change the whole nation — an occurrence starting or ending (Era of
// Peace, Civil War, a calamity), war or peace, a throne changing hands, a state
// religion or law — carry `kind` from scripts/event_bonus.py. Event cards badge
// them and the filter can narrow to them.

export const isNationwide = (r: any): boolean =>
  !!r && (r.kind === 'occurrence' || r.kind === 'nationwide');

export interface NationSummary {
  onOpen: any[];      // fire as the event opens, before any choice (the event's own aeBonuses)
  inOptions: any[];   // fire only if a particular choice is made
}

export function nationSummary(ev: any): NationSummary {
  const onOpen = (ev.guaranteed || []).filter(isNationwide);
  const seen = new Set(onOpen.map((r: any) => r.text));
  const inOptions: any[] = [];
  for (const o of ev.options || [])
    for (const oc of o.outcomes || [])
      for (const r of oc.rewards || [])
        if (isNationwide(r) && !seen.has(r.text)) { seen.add(r.text); inOptions.push(r); }
  return { onOpen, inOptions };
}
