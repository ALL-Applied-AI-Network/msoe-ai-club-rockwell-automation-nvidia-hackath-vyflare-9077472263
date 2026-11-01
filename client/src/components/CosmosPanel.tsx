import { useEffect, useRef, useState, type RefObject } from "react";
import { cosmosMethods, validateCosmosResponse, type CosmosResponse } from "../inspection/cosmos";
import { readResponse, timeLabel, type Health } from "../inspection/types";

type Snapshot = { id: string; dataUrl: string; sha256: string; seconds: number; width: number; height: number; source: string };
export function CosmosPanel({ media, sourceLabel, health, mediaReady, disabled, refresh }: {
  media: RefObject<HTMLVideoElement | null>; sourceLabel: string; health: Health | null; mediaReady: boolean; disabled: boolean; refresh: () => void;
}) {
  const models = (health?.models ?? []).filter(m => !!cosmosMethods[m]);
  const [model, setModel] = useState("");
  const selected = models.includes(model) ? model : models.includes("cosmos_full") ? "cosmos_full" : models[0] ?? "";
  const [prompt, setPrompt] = useState("Describe the visible vial and liquid appearance. State any obstruction or uncertainty. Do not infer a recipe, ingredients, physical volume, or events outside this single frame.");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null), [result, setResult] = useState<CosmosResponse | null>(null);
  const [submittedPrompt, setSubmittedPrompt] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null), generation = useRef(0);
  useEffect(() => () => { generation.current++; request.current?.abort(); }, []);
  const capture = async () => {
    const player = media.current; if (!player || player.readyState < 2) { setError("Wait for a decoded video frame."); return; }
    setError(""); setResult(null); setSnapshot(null); const id = ++generation.current;
    try {
      player.pause(); const seconds = player.currentTime, width = player.videoWidth, height = player.videoHeight;
      if (!width || !height || width * height > 16_000_000 || !Number.isFinite(seconds)) throw new Error("This video frame cannot be captured.");
      const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
      const context = canvas.getContext("2d"); if (!context) throw new Error("Frame capture is unavailable.");
      context.drawImage(player, 0, 0); // Capture source pixels, excluding all UI overlays.
      const dataUrl = canvas.toDataURL("image/png"), bytes = Uint8Array.from(atob(dataUrl.split(",")[1]), c => c.charCodeAt(0));
      if (bytes.length > 4 * 1024 * 1024) throw new Error("Captured frame exceeds 4 MiB. Use a smaller source video.");
      const hash = await crypto.subtle.digest("SHA-256", bytes);
      if (id !== generation.current) return;
      setSnapshot({ id: crypto.randomUUID(), dataUrl, sha256: Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, "0")).join(""), seconds, width, height, source: sourceLabel });
    } catch (e) { if (id === generation.current) setError(e instanceof Error ? e.message : "Frame capture failed."); }
  };
  const analyze = async () => {
    if (!snapshot || !selected) return;
    const evidence = snapshot, question = prompt.trim(), route = selected, id = ++generation.current;
    const abort = new AbortController(); request.current = abort; setBusy(true); setError(""); setResult(null);
    try {
      const response = await fetch("/api/inference/predict", { method: "POST", signal: abort.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: evidence.dataUrl, frame_id: evidence.id, model: route, prompt: question }) });
      const body = await readResponse<unknown>(response);
      const observation = validateCosmosResponse(body, evidence.id, route);
      if (id !== generation.current) return;
      setSubmittedPrompt(question); setResult(observation);
    } catch (e) { if (id === generation.current) setError(e instanceof Error && e.name === "AbortError" ? "Request cancelled. The GPU may still be finishing the request." : e instanceof Error ? e.message : "Cosmos request failed."); }
    finally { if (id === generation.current) setBusy(false); }
  };
  return <section className="card integration-card" aria-label="Cosmos Recorded Frame Analysis">
    <div className="card__header"><div><p className="eyebrow">Prompted Visual Observation</p><h2>Ask Cosmos About a Frame</h2></div><button className="ghost-button" disabled={busy} onClick={refresh}>Refresh Cosmos Connection</button></div>
    <p role="status">{!health?.available ? "Python connection unavailable." : health.mode === "mock" ? "Mock mode — no Cosmos inference." : !selected ? "Cosmos is not configured. Connect the GPU worker to test." : "Cosmos route configured. GPU readiness is verified by a successful request."}</p>
    <p>Pause at the evidence you want, capture a clean frame, then enter a prompt. This analyzes one still image, not the video sequence. Photo analysis with the fine-tuned adapter is experimental; it was trained on videos. Descriptions do not assign recipes or update the recipe bank.</p>
    <button className="ghost-button" disabled={busy || disabled || !mediaReady} onClick={() => void capture()}>Capture Current Frame for Cosmos</button>
    {snapshot && <><img className="experiment-image" src={snapshot.dataUrl} alt={`Cosmos evidence from ${snapshot.source} at ${timeLabel(snapshot.seconds)}`} /><p>{snapshot.source} · Captured at {timeLabel(snapshot.seconds)} · {snapshot.width} × {snapshot.height}</p></>}
    <label>Cosmos Route<select aria-label="Cosmos Route" disabled={busy || !models.length} value={selected} onChange={e => { setModel(e.target.value); setResult(null); }}>{!models.length && <option value="">No Cosmos Route Configured</option>}{models.map(m => <option key={m} value={m}>{cosmosMethods[m]}</option>)}</select></label>
    <label>Cosmos Prompt<textarea aria-label="Cosmos Prompt" maxLength={2000} value={prompt} disabled={busy} onChange={e => { setPrompt(e.target.value); setResult(null); }} /></label>
    <button className="primary-action" disabled={busy || disabled || !snapshot || !selected || !health?.available || health.mode !== "real" || !prompt.trim()} onClick={() => void analyze()}>{busy ? "Asking Cosmos…" : "Ask Cosmos"}</button>
    {busy && <button className="ghost-button" onClick={() => request.current?.abort()}>Cancel Cosmos Request</button>}
    {error && <p role="alert">{error}</p>}
    {result && snapshot && <section aria-label="Cosmos Observation" aria-live="polite"><h3>Cosmos Observation</h3><p>{result.result.implementation === "cosmos3-nano-vial-lora" ? "Fine-Tuned Cosmos3-Nano · Experimental Still-Frame Use" : "Worker implementation: " + (result.result.implementation ?? "Not reported")}</p><p className="model-observation">{result.result.text}</p><p>{cosmosMethods[result.model]} · {result.inference_ms} ms · Source frame {timeLabel(snapshot.seconds)}</p><p>Visual description only · Recipe decisions unchanged</p>{result.result.safety?.status === "not_provided_by_this_lora_worker" && <p>Content screening is not provided by this LoRA worker.</p>}
      <details><summary>Cosmos Evidence and Execution</summary><p>Prompt: {submittedPrompt}</p><p>Frame SHA-256: {snapshot.sha256}</p><p>Browser playback time is the capture position, not a validated source presentation timestamp.</p><p>The inference service may resize or re-encode the frame for the model; the hash identifies the captured upload.</p><pre className="result-json">{JSON.stringify({ frame_id: result.frame_id, implementation: result.result.implementation, model_identity: result.result.model_identity, execution: result.result.execution, safety: result.result.safety, prompt_applied: result.result.prompt_applied, worker_input_sha256: result.result.image_sha256, task_scope: result.result.task_scope, integration_reference: result.result.integration_reference }, null, 2)}</pre></details></section>}
  </section>;
}
