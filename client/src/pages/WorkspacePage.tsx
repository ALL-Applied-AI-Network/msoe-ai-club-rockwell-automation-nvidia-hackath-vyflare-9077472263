import { useEffect, useRef, useState } from "react";
import { Camera, ChevronLeft, ChevronRight, Film, Maximize, Radio, Upload, VideoOff } from "lucide-react";
import { Link } from "react-router-dom";
import { Model4Panel } from "../components/Model4Panel";
import { AutomaticGeometry } from "../components/AutomaticGeometry";
import { geometryAt, useAutomaticGeometry, useRecordedGeometry } from "../inspection/automaticGeometry";
import { VideoGeometry } from "../components/VideoGeometry";
import { RecordedObserverPanel } from "../components/RecordedObserverPanel";
import { detectedRecipeLabel, useRecordedObserver } from "../inspection/recordedObserver";
import { readFrame, readResponse, timeLabel, type Frame, type Health, type RecordedVideo } from "../inspection/types";
import "../workspace.css";
import { playbackObservation } from "../inspection/playback";

export function WorkspacePage() {
  const [mode, setMode] = useState<"recorded" | "live">("recorded");
  const [videos, setVideos] = useState<RecordedVideo[]>([]), [videoId, setVideoId] = useState("video-1"), [vialId, setVialId] = useState("");
  const [health, setHealth] = useState<Health | null>(null), [evidenceError, setEvidenceError] = useState("");
  const [uploaded, setUploaded] = useState<{ url: string; name: string } | null>(null);
  const [frames, setFrames] = useState<Frame[]>([]), [busy, setBusy] = useState(false), [capturing, setCapturing] = useState(false);
  const [error, setError] = useState(""), [currentTime, setCurrentTime] = useState(0), [mediaReady, setMediaReady] = useState(false);
  const [cameraState, setCameraState] = useState<"off" | "connecting" | "connected">("off");
  const [cameraDevices, setCameraDevices] = useState<MediaDeviceInfo[]>([]), [deviceId, setDeviceId] = useState("");
  const video = useRef<HTMLVideoElement>(null), canvasArea = useRef<HTMLDivElement>(null), stream = useRef<MediaStream | null>(null);
  const generation = useRef(0), cameraGeneration = useRef(0), uploadGeneration = useRef(0), healthRequest = useRef<AbortController | null>(null);
  const selectedVideo = videos.find(v => v.id === videoId);
  const selectedVial = !uploaded ? selectedVideo?.vials.find(v => v.id === vialId) : undefined;
  const sourceUrl = uploaded?.url ?? (selectedVideo?.available ? selectedVideo.url : undefined);
  const sourceKey = `${mode}:${uploaded?.url ?? videoId}:${vialId}`;
  const blocked = busy || capturing;
  const observation = playbackObservation(uploaded ? [] : selectedVideo?.vials ?? [], currentTime);
  const observer = useRecordedObserver(mode === "recorded" && !uploaded ? videoId : undefined);
  const [showTracking, setShowTracking] = useState(true);
  const geometryRecording = useRecordedGeometry(mode === "recorded" && !uploaded ? videoId : undefined, observer.job?.state);
  const cachedGeometry = mode === "recorded" && geometryRecording.job?.state === "complete" ? geometryAt(geometryRecording.job.frames, currentTime) ?? null : null;
  const tracking = useAutomaticGeometry(video, showTracking && mediaReady && !cachedGeometry, `${mode}:${sourceUrl ?? "camera"}`);
  const recentFrame = tracking.frame && Math.abs(currentTime - tracking.frame.captured_at) <= .4 ? tracking.frame : null;
  const automaticFrame = showTracking ? cachedGeometry ?? recentFrame : null;
  const detectedAtTime = observer.job?.assessments.find(a => {
    const o = a.observation;
    return currentTime >= o.source_episode_intervals[0].start[0] && !!o.departure_interval_seconds && currentTime < o.departure_interval_seconds[1];
  });

  const refresh = () => {
    healthRequest.current?.abort(); const abort = new AbortController(); healthRequest.current = abort;
    fetch("/api/inference/status", { signal: abort.signal }).then(readResponse<Health>).then(setHealth).catch(e => {
      if (e.name !== "AbortError") setHealth({ available: false, mode: "unavailable", models: [], message: e.message });
    });
  };
  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/inspection/evidence", { signal: abort.signal }).then(readResponse<{ videos: RecordedVideo[] }>).then(body => {
      setVideos(body.videos); setVialId(body.videos[0]?.vials[0]?.id ?? "");
    }).catch(e => { if (e.name !== "AbortError") setEvidenceError(e.message); });
    refresh(); return () => { abort.abort(); healthRequest.current?.abort(); };
  }, []);
  useEffect(() => () => { if (uploaded) URL.revokeObjectURL(uploaded.url); }, [uploaded]);
  const stopCamera = () => {
    cameraGeneration.current++; stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    if (video.current) video.current.srcObject = null;
    setCameraState("off"); setMediaReady(false);
  };
  useEffect(() => {
    generation.current++; uploadGeneration.current++; setFrames([]); setError(""); setCurrentTime(0); setMediaReady(mode === "recorded" && (video.current?.readyState ?? 0) >= 2);
    if (video.current && mode === "recorded" && selectedVial && video.current.readyState >= 1) video.current.currentTime = Math.max(0, selectedVial.pulses[0].startLower - 2);
    return () => { generation.current++; };
  }, [sourceKey]);
  useEffect(() => {
    return () => { cameraGeneration.current++; stream.current?.getTracks().forEach(track => track.stop()); stream.current = null; };
  }, [mode]);

  const connectCamera = async () => {
    if (!navigator.mediaDevices?.getUserMedia) { setError("Camera access requires localhost or HTTPS and a supported browser."); return; }
    stopCamera(); const id = ++cameraGeneration.current; setCameraState("connecting"); setError("");
    try {
      const next = await navigator.mediaDevices.getUserMedia({ video: deviceId ? { deviceId: { exact: deviceId } } : { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
      if (id !== cameraGeneration.current) { next.getTracks().forEach(track => track.stop()); return; }
      stream.current = next;
      if (video.current) { video.current.srcObject = next; await video.current.play(); }
      if (id !== cameraGeneration.current) return;
      setCameraState("connected");
      next.getVideoTracks()[0]?.addEventListener("ended", () => { if (id === cameraGeneration.current) { stopCamera(); setError("Camera feed ended. Reconnect to preview."); } });
      navigator.mediaDevices.enumerateDevices().then(devices => { if (id === cameraGeneration.current) setCameraDevices(devices.filter(d => d.kind === "videoinput")); }).catch(() => {});
    } catch (e) {
      if (id !== cameraGeneration.current) return;
      stopCamera(); setError(e instanceof Error ? `Camera unavailable: ${e.message}` : "Camera connection failed.");
    }
  };
  const switchMode = (next: "recorded" | "live") => { if (next !== mode) { stopCamera(); setMode(next); } };
  const seek = (seconds: number) => { if (video.current && mode === "recorded") { video.current.currentTime = seconds; video.current.pause(); } };
  const uploadFrames = async (files: FileList | null) => {
    if (!files) return;
    const id = ++uploadGeneration.current; setFrames([]); setError("");
    try {
      if (files.length !== 3) throw new Error("Select exactly three post-fill frames together.");
      const result = await Promise.all(Array.from(files).map(readFrame));
      if (id === uploadGeneration.current) setFrames(result);
    } catch (e) { if (id === uploadGeneration.current) setError(e instanceof Error ? e.message : "Could not load frames."); }
  };
  const captureFrames = async () => {
    const player = video.current; if (!player || !selectedVial || mode !== "recorded") return;
    setCapturing(true); setFrames([]); setError(""); const id = ++generation.current;
    try {
      if (player.videoWidth !== 640 || player.videoHeight !== 480) throw new Error("Model 4 requires 640 × 480 footage. This video is not resized.");
      const times = [0.05, 0.15, 0.25].map(offset => selectedVial.flowEndUpper + offset);
      if (times[2] >= selectedVial.stationaryUntil || times[2] >= player.duration) throw new Error("No reviewed three-frame window exists before movement. Supply independently reviewed frames.");
      player.pause(); const next: Frame[] = [];
      for (const time of times) {
        if (Math.abs(player.currentTime - time) > 0.0001) await new Promise<void>((resolve, reject) => {
          const done = () => { cleanup(); resolve(); }; const fail = () => { cleanup(); reject(new Error("Could not seek to the post-fill frame.")); };
          const timeout = window.setTimeout(fail, 8000); const cleanup = () => { window.clearTimeout(timeout); player.removeEventListener("seeked", done); player.removeEventListener("error", fail); };
          player.addEventListener("seeked", done); player.addEventListener("error", fail); player.currentTime = time;
        });
        if (id !== generation.current) return;
        const canvas = document.createElement("canvas"); canvas.width = 640; canvas.height = 480;
        const context = canvas.getContext("2d"); if (!context) throw new Error("Frame capture is unavailable in this browser.");
        context.drawImage(player, 0, 0);
        next.push({ dataUrl: canvas.toDataURL("image/png"), label: `Requested ${timeLabel(time)}`, requestedTime: time });
      }
      setFrames(next);
    } catch (e) { if (id === generation.current) setError(e instanceof Error ? e.message : "Frame capture failed."); }
    finally { setCapturing(false); }
  };
  const index = selectedVideo?.vials.findIndex(v => v.id === vialId) ?? -1;
  const chooseVideo = (id: string) => { setUploaded(null); setVideoId(id); setVialId(videos.find(v => v.id === id)?.vials[0]?.id ?? ""); };
  return <>
    <div className="page-heading workspace-heading"><div><p className="eyebrow">Filling Station · Camera Evidence</p><h1>Inspection Workspace</h1><p>Select evidence, review the fill, and compare its mixture.</p></div>
      <div className="workspace-mode" role="group" aria-label="Inspection mode"><button aria-pressed={mode === "recorded"} disabled={blocked} onClick={() => switchMode("recorded")}><Film size={17} />Recorded</button><button aria-pressed={mode === "live"} disabled={blocked} onClick={() => switchMode("live")}><Radio size={17} />Live</button></div>
    </div>
    <section className="workspace-toolbar" aria-label="Evidence controls">
      {mode === "recorded" ? <>
        <label>Video<select value={uploaded ? "uploaded" : videoId} disabled={blocked} onChange={e => chooseVideo(e.target.value)}>{videos.map(v => <option value={v.id} key={v.id}>{v.name}{!v.available ? " · source missing" : ""}</option>)}{uploaded && <option value="uploaded">{uploaded.name}</option>}</select></label>
        <label>Vial to Compare<select value={vialId} disabled={blocked || !!uploaded || !selectedVideo} onChange={e => setVialId(e.target.value)}>{!selectedVideo && <option>Annotations unavailable</option>}{selectedVideo?.vials.map(v => <option value={v.id} key={v.id}>{v.label} · {v.pulses.length} observed pulses</option>)}</select></label>
        <div className="workspace-vial-nav"><button className="workspace-icon" aria-label="Previous vial" disabled={blocked || !!uploaded || index <= 0} onClick={() => setVialId(selectedVideo!.vials[index - 1].id)}><ChevronLeft size={18} /></button><button className="workspace-icon" aria-label="Next vial" disabled={blocked || !!uploaded || !selectedVideo || index >= selectedVideo.vials.length - 1} onClick={() => setVialId(selectedVideo!.vials[index + 1].id)}><ChevronRight size={18} /></button></div>
        <label className="workspace-upload"><Upload size={16} />Open a Video<input type="file" accept="video/mp4,video/webm" disabled={blocked} onChange={e => {
          const file = e.target.files?.[0]; if (!file) return;
          if (!["video/mp4", "video/webm"].includes(file.type)) { setError("Select an MP4 or WebM video."); return; }
          setUploaded({ url: URL.createObjectURL(file), name: file.name });
        }} /></label>
      </> : <>
        <label>Camera<select value={deviceId} disabled={cameraState !== "off"} onChange={e => setDeviceId(e.target.value)}><option value="">Default browser camera</option>{cameraDevices.map(d => <option value={d.deviceId} key={d.deviceId}>{d.label || "Camera"}</option>)}</select></label>
        <button className="workspace-secondary" disabled={cameraState === "connecting"} onClick={() => cameraState === "connected" ? stopCamera() : void connectCamera()}>{cameraState === "connected" ? <VideoOff size={16} /> : <Camera size={16} />}{cameraState === "connected" ? "Disconnect Camera" : cameraState === "connecting" ? "Connecting…" : "Connect Camera"}</button>
        <span className="workspace-warning workspace-inline">Automatic Visual Tracking · Experimental</span>
      </>}
    </section>
    {mode === "recorded" && <p className="workspace-note">Vials are numbered in video order, not by barcode or batch position. The overlay follows playback; the vial selected for comparison stays fixed.</p>}
    {evidenceError && <p className="workspace-error" role="alert">{evidenceError} You can still open a local video or supply reviewed frames.</p>}
    <div className="workspace-grid">
      <div className="workspace-evidence">
        <div ref={canvasArea} className="workspace-player">
          <video key={mode + (mode === "recorded" ? sourceUrl ?? "none" : "camera")} ref={video} src={mode === "recorded" ? sourceUrl : undefined} controls={mode === "recorded" && !!sourceUrl} muted playsInline preload="metadata"
            onLoadedMetadata={() => { if (mode === "recorded" && selectedVial && video.current) video.current.currentTime = Math.max(0, selectedVial.pulses[0].startLower - 2); }}
            onLoadedData={() => setMediaReady(true)} onTimeUpdate={e => setCurrentTime(e.currentTarget.currentTime)} onError={() => { setMediaReady(false); setError("Video could not be loaded. Check the source file or select another video."); }} />
          <AutomaticGeometry media={video} frame={automaticFrame} />
          <div className="workspace-feed-label"><span className={`workspace-dot ${mode === "live" && cameraState === "connected" ? "is-connected" : ""}`} />{mode === "recorded" ? "Recorded Evidence" : cameraState === "connected" ? "Live Camera Preview" : "Camera Disconnected"}</div>
          <button className="workspace-fullscreen workspace-icon" aria-label="Expand Evidence View" onClick={() => void canvasArea.current?.requestFullscreen().catch(() => setError("Fullscreen is unavailable."))}><Maximize size={16} /></button>
          {((mode === "recorded" && !sourceUrl) || (mode === "live" && cameraState === "off")) && <div className="workspace-player-empty">{mode === "recorded" ? <Film size={36} /> : <Camera size={36} />}<h2>{mode === "recorded" ? "Select a Video Source" : "Connect a Camera"}</h2><p>{mode === "recorded" ? "Open a local video if the recorded source is not installed." : "Connect the fixed-station camera to start automatic vial and visible liquid-surface tracking."}</p></div>}
          {mode === "recorded" && sourceUrl && <>
            <section className="workspace-activity-overlay" aria-label="Playback activity summary">
              <span className="workspace-overlay-caption">Inspection Overlay · {timeLabel(currentTime)}</span>
              <strong>{uploaded ? "No timed annotations for this video" : observation.state}</strong>
              <p>{uploaded ? "Supply reviewed frames to compare a mixture." : observation.detail}</p>
              <small>Reviewed annotations · follows playback</small>
            </section>
            <div className="workspace-vial-card">
              <span>At Current Video Time</span>
              <strong>{observation.vial?.label ?? "No reviewed vial"}</strong>
              {observation.appearance && <p>Observed appearance: {observation.appearance}</p>}
              <p>Recipe: {detectedRecipeLabel(detectedAtTime)}</p><small>{detectedAtTime ? "Automatic fixed-station fill association · experimental" : "Pixel tracking is shown separately; recipe identity requires completed fill evidence"}</small>
            </div>
          </>}
        </div>
        <section className="automatic-tracking-status" aria-label="Automatic Tracking Status">
          <div className="workspace-section-heading"><h2>Automatic Vial and Liquid Tracking</h2><label className="inline-check"><input type="checkbox" checked={showTracking} onChange={e => setShowTracking(e.target.checked)} />Show Tracking</label></div>
          <strong>{!showTracking ? "Tracking Off" : cachedGeometry ? "Recorded Automatic Tracking" : tracking.state}</strong>
          <p>Fixed 640 × 480 station view, active filling position only. Boxes follow detected vials; a dashed line appears only when a colored liquid surface is visible. Hidden or uncertain surfaces remain unmarked. Tracking IDs describe this session, not video-order vial numbers or recipe identities.</p>
          {automaticFrame?.detections.map(d => <p key={d.position}>{d.position}: {d.status === "TRACKING" ? d.track_id?.replace(/^Vial /, "Track ") : d.status === "MOVING" ? "Moving · Identity Reset" : "Confirming"} · {d.surface ? "Visible Liquid Surface" : "Liquid Surface Not Reliably Visible"}</p>)}
          {tracking.error && !cachedGeometry && <p role="alert">{tracking.error}</p>}
          {geometryRecording.job?.error && <p role="alert">{geometryRecording.job.error}</p>}
          {geometryRecording.error && mode === "recorded" && <p role="alert">{geometryRecording.error}</p>}
          {mode === "recorded" && !uploaded && <><button className="workspace-secondary" disabled={observer.busy || geometryRecording.job?.state === "processing"} onClick={() => void geometryRecording.start()}>{geometryRecording.job?.state === "processing" ? `Tracking Recording… ${geometryRecording.job.progress ?? 0}%` : geometryRecording.job?.state === "complete" ? "Load Recorded Tracking" : "Track Entire Recording"}</button><p>Process Recording checks identity and final-color visibility before recipe actions. Track Entire Recording shows geometry evidence only. Numeric liquid level is excluded from matching.</p></>}
          {geometryRecording.job?.state === "complete" && geometryRecording.job.frames.some(f => f.detections.some(d => d.surface)) && <button className="workspace-secondary" onClick={() => { const found = geometryRecording.job?.frames.find(f => f.detections.some(d => d.surface)); if (found) seek(found.captured_at); }}>Review a Detected Surface</button>}
          {geometryRecording.job?.observations && <p>{geometryRecording.job.observations.filter(o => o.track_ids.length !== 1).length} fill intervals need tracking identity review. Recipe eligibility uses the producer’s source-linked tracking checks.</p>}
          {geometryRecording.job?.observations && <details><summary>Geometry Evidence for Detected Fills</summary>{geometryRecording.job.observations.map(o => <p key={o.observation_id}>{o.vial_id.replace(/^V(\d+)-V0*(\d+)$/, "Video $1 · Vial $2")}: {o.tracked_samples}/{o.sample_count} tracked frames · {o.visible_surface_samples} visible surface frames · {o.track_ids.length} Tracking IDs · {o.identity_continuous ? "Continuous Track" : "Continuity Not Established"}</p>)}</details>}
        </section>
        <section className="workspace-timeline card" aria-label="Dispense timeline"><div className="workspace-section-heading"><h2>{mode === "recorded" ? "Reviewed Event Timeline" : "Inspection Pipeline"}</h2><span>{mode === "recorded" ? timeLabel(currentTime) : cameraState === "connected" ? "Preview connected" : "Waiting for camera"}</span></div>
          {mode === "recorded" && selectedVial ? <><div className="workspace-pulses">{selectedVial.pulses.map(p => <button key={p.order} aria-current={observation.vial?.id === selectedVial.id && currentTime >= p.startLower && currentTime <= p.endUpper} disabled={!mediaReady || blocked} onClick={() => seek(p.startUpper)}><strong>Pulse {p.order}</strong><span>{timeLabel(p.startLower)} – {timeLabel(p.endUpper)}</span><small>{p.appearance}</small></button>)}<button disabled={!mediaReady || blocked} onClick={() => seek(selectedVial.finalSampleSeconds)}><strong>Final Sample</strong><span>{timeLabel(selectedVial.finalSampleSeconds)}</span><small>Movement after ≈ {timeLabel(selectedVial.stationaryUntil)}</small></button></div><p className="workspace-note">Sampled visual annotations, not automatic event detection. Pulse count does not establish ingredient count.</p></> : <p className="workspace-note">{mode === "live" ? "Automatic vial and visible liquid-surface tracking run while the camera is connected. Live fill completion, qualified color sampling and automatic recipe assessment still require integration; tracking alone does not start model inference." : "This local video has no reviewed timeline. Supply three independently reviewed post-fill frames below."}</p>}
          {mode === "live" && <p className="workspace-note">Tracking runs automatically after camera connection. Live automatic recipe assessment remains unavailable.</p>}
          <ol className="workspace-stages"><li><span>1</span>Evidence {mediaReady ? "ready" : "pending"}</li><li><span>2</span>{mode === "recorded" && selectedVial ? "Reviewed vial selected" : "Automatic Visual Tracking"}</li><li><span>3</span>{frames.length}/3 frames</li><li><span>4</span>{busy ? "Model 4 running" : "Model 4 on request"}</li></ol>
        </section>
        {mode === "recorded" && !uploaded && selectedVideo && <RecordedObserverPanel key={videoId} observer={{ ...observer, reload: () => { observer.reload(); geometryRecording.reload(); } }} name={selectedVideo.name} onSeek={seek} />}
        {mode === "recorded" && uploaded && <p className="workspace-note">Automatic observation currently supports installed Videos 1 and 2. An opened local video is available for playback and manual frame review.</p>}
        <section className="workspace-frames card"><div className="workspace-section-heading"><div><p className="eyebrow">Model Evidence</p><h2>Three Post-Fill Frames</h2></div><span>{frames.length}/3 selected</span></div>
          <div className="workspace-frame-actions">{mode === "recorded" && selectedVial && <button className="workspace-secondary" disabled={!mediaReady || blocked || !!uploaded} onClick={() => void captureFrames()}>{capturing ? "Extracting frames…" : "Extract Reviewed Post-Fill Window"}</button>}<label className="workspace-upload"><Upload size={16} />Use Reviewed Images<input type="file" accept="image/png,image/jpeg" multiple disabled={blocked} onChange={e => void uploadFrames(e.target.files)} /></label>{frames.length > 0 && <button className="ghost-button" disabled={blocked} onClick={() => setFrames([])}>Clear</button>}</div>
          <div className="workspace-frame-grid">{[0, 1, 2].map(i => <figure key={i}>{frames[i] ? <><img src={frames[i].dataUrl} alt={`Selected post-fill frame ${i + 1}`} /><figcaption>{frames[i].label}</figcaption></> : <><div className="workspace-frame-empty">{i + 1}</div><figcaption>Post-fill frame {i + 1}</figcaption></>}</figure>)}</div>
          <p className="workspace-note">640 × 480 only. Extracted frames request +0.05, +0.15 and +0.25 seconds after the reviewed no-flow bracket. Browser seeking and camera registration must be reviewed; these are not proven settled-liquid frames.</p>
        </section>
        {mode === "recorded" && <details className="advanced-review"><summary>Advanced Review: Manual Video Guides</summary><VideoGeometry key={sourceUrl ?? "none"} media={video} currentTime={currentTime} scope={uploaded ? "uploaded" : observation.vial?.id ?? null} scopeLabel={uploaded ? uploaded.name : observation.vial?.label ?? ""} disabled={blocked || !mediaReady} onSeek={seek} /></details>}
        {error && <p className="workspace-error" role="alert">{error}</p>}
        <section className="workspace-other-models card"><h2>Other Model Workflows</h2><div><span>Cosmos</span><strong>{health?.models.some(m => m.startsWith("cosmos")) ? "Configured in Python" : "Not connected"}</strong><Link to="/analyze">Open image and prompt analysis</Link></div><div><span>Model 2</span><strong>Not integrated · validation pending</strong></div><div><span>Model 3</span><strong>Not integrated</strong></div></section>
      </div>
      <Model4Panel key={sourceKey} initialVial={mode === "recorded" ? selectedVial?.label ?? "" : ""} frames={frames} health={health} refresh={refresh} busy={busy} onBusy={setBusy} />
    </div>
  </>;
}
