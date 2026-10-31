import { useEffect, useRef, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";
import { readResponse, tanks, type Frame, type Health, type Model4Response, type Recipe } from "../inspection/types";

export function Model4Panel({ frames, initialVial, health, refresh, busy, onBusy }: {
  frames: Frame[]; initialVial: string; health: Health | null; refresh: () => void; busy: boolean; onBusy: (value: boolean) => void;
}) {
  const [recipes, setRecipes] = useState<Recipe[]>([]), [recipeError, setRecipeError] = useState("");
  const [recipeId, setRecipeId] = useState(""), [vialId, setVialId] = useState(initialVial), [batchId, setBatchId] = useState(""), [position, setPosition] = useState("");
  const [registered, setRegistered] = useState(false), [reviewed, setReviewed] = useState(false);
  const [result, setResult] = useState<Model4Response | null>(null), [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const available = Boolean(health?.available && health.models.includes("model4"));
  useEffect(() => {
    setRecipes([]); setRecipeError("");
    if (!available) return;
    const abort = new AbortController();
    fetch("/api/inference/model4/recipes", { signal: abort.signal }).then(readResponse<{ recipes: Recipe[] }>).then(body => setRecipes(body.recipes))
      .catch(e => { if (e.name !== "AbortError") setRecipeError(e.message); });
    return () => abort.abort();
  }, [available, health]);
  useEffect(() => { setResult(null); setReviewed(false); setError(""); }, [frames]);
  useEffect(() => () => { controller.current?.abort(); }, []);
  const invalidate = () => { setResult(null); setError(""); };
  const batchPosition = Number(position);
  const ready = available && frames.length === 3 && recipes.some(r => String(r.recipe_id) === recipeId)
    && vialId.trim().length > 0 && batchId.trim().length > 0 && /^[1-9][0-9]{0,8}$/.test(position) && registered && reviewed;
  const selectedRecipe = recipes.find(r => String(r.recipe_id) === recipeId);
  const run = async () => {
    if (!ready) return;
    onBusy(true); setError(""); setResult(null); controller.current = new AbortController();
    try {
      const body = await fetch("/api/inference/model4", { method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.current.signal,
        body: JSON.stringify({ images: frames.map(f => f.dataUrl), frame_id: crypto.randomUUID(), vial_id: vialId.trim(), batch_id: batchId.trim(), batch_position: batchPosition,
          recipe_id: Number(recipeId), camera_profile: "vial-fill-640x480" }) }).then(readResponse<Model4Response>);
      setResult(body);
    } catch (e) { setError(e instanceof Error && e.name === "AbortError" ? "Request cancelled. Backend processing may still finish." : e instanceof Error ? e.message : "Analysis failed."); }
    finally { onBusy(false); }
  };
  return <aside className="workspace-analysis card" aria-label="Model 4 analysis">
    <div className="workspace-section-heading"><div><p className="eyebrow">Powered by Model 4</p><h2>Compare Vial Mixture</h2></div><button className="workspace-icon" aria-label="Refresh Model Connection" onClick={refresh} disabled={busy}><RefreshCw size={16} /></button></div>
    <p className="workspace-note">Compare three post-fill images with a recipe you choose. This panel runs when you select Run Comparison; video playback does not start analysis.</p>
    <p className="workspace-connection" role="status"><span className={`workspace-dot ${available ? "is-connected" : ""}`} />{!health ? "Checking connection…" : available ? health.mode === "mock" ? "Mock mode · no estimates" : "Model 4 connected" : "Model 4 unavailable"}</p>
    {!available && <p className="workspace-note">Connect the Python service with Model 4 enabled to load recipes and run analysis.</p>}
    <fieldset disabled={busy} className="workspace-fieldset">
      <label>Vial ID<input maxLength={128} value={vialId} onChange={e => { setVialId(e.target.value); invalidate(); }} placeholder="Tracked or reviewed vial identity" /></label>
      <div className="workspace-input-row"><label>Batch ID<input maxLength={128} value={batchId} onChange={e => { setBatchId(e.target.value); invalidate(); }} placeholder="Required" /></label><label>Position in Batch<input inputMode="numeric" value={position} onChange={e => { setPosition(e.target.value); invalidate(); }} placeholder="Unknown" /></label></div>
      <p className="workspace-note">Video order does not establish batch position. Enter reliable batch-tracking information.</p>
      <label>Comparison Recipe<select value={recipeId} disabled={!available} onChange={e => { setRecipeId(e.target.value); invalidate(); }}><option value="">Choose a recipe reference</option>{recipes.map(r => <option key={r.recipe_id} value={r.recipe_id}>Recipe {r.recipe_id} · {r.total_ml} mL nominal</option>)}</select></label>
      {selectedRecipe && <p className="workspace-note">Nominal settings: {tanks.map(t => `${t}: ${selectedRecipe.amounts_ml[t]} mL`).join(" · ")}</p>}
      <p className="workspace-note">This reference is selected by you. It is not an identified recipe or verified delivery.</p>
      {position === "1" && <p className="workspace-warning">First vial: transition-contamination review remains required regardless of mixture agreement.</p>}
      <label className="workspace-check"><input type="checkbox" checked={registered} onChange={e => { setRegistered(e.target.checked); invalidate(); }} />The camera geometry matches the calibrated 640 × 480 vial view.</label>
      <label className="workspace-check"><input type="checkbox" checked={reviewed} onChange={e => { setReviewed(e.target.checked); invalidate(); }} />All three frames show this same vial after flow ends and before movement.</label>
    </fieldset>
    {recipeError && <p className="workspace-error" role="alert">{recipeError}</p>}
    <button className="workspace-run" onClick={() => void run()} disabled={!ready || busy}>{busy ? "Analyzing three frames…" : "Run Comparison"}<ArrowRight size={16} /></button>
    {busy && <button className="ghost-button" onClick={() => controller.current?.abort()}>Cancel Request</button>}
    {error && <p className="workspace-error" role="alert">{error}</p>}
    <section className="workspace-results" aria-live="polite"><h3>Analysis Results</h3>
      {!result ? <p className="workspace-note">{busy ? "Waiting for the backend result…" : "Select three valid frames and complete the context to run a comparison."}</p> : <>
        <p className="workspace-provenance">{result.mode === "mock" || result.result.mock ? "Mock Response · no inference" : "Computed from selected frames"} · {result.inference_ms} ms</p>
        {result.result.checkpoint ? <><div className="workspace-mixture-header"><span>Tank</span><span>Reference</span><span>Estimated</span><span>Δ pp</span></div>{tanks.map(t => {
          const cp = result.result.checkpoint!; const difference = cp.signed_difference_percentage_points[t];
          return <div className="workspace-mixture" key={t}><strong>{t}</strong><span>{(result.result.expected.proportions[t] * 100).toFixed(1)}%</span><span>{cp.estimated_percentages[t].toFixed(1)}%</span><span>{difference > 0 ? "+" : ""}{difference.toFixed(1)}</span></div>;
        })}<p className="workspace-note">Differences are percentage points. These estimates do not measure delivered milliliters.</p>{result.result.checkpoint.feature_extrapolation && <p className="workspace-warning">Image features are outside the checkpoint reference coverage. Review the evidence.</p>}</> : <p className="workspace-note">{result.result.message ?? "No mixture estimate was returned."}</p>}
        <p className="workspace-warning">{result.result.review.expected_transition_contamination ? "First-vial transition review required." : "Review required. No calibrated release threshold."} No automatic release.</p>
        <p className="workspace-note">{result.vial_id} · batch {result.batch_id} · position {result.batch_position}</p>
        <details><summary>Model Provenance and Response</summary><p className="workspace-note">{result.result.model_metadata.checkpoint_id}</p><pre className="result-json">{JSON.stringify(result, null, 2)}</pre></details>
      </>}
    </section>
  </aside>;
}
