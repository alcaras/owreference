import json
import os

def parse_events(event_list, source_label, obs_registry):
    for ev in event_list:
        eid = ev.get('id')
        if not eid:
            continue
        name = ev.get('title') or ev.get('name') or eid
        
        card = {
            'id': eid,
            'name': name,
            'type': 'Event',
            'slug': eid.lower(),
            'icon': 'img/icons/effects/event.png',
            'stats': {},
            'effects': [],
            'cost': []
        }
        
        # Add Trigger / Source
        trigger = ev.get('trigger')
        if trigger:
            card['effects'].append(f"Trigger: {trigger}")
        elif source_label:
            card['effects'].append(f"Category: {source_label}")
            
        # Add Conditions
        conds = ev.get('conditions', [])
        if conds:
            card['effects'].append(f"Conditions: {', '.join(conds)}")
            
        # Add Guaranteed Outcomes
        guar = ev.get('guaranteed', [])
        if guar:
            guar_texts = [g['text'] for g in guar if g.get('text')]
            if guar_texts:
                card['effects'].append(f"Guaranteed: {', '.join(guar_texts)}")
                
        # Add Options
        for idx, opt in enumerate(ev.get('options', [])):
            opt_text = opt.get('text', '')
            if opt_text:
                card['effects'].append(f"Option {idx + 1}: \"{opt_text}\"")
            
            # Add rewards
            rewards = []
            for out in opt.get('outcomes', []):
                if isinstance(out, str):
                    rewards.append(out)
                elif isinstance(out, dict):
                    for rew in out.get('rewards', []):
                        if isinstance(rew, dict) and rew.get('text'):
                            rewards.append(rew['text'])
                        elif isinstance(rew, str):
                            rewards.append(rew)
            if rewards:
                card['effects'].append(f" ↳ {', '.join(rewards)}")
                
        obs_registry[eid] = card

def main():
    # Load entities
    with open('src/data/entities.json', 'r', encoding='utf-8') as f:
        entities_data = json.load(f)
        
    # Load all raw catalogs
    traits_list = json.load(open('src/data/traits.json', 'r', encoding='utf-8'))
    units_list = json.load(open('src/data/units.json', 'r', encoding='utf-8'))
    techs_list = json.load(open('src/data/technologies.json', 'r', encoding='utf-8'))
    wonders_list = json.load(open('src/data/wonders.json', 'r', encoding='utf-8'))
    shrines_list = json.load(open('src/data/shrines.json', 'r', encoding='utf-8'))
    specialists_list = json.load(open('src/data/specialists.json', 'r', encoding='utf-8'))
    nations_list = json.load(open('src/data/nations.json', 'r', encoding='utf-8'))
    families_list = json.load(open('src/data/families.json', 'r', encoding='utf-8'))
    archetypes_list = json.load(open('src/data/archetypes.json', 'r', encoding='utf-8'))
    resources_list = json.load(open('src/data/resources.json', 'r', encoding='utf-8'))
    concepts_list = json.load(open('src/data/concepts.json', 'r', encoding='utf-8'))
    opinion_list = json.load(open('src/data/opinion.json', 'r', encoding='utf-8'))
    promotions_list = json.load(open('src/data/promotions.json', 'r', encoding='utf-8'))
    projects_list = json.load(open('src/data/projects.json', 'r', encoding='utf-8'))
    terrain_list = json.load(open('src/data/terrain.json', 'r', encoding='utf-8'))
    theologies_list = json.load(open('src/data/theologies.json', 'r', encoding='utf-8'))
    tribes_list = json.load(open('src/data/tribes.json', 'r', encoding='utf-8'))
    
    # We also have laws in src/data/laws.json which has groups -> classes -> laws
    laws_data = json.load(open('src/data/laws.json', 'r', encoding='utf-8'))
    laws_list = []
    for g in laws_data.get('groups', []):
        for c in g.get('classes', []):
            for l in c.get('laws', []):
                laws_list.append(l)

    # Flatten and index traits by category
    flat_traits = []
    for category, trait_list in traits_list.items():
        for t in trait_list:
            t['category'] = category
            flat_traits.append(t)
            
    # Index catalogs by id
    def make_index(lst):
        return {item['id']: item for item in lst if 'id' in item}
        
    indices = {
        'trait': make_index(flat_traits),
        'unit': make_index(units_list),
        'tech': make_index(techs_list),
        'wonder': make_index(wonders_list),
        'shrine': make_index(shrines_list),
        'specialist': make_index(specialists_list),
        'nation': make_index(nations_list),
        'family': make_index(families_list),
        'archetype': make_index(archetypes_list),
        'resource': make_index(resources_list),
        'concept': make_index(concepts_list),
        'opinion': make_index(opinion_list),
        'promotion': make_index(promotions_list),
        'project': make_index(projects_list),
        'terrain': make_index(terrain_list),
        'theology': make_index(theologies_list),
        'tribe': make_index(tribes_list),
        'law': make_index(laws_list)
    }
    
    obs_registry = {}
    
    for entity in entities_data.get('entities', []):
        eid = entity['id']
        etype = entity['type']
        name = entity['name']
        slug = entity['slug']
        
        card = {
            'id': eid,
            'name': name,
            'type': etype,
            'slug': slug,
            'icon': '',
            'stats': {},
            'effects': [],
            'cost': []
        }
        
        catalog = indices.get(etype, {})
        details = catalog.get(eid, {})
        
        # 1. Resolve Icon
        if etype == 'unit':
            icon_slug = details.get('iconSlug', slug)
            card['icon'] = f"img/icons/units/{icon_slug}.png"
        elif etype == 'tech':
            card['icon'] = f"img/icons/techs/{slug}.png"
        elif etype == 'trait':
            card['icon'] = f"img/icons/traits/{slug}.png"
        elif etype == 'archetype':
            card['icon'] = f"img/archetypes/{slug}.png"
        elif etype == 'shrine':
            card['icon'] = f"img/icons/shrines/{slug}.png"
        elif etype == 'specialist':
            card['icon'] = f"img/icons/specialists/{slug}.png"
        elif etype == 'wonder':
            card['icon'] = f"img/icons/improvements/{slug}.png"
        elif etype == 'resource':
            card['icon'] = f"img/icons/resources/{slug}.png"
        elif etype == 'yield':
            card['icon'] = f"img/icons/yields/{slug}.png"
        elif etype == 'family':
            card['icon'] = f"img/families/{slug}.png"
        elif etype == 'tribe':
            card['icon'] = f"img/tribes/{slug}.png"
        elif etype == 'nation':
            card['icon'] = f"img/crests/{slug}.png"
        elif etype == 'promotion':
            card['icon'] = f"img/icons/unit_traits/{slug}.png"
        elif etype == 'project':
            card['icon'] = f"img/icons/projects/{slug}.png"
        elif etype == 'theology':
            card['icon'] = f"img/icons/religions/{slug}.png"
        elif etype == 'terrain':
            card['icon'] = f"img/icons/improvements/{slug}.png"
            
        # Ensure icon exists
        if card['icon'] and not os.path.exists(os.path.join('public', card['icon'])):
            card['icon'] = "img/icons/effects/event.png"
            
        # 2. Resolve Stats & Effects
        if etype == 'unit':
            card['stats'] = {
                'Strength': details.get('strength', 0),
                'Movement': details.get('movement', 0),
                'Range': details.get('range', 0),
                'HP': details.get('hp', 0)
            }
            card['stats'] = {k: v for k, v in card['stats'].items() if v}
            
            costs = details.get('costs', [])
            for c in costs:
                card['cost'].append(f"{c['value']} {c['yield'].capitalize()}")
                
            for effect in details.get('abilities', []):
                if isinstance(effect, dict):
                    lbl = effect.get('label', '')
                    lines = effect.get('lines', [])
                    if lbl and lines:
                        card['effects'].append(f"{lbl}: {', '.join(lines)}")
                    elif lbl:
                        card['effects'].append(lbl)
                    elif lines:
                        card['effects'].extend(lines)
                elif isinstance(effect, str):
                    card['effects'].append(effect)
                
        elif etype == 'tech':
            card['cost'].append(f"{details.get('cost', 100)} Science")
            unlocks = details.get('unlocks', [])
            for u in unlocks:
                card['effects'].append(f"Unlocks: {u}")
                
        elif etype == 'trait' or etype == 'archetype':
            ratings = details.get('ratings', [])
            for r in ratings:
                rating_key = r.get('rating') or r.get('label')
                if rating_key:
                    card['stats'][rating_key.capitalize()] = f"{r['value']:+d}"
            for field in ['leaderEffects', 'governorEffects', 'generalEffects', 'modifiers']:
                for eff in details.get(field, []):
                    card['effects'].append(f"({field[:-7].capitalize()}) {eff}")
                    
        elif etype == 'wonder':
            for c in details.get('cost', []):
                card['cost'].append(f"{c['value']} {c['yield'].capitalize()}")
            card['effects'].extend(details.get('effects', []))
            
        elif etype == 'shrine':
            card['effects'].extend(details.get('effects', []))
            
        elif etype == 'specialist':
            for c in details.get('cost', []):
                card['cost'].append(f"{c['value']} {c['yield'].capitalize()}")
            card['effects'].extend(details.get('effects', []))
            
        elif etype == 'law':
            card['cost'].append(f"{details.get('switchCost', 200)} Civics")
            card['effects'].extend(details.get('effects', []))
            
        elif etype == 'nation':
            card['effects'].extend(details.get('effects', []))
            
        elif etype == 'family':
            # Seat Bonus
            seat_bonus = details.get('seatBonus', [])
            if seat_bonus:
                card['effects'].append(f"Seat Bonus: {', '.join(seat_bonus)}")
            # City Bonus
            city_bonus = details.get('cityBonus', [])
            if city_bonus:
                for cb in city_bonus:
                    card['effects'].append(f"City Bonus: {cb}")
            # Granted Traits
            for gt in details.get('grantedTraits', []):
                card['effects'].append(f"Granted Trait: {gt['name']} ({', '.join(gt.get('effects', []))})")
            # Preferred Laws
            pref_laws = details.get('preferredLaws', [])
            if pref_laws:
                pl_strings = []
                for pl in pref_laws:
                    val_str = f"+{pl['value']}" if pl['value'] >= 0 else str(pl['value'])
                    pl_strings.append(f"{pl['label']} ({val_str})")
                card['effects'].append(f"Preferred Laws: {', '.join(pl_strings)}")
            # Opinions
            opinions = details.get('opinions', [])
            if opinions:
                op_strings = []
                for op in opinions:
                    val_str = f"+{op['value']}" if op['value'] >= 0 else str(op['value'])
                    op_strings.append(f"{op['label']} ({val_str})")
                card['effects'].append(f"Opinions: {', '.join(op_strings)}")
            
        if not card['effects'] and details.get('description'):
            card['effects'].append(details['description'])
            
        obs_registry[eid] = card
        
    # 3. Load and parse all event databases
    try:
        events_data = json.load(open('src/data/events.json', 'r', encoding='utf-8'))
        for category in events_data:
            cat_label = category.get('label', 'Events')
            parse_events(category.get('events', []), cat_label, obs_registry)
    except Exception as e:
        print("Error reading events.json:", e)

    try:
        harvest_data = json.load(open('src/data/harvest_events.json', 'r', encoding='utf-8'))
        parse_events(harvest_data, 'Harvest Events', obs_registry)
    except Exception as e:
        print("Error reading harvest_events.json:", e)

    try:
        study_data = json.load(open('src/data/study_events.json', 'r', encoding='utf-8'))
        parse_events(study_data, 'Study Events', obs_registry)
    except Exception as e:
        print("Error reading study_events.json:", e)

    parts_dir = 'src/data/story-events/parts'
    if os.path.exists(parts_dir):
        for fname in os.listdir(parts_dir):
            if fname.endswith('.json'):
                fpath = os.path.join(parts_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    cat_label = data.get('category', {}).get('label') or fname[:-5].replace('-', ' ').title()
                    parse_events(data.get('events', []), cat_label, obs_registry)
                except Exception as e:
                    print(f"Error parsing story event part {fname}: {e}")

    os.makedirs('public/data', exist_ok=True)
    with open('public/data/obs-data.json', 'w', encoding='utf-8') as f:
        json.dump(obs_registry, f, indent=2, sort_keys=True)
        
    print(f"Successfully generated public/data/obs-data.json with {len(obs_registry)} display cards!")

if __name__ == '__main__':
    main()
