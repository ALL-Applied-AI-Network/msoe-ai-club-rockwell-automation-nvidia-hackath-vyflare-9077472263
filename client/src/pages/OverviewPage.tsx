import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { readResponse, type Health, type RecordedVideo } from "../inspection/types";
import type { WorkflowStatus } from "../inspection/recipeWorkflow";

export function OverviewPage() {
  const [health, setHealth] = useState<Health | null>(null), [videos, setVideos] = useState<RecordedVideo[] | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [references, setReferences] = useState<number | null>(null), [errors, setErrors] = useState<string[]>([]), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const abort = new AbortController(); setErrors([]); setHealth(null); setVideos(null); setReferences(null); setWorkflow(null);
    const fail = (e: Error) => { if (e.name !== "AbortError") setErrors(a => [...a, e.message]); };
    fetch("/api/inference/status", { signal: abort.signal }).then(readResponse<Health>).then(setHealth).catch(fail);
    fetch("/api/inspection/evidence", { signal: abort.signal }).then(readResponse<{ videos: RecordedVideo[] }>).then(b => setVideos(b.videos)).catch(fail);
    fetch("/api/recipe-library/references", { signal: abort.signal }).then(readResponse<{ recipes: unknown[] }>).then(b => setReferences(b.recipes.length)).catch(fail);
    fetch("/api/recipe-workflow/status", { signal: abort.signal }).then(readResponse<WorkflowStatus>).then(setWorkflow).catch(fail);
    return () => abort.abort();
  }, [refresh]);
  const modelStatus = (match: (m: string) => boolean) => !health ? "Checking Connection" : !health.available ? "Backend Unavailable" : !health.models.some(match) ? "Not Connected" : health.mode === "mock" ? "Mock Mode — No Inference" : "Configured";
  const metrics = [
    ["Recorded Sources Installed", videos ? `${videos.filter(v => v.available).length} / ${videos.length}` : "—"],
    ["Reviewed Fill Sequences", videos ? videos.reduce((n, v) => n + v.vials.length, 0) : "—"],
    ["Reference Recipes", references ?? "—"],
    ["Saved Recipe Assessments", workflow?.saved_assessment_count ?? "—"]
  ];
  return <>
    <div className="page-heading"><div><p className="eyebrow">Evidence to Mixture Review</p><h1>Solution Overview</h1><p>The current inspection workflow, available evidence, and model connections.</p></div><button className="ghost-button" onClick={() => setRefresh(n => n + 1)}>Refresh Overview</button></div>
    {errors.map((e, i) => <p role="alert" className="integration-error" key={i}>{e}</p>)}
    <div className="metric-grid">{metrics.map(([label, value]) => <article className="card integration-card" key={label}><span>{label}</span><h2>{value}</h2></article>)}</div>
    <section className="card integration-card overview-workflow"><h2>Inspection Workflow</h2><ol className="solution-steps">
      <li><strong>Select Evidence</strong><p>Review recorded video or connect a live camera preview.</p></li>
      <li><strong>Review the Vial</strong><p>Use reviewed dispense times and assess recipe evidence; manual geometry remains optional.</p></li>
      <li><strong>Select Three Frames</strong><p>Confirm the same vial, post-fill timing, and calibrated camera view.</p></li>
      <li><strong>Compare with Model 4</strong><p>Choose a reference and enter reliable batch context.</p></li>
      <li><strong>Review the Result</strong><p>Inspect estimated proportions, reference differences, and first-vial flags.</p></li>
    </ol><Link className="workflow-link" to="/inspect">Open Inspection Workspace →</Link></section>
    <div className="integration-grid"><section className="card integration-card"><h2>Evidence Modes</h2>
      <h3>Recorded Video</h3><p>Playback, reviewed event overlays, manual guide keyframes, and post-fill frame extraction. Video recipes remain unknown unless independently established.</p>
      {videos?.map(v => <p key={v.id}>{v.name} · {v.vials.length} reviewed fill sequences · {v.available ? "Source installed" : "Source missing"}</p>)}
      <h3>Live Camera</h3><p>Camera selection and preview are available. Automatic vial tracking, fill-end detection, and live capture still need their processing adapters.</p>
    </section><section className="card integration-card"><h2>Model Connections</h2>
      <dl className="definition-list"><div><dt>Model 4</dt><dd>{modelStatus(m => m === "model4")}</dd></div><div><dt>Cosmos</dt><dd>{modelStatus(m => m.startsWith("cosmos"))}</dd></div><div><dt>Model 2</dt><dd>{modelStatus(m => m === "model2")} · Experimental</dd></div><div><dt>Model 3</dt><dd>Role Pending · Not Integrated</dd></div></dl>
      <p>Model 4 estimates mixture proportions. Cosmos provides prompted visual descriptions when connected. Configured status does not guarantee remote GPU readiness.</p><Link className="workflow-link" to="/analyze">Open Image and Prompt Analysis →</Link>
    </section></div>
    <section className="card integration-card overview-workflow"><h2>Results and Recipe Review</h2><p>Recipe assessments retain source evidence and matching outcomes in the connected storage service. Missing observation references remain Insufficient Evidence. Model 4 mixture-comparison results are still shown only in the workspace. These records are advisory, not production pass-rate statistics; the system does not release vials or control equipment.</p>{workflow && <p>Comparable timing/color reference patterns: {workflow.coverage.comparable_reference_count}/{workflow.coverage.nominal_reference_count}.</p>}<div className="overview-links"><Link to="/recipes">Reference Recipes and Unmatched Candidates →</Link><Link to="/experiments">Saved Experiments →</Link><Link to="/inspection">Separate Simulated Demo Cases →</Link></div></section>
  </>;
}
