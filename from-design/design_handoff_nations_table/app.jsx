/* global React, ReactDOM, TweaksPanel, useTweaks, TweakSection, TweakRadio, TweakToggle, TweakSelect, NATIONS */
const { useState, useEffect, useMemo, useRef } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "variant": "refined",
  "density": "micro",
  "showLeftTint": false,
  "crosshair": false,
  "showYieldIcons": false
}/*EDITMODE-END*/;

/* ─── Yield classifier — mirrors lib/entities.ts behavior ───── */
const YIELD_KEYWORDS = [
  ['orders',     ['orders/kill', 'orders/turn', '+1 order', 'order ', 'orders']],
  ['science',    ['science', 'scientist']],
  ['civics',     ['civics', 'civic']],
  ['culture',    ['culture', 'cultural']],
  ['money',      ['money', 'coin', 'gold ', 'wealth']],
  ['training',   ['training', '+xp', ' xp', 'experience']],
  ['food',       ['food']],
  ['growth',     ['growth']],
  ['wood',       ['wood', 'lumber', 'forester']],
  ['stone',      ['stone', 'quarry']],
  ['iron',       ['iron', 'mine']],
  ['happiness',  ['happiness']],
  ['discontent', ['discontent']],
  ['influence',  ['influence']],
  ['legitimacy', ['legitimacy']],
];
function classifyYield(text){
  if (!text) return null;
  const t = (' ' + String(text).toLowerCase() + ' ');
  for (const [key, words] of YIELD_KEYWORDS){
    for (const w of words){ if (t.includes(w)) return key; }
  }
  return null;
}

/* ─── Naive linkifier: highlight any nation / yield name found in text ── */
const LINK_TERMS = (() => {
  const terms = new Set();
  NATIONS.forEach(n => terms.add(n.name));
  ['Orders','Science','Civics','Culture','Money','Training','Food','Growth','Wood','Stone','Iron',
   'Happiness','Discontent','Influence','Legitimacy','Ivory','Coin','Stele','Elephants','Pastures',
   'Mines','Nets','Forests','Camps','Quarries','Camp','Forest','Quarry','Mine','Pasture','Net',
   'Wisdom','Charisma','Courage','Discipline','Family','Families','Tech','Techs','Unit','Units',
   'Citadel','Citadels','Pillage','Pillaged','Kill','Kills','Focus','Hero','Heroes','Cavalry',
   'Infantry','Archer','Archers','Worker','Workers','Specialist','Specialists','Shrine','Shrines']
   .forEach(w => terms.add(w));
  return Array.from(terms).sort((a,b)=>b.length-a.length);
})();
const LINK_REGEX = new RegExp(`(?<![A-Za-z0-9])(${LINK_TERMS.map(t=>t.replace(/[-\\^$*+?.()|[\]{}]/g,'\\$&')).join('|')})(?![A-Za-z0-9])`, 'g');

function Linkified({ text }){
  if (!text) return null;
  const parts = [];
  let i = 0, m;
  LINK_REGEX.lastIndex = 0;
  while ((m = LINK_REGEX.exec(text)) !== null){
    if (m.index > i) parts.push(text.slice(i, m.index));
    parts.push(<a key={m.index} className="lnk" href="#" onClick={e=>e.preventDefault()}>{m[0]}</a>);
    i = m.index + m[0].length;
  }
  if (i < text.length) parts.push(text.slice(i));
  return <>{parts}</>;
}

/* ─── Row spec mirrors src/pages/nations.astro ─── */
const ROWS = [
  { section: 'Bonuses' },
  { label: 'Bonus 1', kind: 'data', get: n => n.bonuses?.[0] },
  { label: 'Bonus 2', kind: 'data', get: n => n.bonuses?.[1] },
  { label: 'Bonus 3', kind: 'data', get: n => n.bonuses?.[2] },
  { section: 'Shrines' },
  { label: 'Shrine 1', kind: 'shrine', get: n => n.shrines?.[0] },
  { label: 'Shrine 2', kind: 'shrine', get: n => n.shrines?.[1] },
  { label: 'Shrine 3', kind: 'shrine', get: n => n.shrines?.[2] },
  { label: 'Shrine 4', kind: 'shrine', get: n => n.shrines?.[3] },
  { section: 'Unique Unit' },
  { label: 'Names',      kind: 'data', get: n => n.uniqueUnit?.names },
  { label: 'Traits',     kind: 'data', get: n => n.uniqueUnit?.traits },
  { label: 'Cost',       kind: 'data', get: n => n.uniqueUnit?.cost },
  { label: 'Upkeep',     kind: 'data', get: n => n.uniqueUnit?.upkeep },
  { label: 'Move/Sight', kind: 'data', get: n => n.uniqueUnit?.moveSight },
  { label: 'U6 Card',    kind: 'data', get: n => n.uniqueUnit?.u6Card },
  { label: 'U8 Card',    kind: 'data', get: n => n.uniqueUnit?.u8Card },
  { section: 'Starting Techs' },
  { label: 'Tech 1', kind: 'data', get: n => n.startingTech?.[0] },
  { label: 'Tech 2', kind: 'data', get: n => n.startingTech?.[1] },
  { label: 'Tech 3', kind: 'data', get: n => n.startingTech?.[2] },
  { section: 'Families' },
  { label: 'Family 1', kind: 'family', get: n => n.families?.[0] },
  { label: 'Family 2', kind: 'family', get: n => n.families?.[1] },
  { label: 'Family 3', kind: 'family', get: n => n.families?.[2] },
  { label: 'Family 4', kind: 'family', get: n => n.families?.[3] },
  { label: 'Family 5', kind: 'family', get: n => n.families?.[4] },
  { label: 'Family 6', kind: 'family', get: n => n.families?.[5] },
  { section: 'Royal Family' },
  { label: 'Leader', kind: 'data', get: n => n.leader?.name },
  { label: 'Spouse', kind: 'data', get: n => n.leader?.spouse },
  { label: 'Heir 1', kind: 'data', get: n => n.leader?.heir1 },
  { label: 'Heir 2', kind: 'data', get: n => n.leader?.heir2 },
];

const YIELD_GLYPH = {
  orders: '◇', science: '⚛', civics: '§', culture: '♪', money: '¤', training: '✕',
  food: '◉', growth: '↑', wood: '🌲', stone: '◼', iron: '⬢',
  happiness: '☻', discontent: '☹', influence: '✦', legitimacy: '✸',
};
const SHRINE_GLYPH = {
  LOVE: '♥', WAR: '⚔', WATER: '≋', FIRE: '🜂', KINGSHIP: '♔', SUN: '☀',
  EARTH: '◔', SKY: '☁', MOON: '☾', WISDOM: '✦',
};

/* ─── Header ─── */
function SiteHeader({ activeTab, setActiveTab, search, setSearch }){
  const tabs = ['Index','Nations','Yields','Techs','Units','Families','Laws','Shrines'];
  return (
    <header className="hdr">
      <div className="hdr__inner">
        <a className="hdr__brand" href="#" onClick={e=>{e.preventDefault(); setActiveTab('Index');}}>
          <span className="hdr__mark">⚜</span>
          <span className="hdr__title">Old World</span>
          <span className="hdr__sub">Reference</span>
        </a>
        <nav className="hdr__nav">
          {tabs.map(t => (
            <a key={t} href="#" className={'hdr__navlink ' + (activeTab===t?'is-active':'')}
               onClick={e=>{e.preventDefault(); setActiveTab(t);}}>{t}</a>
          ))}
        </nav>
        <label className="hdr__search">
          <span className="hdr__search-ico">⌕</span>
          <input
            value={search}
            onChange={e=>setSearch(e.target.value)}
            placeholder="Search nations, yields, techs…"
          />
          <kbd>⌘K</kbd>
        </label>
      </div>
    </header>
  );
}

/* ─── Cell renderers ─── */
function Cell({ row, nation, value, t, hoverCol, setHoverCol, hoverRow, setHoverRow, ri, ci }){
  const isHoverCol = hoverCol === ci;
  const isHoverRow = hoverRow === ri;
  const yKey = classifyYield(
    row.kind === 'shrine'
      ? (value?.effect || '')
      : (row.kind === 'family' ? '' : String(value || ''))
  );
  const yClass = yKey ? `yield-${yKey}` : '';
  const empty = value == null || value === '' || (row.kind==='family' && !value);

  const cls = [
    'cell',
    `n-${nation.slug}`,
    yClass,
    empty ? 'is-empty' : '',
    t.crosshair && (isHoverCol || isHoverRow) ? 'is-cross' : '',
    !t.showLeftTint ? 'no-left' : ''
  ].join(' ');

  const onEnter = () => { setHoverCol(ci); setHoverRow(ri); };

  if (empty) return <td className={cls} onMouseEnter={onEnter}><span className="cell__dash">—</span></td>;

  if (row.kind === 'shrine'){
    const sh = value;
    return (
      <td className={cls} onMouseEnter={onEnter}>
        <div className="shrine">
          <span className={`shrine__type shrine__type--${(sh.type||'').toLowerCase()}`}>
            <span className="shrine__glyph">{SHRINE_GLYPH[sh.type] || '✦'}</span>
            {sh.typeLabel}
          </span>
          <span className="shrine__name">{sh.name}</span>
        </div>
        <div className="cell__body"><Linkified text={sh.effect}/></div>
        {t.showYieldIcons && yKey && <span className="cell__yico" aria-hidden>{YIELD_GLYPH[yKey]}</span>}
      </td>
    );
  }
  if (row.kind === 'family'){
    return (
      <td className={cls} onMouseEnter={onEnter}>
        <div className="fam">
          <span className="fam__class"><Linkified text={value.class}/></span>
          <span className="fam__name">{value.name}</span>
        </div>
      </td>
    );
  }
  return (
    <td className={cls} onMouseEnter={onEnter}>
      <div className="cell__body"><Linkified text={String(value)}/></div>
      {t.showYieldIcons && yKey && <span className="cell__yico" aria-hidden>{YIELD_GLYPH[yKey]}</span>}
    </td>
  );
}

/* ─── Table ─── */
function NationsTable({ t, search }){
  const [hoverCol, setHoverCol] = useState(null);
  const [hoverRow, setHoverRow] = useState(null);
  const ordered = useMemo(() => [...NATIONS].sort((a,b)=>a.name.localeCompare(b.name)), []);

  const q = search.trim().toLowerCase();
  const matches = (n) => {
    if (!q) return true;
    if (n.name.toLowerCase().includes(q)) return true;
    const blob = JSON.stringify(n).toLowerCase();
    return blob.includes(q);
  };
  const visible = ordered.map(n => matches(n));
  const anyHidden = visible.some(v => !v);

  return (
    <div
      className={`grid grid--${t.variant} grid--${t.density}`}
      onMouseLeave={() => { setHoverCol(null); setHoverRow(null); }}
    >
      <div className="grid__scroll">
        <table className="ntbl">
          <colgroup>
            <col className="ntbl__rowlabel-col"/>
            {ordered.map((n,i) => <col key={n.slug} className={visible[i]?'':'is-hidden'}/>)}
          </colgroup>
          <thead>
            <tr>
              <th className="rowlabel rowlabel--corner">
                <span className="rowlabel__small">Nation →</span>
                <span className="rowlabel__big">Attribute ↓</span>
              </th>
              {ordered.map((n, ci) => (
                <th key={n.slug}
                    className={`nhdr n-${n.slug} ${hoverCol===ci?'is-hover':''} ${visible[ci]?'':'is-hidden'}`}
                    onMouseEnter={()=>setHoverCol(ci)}>
                  <div className="nhdr__inner">
                    <img className="nhdr__crest" src={`public/img/crests/${n.slug}.png`} alt=""
                         onError={(e)=>{e.target.style.display='none';}} />
                    <div className="nhdr__name">{n.name}</div>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row, ri) => row.section ? (
              <tr className="srow" key={'s'+ri}>
                <th className="srow__th" colSpan={ordered.length + 1}>
                  <span className="srow__chevron">▸</span>{row.section}
                </th>
              </tr>
            ) : (
              <tr key={row.label} className={hoverRow===ri && t.crosshair ? 'tr--hover' : ''}>
                <th className={`rowlabel ${hoverRow===ri?'is-hover':''}`}
                    onMouseEnter={()=>setHoverRow(ri)}>
                  {row.label}
                </th>
                {ordered.map((n, ci) => (
                  <Cell key={n.slug+ri} row={row} nation={n} value={row.get(n)}
                        t={t} ri={ri} ci={ci}
                        hoverCol={hoverCol} hoverRow={hoverRow}
                        setHoverCol={setHoverCol} setHoverRow={setHoverRow}/>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {anyHidden && (
        <div className="grid__searchnote">
          Showing {visible.filter(Boolean).length} of {ordered.length} nations matching "{search}"
        </div>
      )}
    </div>
  );
}

/* ─── Legends ─── */
function Legends(){
  const yields = ['orders','science','civics','culture','money','training','food','growth','wood','stone','iron'];
  return (
    <div className="legends">
      <div className="legend">
        <span className="legend__label">Yields</span>
        {yields.map(y => (
          <span key={y} className={`chip yield-${y}`}>
            <span className="chip__glyph">{YIELD_GLYPH[y]}</span>
            {y[0].toUpperCase()+y.slice(1)}
          </span>
        ))}
      </div>
      <div className="legend">
        <span className="legend__label">Cell color = what a bonus <em>gives</em>. Left edge = nation tint.</span>
      </div>
    </div>
  );
}

/* ─── App ─── */
function App(){
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [activeTab, setActiveTab] = useState('Nations');
  const [search, setSearch] = useState('');

  // Keyboard shortcut for search
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k'){
        e.preventDefault();
        document.querySelector('.hdr__search input')?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className={`app app--${t.variant} app--${t.density}`}>
      <SiteHeader activeTab={activeTab} setActiveTab={setActiveTab} search={search} setSearch={setSearch}/>
      <main className="main">
        <div className="page-meta">
          <div>
            <h1 className="page-title"><span className="page-title__mark">👑</span>Nations</h1>
          </div>
          <div className="page-stats">
            <span className="stat"><b>13</b> nations</span>
            <span className="stat"><b>{NATIONS.reduce((a,n)=>a+(n.families?.length||0),0)}</b> families</span>
            <span className="stat"><b>{NATIONS.reduce((a,n)=>a+(n.shrines?.length||0),0)}</b> shrines</span>
          </div>
        </div>
        <NationsTable t={t} search={search}/>
        <Legends/>
        <footer className="foot">
          <div className="foot__col">
            <span className="foot__label">Patch</span>
            <span className="foot__val">1.0.79431</span>
            <span className="foot__dot">·</span>
            <span className="foot__val foot__val--dim">released May 02, 2026</span>
            <span className="foot__dot">·</span>
            <span className="foot__val foot__val--dim">data auto-synced from game files</span>
          </div>
          <div className="foot__col foot__col--right">
            <a href="#" onClick={e=>e.preventDefault()}>Changelog</a>
            <span className="foot__dot">·</span>
            <a href="#" onClick={e=>e.preventDefault()}>Source</a>
            <span className="foot__dot">·</span>
            <a href="https://mohawkgames.com/oldworld/" target="_blank" rel="noopener">Old World</a>
          </div>
        </footer>
      </main>

      <TweaksPanel title="Tweaks">
        <TweakSection title="Direction">
          <TweakRadio
            value={t.variant}
            onChange={v => setTweak('variant', v)}
            options={[
              { value: 'refined',     label: 'Refined' },
              { value: 'columnar',    label: 'Columnar' },
              { value: 'engraved',    label: 'Engraved' },
            ]}
          />
          <p className="tw-help">
            <b>Refined</b> — polished evolution of current.<br/>
            <b>Columnar</b> — strong nation columns, lighter yield fills.<br/>
            <b>Engraved</b> — atmospheric, embossed shrine cards.
          </p>
        </TweakSection>
        <TweakSection title="Density">
          <TweakRadio value={t.density} onChange={v=>setTweak('density', v)}
            options={[{value:'comfy',label:'Comfy'},{value:'tight',label:'Tight'},{value:'micro',label:'Micro'}]}/>
        </TweakSection>
        <TweakSection title="Reading aids">
          <TweakToggle label="Crosshair on hover" value={t.crosshair} onChange={v=>setTweak('crosshair', v)}/>
          <TweakToggle label="Nation tint on left edge" value={t.showLeftTint} onChange={v=>setTweak('showLeftTint', v)}/>
          <TweakToggle label="Yield glyph in corner" value={t.showYieldIcons} onChange={v=>setTweak('showYieldIcons', v)}/>
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
