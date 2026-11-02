import {useEffect,useRef,useState} from "react";
import type {InspectionEvent} from "../inspection/inspectionLog";
import {synchronizeLog} from "../inspection/inspectionLog";
import type {useRecordedObserver} from "../inspection/recordedObserver";
import {timeLabel} from "../inspection/types";
export function InspectionLog({observer,currentTime,playing,seekRevision,sourceKey,started,registrationError,registering,retryUpload}: {
  observer:ReturnType<typeof useRecordedObserver>;currentTime:number;playing:boolean;seekRevision:number;sourceKey:string;started:boolean;
  registrationError:string;registering:boolean;retryUpload:()=>void;
}) {
  const [visible,setVisible]=useState<InspectionEvent[]>([]),[tail,setTail]=useState(true);
  const previousSeek=useRef(seekRevision), previousSource=useRef(sourceKey),messageBox=useRef<HTMLDivElement>(null),autoScrolling=useRef(false);
  const job=observer.job;
  useEffect(()=>{
    const changed=previousSource.current!==sourceKey,seeked=previousSeek.current!==seekRevision;
    previousSeek.current=seekRevision;previousSource.current=sourceKey;
    setVisible(prev=>synchronizeLog(changed?[]:prev,job?.events??[],currentTime,playing,seeked));
  },[job?.events,currentTime,playing,seekRevision,sourceKey]);
  useEffect(()=>{
    if(!tail||!messageBox.current)return;
    autoScrolling.current=true;messageBox.current.scrollTop=messageBox.current.scrollHeight;
    const frame=requestAnimationFrame(()=>{autoScrolling.current=false;});return()=>cancelAnimationFrame(frame);
  },[visible,tail]);
  const backendUnavailable=observer.status && (!observer.status.enabled || !observer.status.available);
  return <aside className="inspection-log card" aria-label="Inspection Log">
    <header><p className="eyebrow">Automatic Recipe Observation</p><h2>Inspection Log</h2><p>{playing?"Following Playback":"Paused · Incoming Entries Held"} · {timeLabel(currentTime)}</p></header>
    <div className="inspection-log-status" role="status">
      {registering ? "Registering Recording…" : backendUnavailable ? observer.status?.reason || "Automatic observation is unavailable. Configure the separate recipe store and video decoder." : observer.busy ? `${job?.stage??"Starting Analysis"} · ${job?.progress??0}%` : job?.state==="completed"||job?.state==="saved" ? `${job.stage??"Saved Analysis"} · Results Follow Video Time` : started ? "Waiting for Analysis" : "Play the Recording to Start Automatic Analysis"}
    </div>
    {(registrationError||observer.error||job?.error)&&<div className="workspace-error" role="alert">{registrationError||observer.error||job?.error}<button className="ghost-button" onClick={()=>registrationError?retryUpload():void observer.start(true)}>Retry Analysis</button></div>}
    {observer.busy&&playing&&visible.length===0&&<p className="workspace-note">Analysis is catching up. Entries appear only when supported video evidence is ready.</p>}
    <div ref={messageBox} className="inspection-log-messages" role="log" aria-label="Timestamped Inspection Events" aria-live={playing?"polite":"off"} onScroll={e=>{if(autoScrolling.current)return;const el=e.currentTarget;setTail(el.scrollHeight-el.scrollTop-el.clientHeight<60);}}>
      {visible.map(e=><article key={e.id} className={`inspection-log-entry is-${e.kind}`}><div><time>{timeLabel(e.at)}</time><span>{e.vial}</span></div><h3>{e.title}</h3><p>{e.detail}</p><small>Automatic pixel observation · Experimental</small></article>)}
      {!visible.length&&<p className="workspace-note">No analysis entries at this playback time. Saved review annotations are not used as inference results.</p>}
    </div>
    {!tail&&<button className="ghost-button" onClick={()=>setTail(true)}>Follow Latest Visible Entry</button>}
    {job&&(job.state==="completed"||job.state==="saved")&&!job.events?.length&&currentTime>=(job.analyzed_through_seconds??Infinity)&&<p className="workspace-warning">No assessable fills were detected. This does not establish that the recording contains no fills.</p>}
    <footer><p>Recipe IDs describe observed patterns, not verified chemical identity. Timing, color and visibility holds remain in force.</p><p>Analysis continues while paused. Seek to review completed evidence at another time; replay does not create duplicate recipe votes.</p></footer>
  </aside>;
}
