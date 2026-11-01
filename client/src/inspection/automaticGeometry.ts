import { useEffect, useRef, useState, type RefObject } from "react";
import { readResponse } from "./types.js";
import type { Rectangle } from "./geometry.js";
export type Detection = { position: string; track_id: string | null; box: Rectangle; status: "CONFIRMING" | "MOVING" | "TRACKING";
  surface: { x1: number; x2: number; y1: number; y2: number } | null; surface_reason: string };
export type GeometryFrame = { captured_at: number; width: number; height: number; detections: Detection[]; issues: string[] };
export type GeometryEvidence = { observation_id: string; vial_id: string; sample_count: number; tracked_samples: number; visible_surface_samples: number; identity_continuous: boolean; track_ids: string[] };
export type GeometryRecording = { state: "idle" | "processing" | "complete" | "failed"; progress?: number; error?: string; frames: GeometryFrame[]; observations?: GeometryEvidence[] };

// No interpolation across missing evidence, a seek, a departure or a new vial.
export function geometryAt(frames: GeometryFrame[], time: number): GeometryFrame | undefined {
  let lo = 0, hi = frames.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (frames[mid].captured_at <= time + .00001) lo = mid + 1; else hi = mid; }
  const frame = frames[lo - 1];
  return frame && time - frame.captured_at <= .3 ? frame : undefined;
}

export function useAutomaticGeometry(media: RefObject<HTMLVideoElement | null>, enabled: boolean, sourceKey: string) {
  const [frame, setFrame] = useState<GeometryFrame | null>(null), [error, setError] = useState("");
  const [state, setState] = useState("Waiting for Video");
  const epoch = useRef(0);
  useEffect(() => {
    setFrame(null); setError(""); setState(enabled ? "Connecting Tracking" : "Tracking Off");
    if (!enabled) return;
    const generation = ++epoch.current;
    let disposed = false, session: string | null = null, timer = 0, last = -1, failures = 0, controller: AbortController | null = null;
    const canvas = document.createElement("canvas"); canvas.width = 640; canvas.height = 480;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    const closeSession = () => { const key = session; session = null; if (key) void fetch(`/api/geometry/sessions/${key}`, { method: "DELETE", keepalive: true }).catch(() => {}); };
    const reset = () => { controller?.abort(); closeSession(); last = -1; setFrame(null); setState("Resetting After Seek"); };
    const player = media.current; player?.addEventListener("seeking", reset);
    const tick = async () => {
      try {
        const video = media.current;
        if (!video || !context || video.readyState < 2 || video.seeking) { setState("Waiting for Video"); return; }
        if (video.videoWidth !== 640 || video.videoHeight !== 480) { setFrame(null); setError("Automatic tracking requires the original 640 × 480 station view. This image is not resized."); setState("Unsupported Camera View"); return; }
        const time = video.currentTime;
        if (time === last) return;
        if (time < last || (last >= 0 && time - last > .4)) { closeSession(); setFrame(null); }
        controller = new AbortController(); const signal = controller.signal;
        if (!session) {
          const body = await fetch("/api/geometry/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal: AbortSignal.timeout(10000) }).then(readResponse<{ session_id: string }>);
          if (disposed || signal.aborted) { void fetch(`/api/geometry/sessions/${body.session_id}`, { method: "DELETE", keepalive: true }); return; }
          session = body.session_id;
        }
        context.drawImage(video, 0, 0);
        const next = await fetch(`/api/geometry/sessions/${session}/frame`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image: canvas.toDataURL("image/jpeg", .92), captured_at: time }), signal }).then(readResponse<GeometryFrame>);
        if (disposed || signal.aborted || epoch.current !== generation) return;
        last = time; failures = 0; setFrame(next); setError(""); setState(next.detections.some(d => d.status === "TRACKING") ? "Automatic Tracking Active" : next.detections.length ? "Confirming Vial Position" : "No Supported Vial Visible");
      } catch (e) {
        if (!disposed && !(e instanceof Error && e.name === "AbortError")) { setFrame(null); setError(e instanceof Error ? e.message : "Tracking failed"); setState("Tracking Unavailable"); failures++; closeSession(); }
      } finally { if (!disposed) timer = window.setTimeout(() => void tick(), failures ? Math.min(5000, 1000 * failures) : 200); }
    };
    void tick();
    return () => { disposed = true; epoch.current++; window.clearTimeout(timer); controller?.abort(); closeSession(); player?.removeEventListener("seeking", reset); };
  }, [enabled, sourceKey, media]);
  return { frame, error, state };
}

export function useRecordedGeometry(videoId: string | undefined, observerState?: string) {
  const [job, setJob] = useState<GeometryRecording | null>(null), [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    setJob(null); setError(""); if (!videoId) return;
    const abort = new AbortController(); let timer = 0;
    const poll = async () => {
      try {
        const next = await fetch(`/api/geometry/recordings/${videoId}`, { signal: abort.signal }).then(readResponse<GeometryRecording>);
        if (abort.signal.aborted) return;
        setJob(next); if (next.state === "processing") timer = window.setTimeout(() => void poll(), 1500);
      } catch (e) { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : "Recording tracking unavailable"); }
    };
    void poll(); return () => { abort.abort(); window.clearTimeout(timer); };
  }, [videoId, refresh, observerState]);
  const start = async () => {
    if (!videoId) return;
    try {
      await fetch(`/api/geometry/recordings/${videoId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(readResponse<GeometryRecording>);
      setRefresh(n => n + 1);
    } catch (e) { setError(e instanceof Error ? e.message : "Recording tracking unavailable"); }
  };
  return { job, error, start, reload: () => setRefresh(n => n + 1) };
}
