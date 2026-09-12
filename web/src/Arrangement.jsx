import React from 'react';
const labels={A:'A',B:'B',none:'Keiner',hybrid:'A + B'};
export function Arrangement({sections,setSections,onPlan,onIntro,busy,bpm,setBpm,keyMatch,setKeyMatch}){
 const change=(i,key,value)=>setSections(sections.map((s,n)=>n===i?{...s,[key]:value}:s));
 let bar=1;
 return <section className="arrangement panel">
  <div className="section-heading"><h2>Dein Arrangement</h2><div className="plan-controls"><button disabled={busy} onClick={onPlan}>✧ &nbsp; Zusammenhängend planen</button><label>Zieltempo <input aria-label="Zieltempo" type="number" min="60" max="200" placeholder="Auto" value={bpm} onChange={e=>setBpm(e.target.value)}/></label><label className="toggle-label">Tonart anpassen <input className="toggle" type="checkbox" checked={keyMatch} onChange={e=>setKeyMatch(e.target.checked)}/></label></div></div>
  {!sections.length?<div className="empty-plan">Wähle zwei Songs und lass dir einen Abschnittsplan vorschlagen.</div>:<>
   <div className="timeline" aria-label="Arrangement in Takten">{sections.map((s,i)=>{const start=bar;bar+=s.bars;return <div key={i} className={'timeline-section color-'+(s.effect==='drop'?'drop':s.vocal)} style={{flex:s.bars}}><strong>{s.name}</strong><span>{s.bars} Takte</span><small>{start}</small></div>})}<small className="end-bar">{bar}</small></div>
   <div className="table-scroll"><table><thead><tr><th>Abschnitt</th><th>Takte</th><th>Gesang</th><th>Instrumental</th><th>Start A · Sek.</th><th>Start B · Sek.</th><th><span className="sr-only">Entfernen</span></th></tr></thead><tbody>{sections.map((s,i)=><tr key={i}>
    <td><span className={'dot dot-'+(s.effect==='drop'?'drop':s.vocal)}/><input aria-label={`Name Abschnitt ${i+1}`} className="name-input" value={s.name} maxLength="60" onChange={e=>change(i,'name',e.target.value)}/></td>
    <td><input aria-label={`Takte Abschnitt ${i+1}`} type="number" min="1" max="32" value={s.bars} onChange={e=>change(i,'bars',Number(e.target.value))}/></td>
    <td><select aria-label={`Gesang Abschnitt ${i+1}`} value={s.vocal} onChange={e=>change(i,'vocal',e.target.value)}>{['none','A','B'].map(x=><option key={x} value={x}>{labels[x]}</option>)}</select></td>
    <td><select aria-label={`Instrumental Abschnitt ${i+1}`} value={s.instrumental} onChange={e=>change(i,'instrumental',e.target.value)}>{['A','B','hybrid'].map(x=><option key={x} value={x}>{labels[x]}</option>)}</select></td>
    {['a','b'].map(x=><td key={x}><input aria-label={`Start ${x.toUpperCase()} Abschnitt ${i+1}`} type="number" min="0" step="0.1" value={s['start_'+x]} onChange={e=>change(i,'start_'+x,Number(e.target.value))}/></td>)}
    <td><button className="remove" aria-label={`Abschnitt ${i+1} entfernen`} disabled={sections.length===1} onClick={()=>setSections(sections.filter((_,n)=>n!==i))}>×</button></td>
   </tr>)}</tbody></table></div>
   <div className="arrangement-foot"><p>Baue ein Intro aus dem Motiv der folgenden Begleitung. Bass und Drums kommen schrittweise dazu.</p><button className="subtle" disabled={busy} onClick={onIntro}>Intro neu aufbauen</button><button className="subtle" disabled={sections.length>=16} onClick={()=>setSections([...sections,{...sections.at(-1),name:'Neuer Teil',effect:'normal',bars:8}])}>+ Abschnitt</button></div>
   <details className="fine"><summary>Feinabstimmung pro Abschnitt</summary><p>A + B kombiniert Drums aus B mit Bass und übrigen Instrumenten aus A. Nach der musikalischen Analyse rasten Einstiege auf erkannte Taktanfänge ein; manuelle BPM überschreiben dieses Raster.</p>{sections.map((s,i)=><div className="fine-row" key={i}><strong>{s.name}</strong><label>Gesang · dB<input aria-label={`Gesangspegel Abschnitt ${i+1}`} type="number" min="-18" max="12" value={s.vocal_db} onChange={e=>change(i,'vocal_db',Number(e.target.value))}/></label><label>Musik · dB<input type="number" min="-18" max="12" value={s.instrumental_db} onChange={e=>change(i,'instrumental_db',Number(e.target.value))}/></label><label>Gesang · Versatz in Beats<input type="number" min="-8" max="8" step="0.25" value={s.vocal_offset} onChange={e=>change(i,'vocal_offset',Number(e.target.value))}/></label><label>Verlauf<select value={s.effect} onChange={e=>change(i,'effect',e.target.value)}>{['normal','intro','build','drop','outro'].map(x=><option key={x}>{x}</option>)}</select></label></div>)}</details>
  </>}
 </section>
}
