import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api,setToken} from './api';
import {TrackPanel} from './TrackPanel';
import {Arrangement} from './Arrangement';
import {ResultPanel} from './ResultPanel';
import './style.css';

function App(){
 const[tracks,setTracks]=useState([]),[a,setA]=useState(''),[b,setB]=useState('');
 const[sections,setSections]=useState([]),[bpm,setBpm]=useState(''),[keyMatch,setKeyMatch]=useState(true);
 const[bpmA,setBpmA]=useState(''),[bpmB,setBpmB]=useState(''),[pitchB,setPitchB]=useState('');
 const[job,setJob]=useState(null),[result,setResult]=useState(null),[history,setHistory]=useState([]);
 const[error,setError]=useState(''),[loading,setLoading]=useState(true),[importSide,setImportSide]=useState(null),[dataDir,setDataDir]=useState('');
 const[requesting,setRequesting]=useState(false);
 const[quality,setQuality]=useState(null);
 const[separationQuality,setSeparationQuality]=useState('auto'),[hqInstalled,setHqInstalled]=useState(false);
 const busy=requesting||['running','queued'].includes(job?.status);
 const trackA=tracks.find(x=>x.id===a),trackB=tracks.find(x=>x.id===b);
 async function refresh(){const state=await api('/state');setToken(state.token);setTracks(state.tracks);setHistory(state.exports);setDataDir(state.data_dir);setHqInstalled(state.hq_installed);return state;}
 async function plan(x=a,y=b){if(!x||!y)return;try{const data=await api('/plan',{track_a:x,track_b:y});setSections(data.sections);}catch(e){setError(e.message)}}
 useEffect(()=>{(async()=>{try{const state=await refresh();let saved=null;try{saved=JSON.parse(localStorage.getItem('mashup-session'));}catch{}
  const first=state.tracks.find(t=>t.id===state.defaults?.track_a)||state.tracks[0],second=state.tracks.find(t=>t.id===state.defaults?.track_b)||state.tracks.find(t=>t.id!==first?.id)||first;
  const valid=saved&&state.tracks.some(t=>t.id===saved.a)&&state.tracks.some(t=>t.id===saved.b);
  const x=valid?saved.a:first?.id||'',y=valid?saved.b:second?.id||'';setA(x);setB(y);
  if(valid){setSections(saved.sections||[]);setBpm(saved.bpm??'');setKeyMatch(saved.keyMatch??true);setBpmA(saved.bpmA??'');setBpmB(saved.bpmB??'');setPitchB(saved.pitchB??'');setQuality(saved.quality??null);setSeparationQuality(saved.separationQuality??'auto');}else await plan(x,y);
  setResult(state.exports[0]||null);setJob(state.jobs.find(j=>['queued','running'].includes(j.status))||null);
 }catch(e){setError('Verbindung zum lokalen Audiowerkzeug fehlgeschlagen: '+e.message)}finally{setLoading(false)}})();},[]);
 useEffect(()=>{if(!loading)localStorage.setItem('mashup-session',JSON.stringify({a,b,sections,bpm,keyMatch,bpmA,bpmB,pitchB,quality,separationQuality}));},[a,b,sections,bpm,keyMatch,bpmA,bpmB,pitchB,quality,separationQuality,loading]);
 useEffect(()=>{if(!['running','queued'].includes(job?.status))return;let stopped=false;const id=setInterval(async()=>{try{const next=await api('/jobs/'+job.id);if(stopped)return;setJob(next);if(next.status==='done'){await refresh();if(next.kind==='render')setResult(next.result);else if(next.kind==='plan'){setSections(next.result.sections);setPitchB(next.result.pitch_b);setKeyMatch(true);setBpmA('');setBpmB('');setQuality(next.result);if(bpm==='')setBpm(next.result.target_bpm);}else if(next.kind==='separation'){setQuality(null);setSeparationQuality('auto');}else if(importSide){const x=importSide==='A'?next.result.id:a,y=importSide==='B'?next.result.id:b;setA(x);setB(y);await plan(x,y);setImportSide(null);}}}catch(e){if(!stopped)setError(e.message)}},1500);return()=>{stopped=true;clearInterval(id)};},[job?.id,job?.status,importSide,a,b]);
 async function qualityPlan(){setRequesting(true);setError('');try{setJob(await api('/quality-plan',{track_a:a,track_b:b}));}catch(e){setError(e.message)}finally{setRequesting(false)}}
 async function separateHQ(){setRequesting(true);setError('');try{setJob(await api('/separate-hq',{track_a:a,track_b:b}));}catch(e){setError(e.message)}finally{setRequesting(false)}}
 async function upload(file,side){setRequesting(true);setError('');setQuality(null);try{const form=new FormData();form.append('file',file);setImportSide(side);setJob(await api('/upload',form));}catch(e){setError(e.message)}finally{setRequesting(false)}}
 async function render(preview){setRequesting(true);setError('');try{setJob(await api('/render',{track_a:a,track_b:b,sections,preview,separation_quality:separationQuality,target_bpm:bpm===''?null:Number(bpm),key_match:keyMatch,bpm_a:bpmA===''?null:Number(bpmA),bpm_b:bpmB===''?null:Number(bpmB),pitch_b:pitchB===''?null:Number(pitchB)}));}catch(e){setError(e.message)}finally{setRequesting(false)}}
 const choose=(side,id)=>{setQuality(null);if(side==='A'){setA(id);setBpmA('');}else{setB(id);setBpmB('');}setPitchB('');plan(side==='A'?id:a,side==='B'?id:b)};
 return <><header><a className="brand" href="/">Buckswood <span>auto Mashup</span></a><span>Lokal auf deinem Mac</span></header><main>
 <div className="intro"><h1>Zwei Tracks. Ein neuer Mix.</h1><p>Wechsle Gesang und Instrumente. Gestalte Builds, Drops und neue Verbindungen.<br/>Deine Songs, in einem gemeinsamen Arrangement.</p></div>
 {error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')} aria-label="Fehlermeldung schließen">×</button></div>}
 {loading?<div className="loading">Studio wird geladen …</div>:<>
 <div className="tracks">{[['A',trackA],['B',trackB]].map(([letter,track])=><TrackPanel key={letter} letter={letter} track={track} tracks={tracks} busy={busy} onChoose={id=>choose(letter,id)} onUpload={file=>upload(file,letter)}/>)}</div>
 <Arrangement sections={sections} setSections={setSections} onPlan={qualityPlan} busy={busy||!a||!b} bpm={bpm} setBpm={setBpm} keyMatch={keyMatch} setKeyMatch={setKeyMatch}/>
 <section className="quality-panel panel" aria-label="Musikalische Qualität"><div><h2>Passende Phrasen finden</h2><p>Längere Gesangspassagen, eine vertraute Begleitung beim Sängerwechsel und wiederkehrende Motive. Wählt zusammenhängende 8- oder 16-Takt-Phrasen und berücksichtigt auffällige Klangwechsel innerhalb des Gesangs. Neue Stems werden beim ersten Planen vorbereitet.</p></div><button disabled={busy||!a||!b} onClick={qualityPlan}>Musikalisch planen</button>{quality&&<div className="quality-note"><p>{quality.analysis.note}</p><p>Tempo-Vergleich: <strong>{quality.target_bpm} BPM</strong> verteilt die Tempoänderung gleichmäßig auf beide Songs. Dein gewähltes Zieltempo bleibt erhalten.</p><button className="subtle" disabled={busy} onClick={()=>setBpm(quality.target_bpm)}>{quality.target_bpm} BPM übernehmen</button><span>Gewähltes Tempo: A {trackA&&Math.round(((Number(bpm)||quality.target_bpm)/trackA.bpm-1)*100)} % · B {trackB&&Math.round(((Number(bpm)||quality.target_bpm)/trackB.bpm-1)*100)} %</span></div>}</section>
 <section className="quality-panel panel" aria-label="Vocal-Trennung"><div><h2>Klarere Vocals</h2><p>Trennt zuerst Gesang und Begleitung, danach die Instrumente. Die bisherige Trennung bleibt zum Vergleichen verfügbar.</p><p>Track A: {trackA?.hq_separated?'Neue Stems bereit':'Bisherige Trennung'} · Track B: {trackB?.hq_separated?'Neue Stems bereit':'Bisherige Trennung'}</p></div><button disabled={busy||!a||!b||!hqInstalled||!!(trackA?.hq_separated&&trackB?.hq_separated)} onClick={separateHQ}>Vocals neu trennen</button><label>Trennung für den Mix <select disabled={busy} value={separationQuality} onChange={e=>setSeparationQuality(e.target.value)}><option value="auto">Neue Stems, wenn vorhanden</option><option value="standard">Bisherige Stems · Vergleich</option><option value="hq" disabled={!(trackA?.hq_separated&&trackB?.hq_separated)}>Nur neue Stems</option></select></label>{!hqInstalled&&<p>Die zusätzliche Trennung ist noch nicht installiert.</p>}</section>
 <details className="analysis-details"><summary>Tempo- und Tonartschätzung korrigieren</summary><p>Bei halbem oder doppeltem Tempo die BPM hier korrigieren. Die Tonartschätzung vergleicht Tonverteilungen, keine einzelnen Akkordfolgen.</p><div className="corrections"><label>Track A · BPM<input type="number" min="40" max="240" placeholder={trackA?.bpm} value={bpmA} onChange={e=>setBpmA(e.target.value)}/></label><label>Track B · BPM<input type="number" min="40" max="240" placeholder={trackB?.bpm} value={bpmB} onChange={e=>setBpmB(e.target.value)}/></label><label>Track B · Halbtöne<input type="number" min="-6" max="6" step="0.5" placeholder="Automatisch" value={pitchB} onChange={e=>setPitchB(e.target.value)}/></label></div></details>
 <ResultPanel job={job} result={result} history={history} onSelect={setResult} onRender={render} onCancel={async()=>{try{await api('/jobs/'+job.id+'/cancel',{});}catch(e){setError(e.message)}}} busy={busy} ready={!!(a&&b&&sections.length)}/>
 </>}
 <footer>Die Audiodateien werden lokal verarbeitet.<details><summary>Speicherort & Werkzeuge</summary><p>{dataDir}</p><p>AutoMashup · Mel-Band RoFormer · Demucs · Beat This! · Rubber Band · librosa · FFmpeg</p></details></footer>
 </main></>
}
createRoot(document.getElementById('root')).render(<App/>);
