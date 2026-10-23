import { ArrowLeft, ArrowRight, Beaker, ChevronRight, Database, Eye, FlaskConical, Gauge, Lightbulb, ScanLine, ShieldAlert } from "lucide-react";
import { useState } from "react";
import type { AppData } from "../../../shared/domain";
import { DecisionBadge } from "../components/DecisionBadge";
import { EvidenceViewer } from "../components/EvidenceViewer";
import { RecipeComposition } from "../components/RecipeComposition";

export function InspectionPage({ data, selectedId, onSelect }: { data: AppData; selectedId: string; onSelect: (id: string) => void }) {
  const [showOverlays, setShowOverlays] = useState(true);
  const index = Math.max(0, data.cases.findIndex((item) => item.caseId === selectedId));
  const item = data.cases[index];
  const recipe = data.recipes.find((r) => r.recipeId === item.recipeId)!;
  const previous = data.recipes.find((r) => r.recipeId === item.previousRecipeId);
  const selectAt = (next: number) => onSelect(data.cases[next].caseId);
  return <>
    <div className="page-heading"><div><p className="eyebrow">Recorded quality review</p><h1>Inspection review</h1><p>Trace the intended recipe, visual observation, and advisory decision.</p></div><span className={`review-status review-status--${item.reviewStatus.toLowerCase()}`}>{item.reviewStatus.replace("_", " ")}</span></div>
    <section className="context-toolbar" aria-label="Case context">
      <label>Station<select value="VIAL_FILL" disabled><option>Vial Fill</option></select></label>
      <label>Run<select value="VIDEO-5" disabled><option>Video 5 · labeled run</option></select></label>
      <label className="context-toolbar__case">Case<select value={item.caseId} onChange={(e) => onSelect(e.target.value)}>{data.cases.map((c) => <option key={c.caseId}>{c.caseId}</option>)}</select></label>
      <div className="context-toolbar__nav"><button onClick={() => selectAt(index - 1)} disabled={index === 0} aria-label="Previous case"><ArrowLeft /></button><span>{index + 1} / {data.cases.length}</span><button onClick={() => selectAt(index + 1)} disabled={index === data.cases.length - 1} aria-label="Next case"><ArrowRight /></button></div>
      <div className="context-toolbar__time"><span>Source timestamp</span><strong>{item.capturedAt ? new Date(item.capturedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "Unavailable"}</strong></div>
    </section>
    <div className="inspection-grid">
      <div className="inspection-grid__visual"><EvidenceViewer item={item} showOverlays={showOverlays} onToggle={() => setShowOverlays(!showOverlays)} /></div>
      <aside className="decision-panel card">
        <div className="decision-panel__top"><p className="eyebrow">Advisory decision</p><DecisionBadge decision={item.decision} large /><span className="provenance-tag">Simulated demo result</span></div>
        <h2>{item.finding}</h2>
        <div className="decision-panel__facts"><div><span>Case</span><strong>{item.caseId}</strong></div><div><span>Recipe</span><strong>{item.recipeId}</strong></div><div><span>Camera</span><strong>{item.cameraId}</strong></div></div>
        {item.qualityFlags.map((flag) => <div key={flag.code} className={`quality quality--${flag.severity.toLowerCase()}`}><ShieldAlert /><div><strong>{flag.code.replaceAll("_", " ")}</strong><span>{flag.message}</span></div></div>)}
      </aside>
      <section className="card recipe-card"><div className="card__header"><div><p className="eyebrow">Intended recipe</p><h2>Recipe {recipe.recipeId}</h2></div><Beaker /></div><RecipeComposition recipe={recipe} /><dl className="definition-list"><div><dt>Intended total</dt><dd>{recipe.totalMl} mL</dd></div><div><dt>Dispense order</dt><dd>{recipe.dispenseOrder.join(" → ")}</dd></div><div><dt>Expected appearance</dt><dd>{recipe.expectedAppearance ?? "Not documented"}</dd></div><div><dt>Previous recipe</dt><dd>{previous ? `Recipe ${previous.recipeId}` : "Not available"}</dd></div></dl><p className="source-line"><Database /> Dataset record · {recipe.source}</p></section>
      <section className="card observation-card"><div className="card__header"><div><p className="eyebrow">Observed result</p><h2>Image-relative measurement</h2></div><ScanLine /></div><div className="observation-hero"><div className="swatch" style={{ background: item.observation.colorHex ?? "var(--surface-3)" }} /><div><span>Observed color</span><strong>{item.observation.colorLabel ?? "Unavailable"}</strong></div><div className="fill-reading"><span>Liquid-height ratio</span><strong>{item.observation.fillRatio === null ? "Unavailable" : `${Math.round(item.observation.fillRatio * 100)}%`}</strong></div></div><div className="calibration"><Gauge /><p><strong>Physical volume not established</strong><span>The ratio describes liquid height inside an illustrative measurement region; it is not a volume fraction.</span></p></div><span className="provenance-tag">Simulated demo result</span></section>
    </div>
    <div className="detail-grid">
      <section className="card"><div className="card__header"><div><p className="eyebrow">Decision trace</p><h2>Supporting evidence</h2></div><Eye /></div><div className="evidence-list">{item.evidence.map((e) => <div key={e.label}><span>{e.label}</span><strong>{e.value}</strong><small>{e.source} · {e.provenance.replaceAll("_", " ").toLowerCase()}</small></div>)}</div></section>
      <section className="card"><div className="card__header"><div><p className="eyebrow">Cause analysis</p><h2>Hypotheses</h2></div><Lightbulb /></div>{item.hypotheses.length ? item.hypotheses.map((h) => <div className="hypothesis" key={h.label}><strong>{h.label}</strong><p><b>Supporting:</b> {h.supportingEvidence.join(" ")}</p><p><b>Missing:</b> {h.missingEvidence.join(" ")}</p></div>) : <div className="quiet-state">No cause hypothesis is attached to this case. Findings remain separate from root-cause analysis.</div>}</section>
      <section className="card action-card"><div className="card__header"><div><p className="eyebrow">Human next action</p><h2>Recommended review</h2></div><FlaskConical /></div><ol>{item.recommendedActions.map((action) => <li key={action}><span><ChevronRight /></span>{action}</li>)}</ol><p>Informational guidance only. No control command is available.</p></section>
    </div>
  </>;
}
