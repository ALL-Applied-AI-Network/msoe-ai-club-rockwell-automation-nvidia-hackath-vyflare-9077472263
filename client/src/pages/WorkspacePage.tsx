import {useEffect,useRef,useState} from "react";
import {Camera,Film,Maximize,Radio,Upload,VideoOff} from "lucide-react";
import {CosmosPanel} from "../components/CosmosPanel";
import {InspectionLog} from "../components/InspectionLog";
import {AutomaticGeometry} from "../components/AutomaticGeometry";
import {geometryAt,useAutomaticGeometry,useRecordedGeometry} from "../inspection/automaticGeometry";
import {useRecordedObserver} from "../inspection/recordedObserver";
import {useRecordingSource} from "../inspection/useRecordingSource";
import {readResponse,type Health,type RecordedVideo} from "../inspection/types";
import "../workspace.css";

export function WorkspacePage(){
  const [mode,setMode]=useState<"recorded"|"live">("recorded"),[videos,setVideos]=useState<RecordedVideo[]>([]),[videoId,setVideoId]=useState("video-1");
  const [file,setFile]=useState<File|null>(null),[uploadedUrl,setUploadedUrl]=useState<string|null>(null),[health,setHealth]=useState<Health|null>(null);
  const [currentTime,setCurrentTime]=useState(0),[playing,setPlaying]=useState(false),[started,setStarted]=useState(false),[seekRevision,setSeekRevision]=useState(0);
  const [opening,setOpening]=useState(0);
  const [mediaReady,setMediaReady]=useState(false),[error,setError]=useState(""),[showTracking,setShowTracking]=useState(true);
  const [cameraState,setCameraState]=useState("off"),[devices,setDevices]=useState<MediaDeviceInfo[]>([]),[deviceId,setDeviceId]=useState("");
  const media=useRef<HTMLVideoElement>(null),container=useRef<HTMLDivElement>(null),stream=useRef<MediaStream|null>(null),cameraGeneration=useRef(0);
  const selected=videos.find(v=>v.id===videoId);
  const sourceKey=mode+":"+(file?`opened-${opening}`:videoId),sourceUrl=file?(uploadedUrl??undefined):(selected?.available?selected.url:undefined);
  const recording=useRecordingSource(mode==="recorded"?videoId:undefined,mode==="recorded"?file:null);
  const observer=useRecordedObserver(mode==="recorded"?recording.id:undefined,mode==="recorded"&&started&&mediaReady);
  const geometry=useRecordedGeometry(mode==="recorded"?recording.id:undefined,observer.job?.state);
  const cached=mode==="recorded"&&geometry.job?.state==="complete"?geometryAt(geometry.job.frames,currentTime)??null:null;
  const tracking=useAutomaticGeometry(media,showTracking&&mediaReady&&!cached,sourceKey);
  const recent=tracking.frame&&Math.abs(currentTime-tracking.frame.captured_at)<=.4?tracking.frame:null;
  const automaticFrame=showTracking?cached??recent:null;
  const refresh=()=>{fetch("/api/inference/status").then(readResponse<Health>).then(setHealth).catch(()=>setHealth({available:false,mode:"unavailable",models:[]}));};
  useEffect(()=>{const abort=new AbortController();fetch("/api/inspection/evidence",{signal:abort.signal}).then(readResponse<{videos:RecordedVideo[]}>).then(b=>setVideos(b.videos)).catch(e=>{if(e.name!=="AbortError")setError(e.message);});refresh();return()=>abort.abort();},[]);
  useEffect(()=>{if(!file){setUploadedUrl(null);return;}const url=URL.createObjectURL(file);setUploadedUrl(url);return()=>URL.revokeObjectURL(url);},[file]);
  useEffect(()=>{setStarted(false);setPlaying(false);setCurrentTime(0);setMediaReady(false);setError("");setSeekRevision(n=>n+1);},[sourceKey]);
  const stopCamera=()=>{cameraGeneration.current++;stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;if(media.current)media.current.srcObject=null;setCameraState("off");setMediaReady(false);};
  useEffect(()=>()=>{cameraGeneration.current++;stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;},[mode]);
  const connectCamera=async()=>{
    stopCamera();const generation=cameraGeneration.current;setCameraState("connecting");
    try{
      const next=await navigator.mediaDevices.getUserMedia({video:deviceId?{deviceId:{exact:deviceId},width:{ideal:640},height:{ideal:480}}:{width:{ideal:640},height:{ideal:480}},audio:false});
      if(generation!==cameraGeneration.current){next.getTracks().forEach(t=>t.stop());return;}
      stream.current=next;if(media.current){media.current.srcObject=next;await media.current.play();}setCameraState("connected");
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==="videoinput"));
    }catch(e){if(generation===cameraGeneration.current){setCameraState("error");setError(e instanceof Error?e.message:"Camera connection failed.");}}
  };
  return <><div className="page-heading"><div><p className="eyebrow">Filling Station · Camera Evidence</p><h1>Inspection Workspace</h1><p>Play a recording to observe fills and follow the automatic recipe log.</p></div><div className="workspace-mode" role="group" aria-label="Inspection Mode"><button aria-pressed={mode==="recorded"} onClick={()=>{stopCamera();setMode("recorded");}}><Film size={16}/>Recorded</button><button aria-pressed={mode==="live"} onClick={()=>setMode("live")}><Radio size={16}/>Live</button></div></div>
    <div className="workspace-toolbar" aria-label="Evidence Controls">{mode==="recorded"?<><label>Video<select value={file?"opened":videoId} onChange={e=>{setFile(null);setVideoId(e.target.value);}}>{file&&<option value="opened">{file.name}</option>}{videos.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select></label><label className="workspace-upload"><Upload size={16}/>Open a Recording<input type="file" accept="video/mp4,video/webm,video/quicktime,.mov,.m4v" onChange={e=>{const f=e.target.files?.[0];if(f){setUploadedUrl(null);setFile(f);setOpening(n=>n+1);setError("");}e.target.value="";}}/></label><span className="workspace-note">New recordings from this station view are analyzed automatically when played. No training or manual recipe setup.</span></>:<><label>Camera<select value={deviceId} onChange={e=>setDeviceId(e.target.value)}><option value="">Default Camera</option>{devices.map(d=><option key={d.deviceId} value={d.deviceId}>{d.label||"Camera"}</option>)}</select></label><button className="workspace-secondary" onClick={()=>void connectCamera()}><Camera size={16}/>Connect Camera</button><button className="ghost-button" onClick={stopCamera}><VideoOff size={16}/>Disconnect</button><span>{cameraState}</span></>}</div>
    <div className="workspace-grid"><div className="workspace-evidence"><div className="workspace-player" ref={container}>
      <video key={sourceKey} ref={media} src={mode==="recorded"?sourceUrl:undefined} controls={mode==="recorded"} muted playsInline preload="metadata"
        onLoadedMetadata={e=>{const v=e.currentTarget;if(v.videoWidth!==640||v.videoHeight!==480){setMediaReady(false);setError("Automatic inspection requires the calibrated 640 × 480 station view. This recording is available for playback only.");}else setMediaReady(true);}}
        onPlay={()=>{setPlaying(true);if(mode==="recorded")setStarted(true);}} onPause={()=>setPlaying(false)} onEnded={()=>setPlaying(false)}
        onTimeUpdate={e=>setCurrentTime(e.currentTarget.currentTime)} onSeeked={e=>{setCurrentTime(e.currentTarget.currentTime);setSeekRevision(n=>n+1);}}
        onError={()=>setError("This video cannot be played. Choose a browser-supported recording.")}/>
      {automaticFrame&&<AutomaticGeometry media={media} frame={automaticFrame}/>}<span className="workspace-feed-label">{mode==="recorded"?"Recorded Evidence":"Camera Preview"}</span><button className="workspace-fullscreen" aria-label="Expand Evidence View" onClick={()=>void container.current?.requestFullscreen()}><Maximize size={16}/></button>
      {mode==="recorded"&&<div className="workspace-vial-card"><strong>{file?.name??selected?.name??"Recording"}</strong><small>Automatic observations appear in the Inspection Log. No reviewed timeline is used as inference.</small></div>}
    </div>
    <section className="automatic-tracking-status"><div className="workspace-section-heading"><h2>Automatic Vial and Liquid Tracking</h2><label className="inline-check"><input type="checkbox" checked={showTracking} onChange={e=>setShowTracking(e.target.checked)}/>Show Tracking</label></div><strong>{!showTracking?"Tracking Off":cached?"Recorded Automatic Tracking":tracking.state}</strong><p>Fixed 640 × 480 station view. Hidden or uncertain liquid surfaces remain unmarked. Numeric liquid level is excluded from recipe matching.</p>{tracking.error&&!cached&&<p role="alert">{tracking.error}</p>}</section>
    {mode==="recorded"&&<CosmosPanel key={sourceKey} media={media} sourceLabel={file?.name??selected?.name??"Recording"} health={health} mediaReady={mediaReady} disabled={false} refresh={refresh}/>}
    {mode==="live"&&<p className="workspace-warning">Live camera tracking is experimental. Automatic live fill completion and recipe processing remain pending; recorded inspection is the current workflow.</p>}
    {error&&<p className="workspace-error" role="alert">{error}</p>}
    </div>
    {mode==="recorded"?<InspectionLog key={sourceKey} observer={observer} currentTime={currentTime} playing={playing} seekRevision={seekRevision} sourceKey={sourceKey} started={started} registrationError={recording.error} registering={recording.registering} retryUpload={recording.retry}/>:<aside className="inspection-log card"><h2>Inspection Log</h2><p>Live recipe observation will be connected in the next phase.</p></aside>}
    </div>
  </>;
}
