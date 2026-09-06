import React,{useEffect,useRef,useState} from 'react';
export function TrackPanel({letter,track,tracks,onChoose,onUpload,busy}){
 const file=useRef(null),player=useRef(null);const[stem,setStem]=useState('audio');const audition=useRef({at:0,playing:false});
 useEffect(()=>{audition.current={at:0,playing:false};setStem('audio')},[track?.id]);
 function selectStem(value){audition.current={at:player.current?.currentTime||0,playing:player.current?!player.current.paused:false};setStem(value)}
 return <section className={'track track-'+letter} aria-label={'Track '+letter}>
  <div className="track-top"><h2>Track {letter}</h2>{track&&<div className="metrics"><span title="Geschätztes Tempo">{track.bpm} BPM</span><span title={`Tonartschätzung; alternativ ${track.key_alternative}`}>{track.key.replace(' major',' Dur').replace(' minor',' Moll')}</span></div>}</div>
  {tracks.length>0?<select aria-label={'Song für Track '+letter} className="track-select" value={track?.id||''} onChange={e=>{setStem('audio');onChoose(e.target.value)}}><option value="" disabled>Song wählen</option>{tracks.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select>:<p>Wähle deinen {letter==='A'?'ersten':'zweiten'} Song.</p>}
  <svg className="wave" viewBox="0 0 720 80" preserveAspectRatio="none" role="img" aria-label={track?'Wellenform des Songs':'Noch kein Song geladen'} onClick={e=>{if(track&&player.current){const box=e.currentTarget.getBoundingClientRect();player.current.currentTime=(e.clientX-box.left)/box.width*track.duration}}}>
   {(track?.waveform||Array(360).fill(.025)).map((v,i)=><line key={i} x1={i*2} x2={i*2} y1={40-v*34} y2={40+v*34}/>)}
  </svg>
  {track?<audio ref={player} key={track.id+stem} controls preload="metadata" onLoadedMetadata={()=>{const audio=player.current;if(!audio)return;audio.currentTime=Math.min(audition.current.at,audio.duration||0);if(audition.current.playing)audio.play().catch(()=>{});}} src={stem==='audio'?`/api/tracks/${track.id}/audio`:`/api/tracks/${track.id}/stems/${stem==='vocals-old'?'vocals':stem}?quality=${stem==='vocals-old'?'standard':'auto'}`}/>:<div className="audio-empty">MP3 · WAV · OGG · FLAC · M4A · AIFF</div>}
  <div className="track-bottom"><button disabled={busy} onClick={()=>file.current.click()}>↥ &nbsp; Datei wählen</button><input ref={file} hidden type="file" accept="audio/*,.ogg,.flac" onChange={e=>{if(e.target.files[0])onUpload(e.target.files[0]);e.target.value=''}}/>
   {(track?.separated||track?.hq_separated)&&<select aria-label={'Spur vorhören Track '+letter} value={stem} onChange={e=>selectStem(e.target.value)}><option value="audio">Original</option><option value="vocals">{track.hq_separated?'Gesang · RoFormer':'Gesang solo'}</option>{track.hq_separated&&track.separated&&<option value="vocals-old">Gesang · Demucs bisher</option>}<option value="drums">Drums solo</option><option value="bass">Bass solo</option><option value="other">Instrumente solo</option></select>}
  </div>
 </section>
}
