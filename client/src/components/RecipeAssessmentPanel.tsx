import { useState } from "react";
import { Link } from "react-router-dom";
import { assessmentLabel, type RecipeAssessment, type WorkflowStatus } from "../inspection/recipeWorkflow";
import { timeLabel, type Vial } from "../inspection/types";

export function RecipeAssessmentPanel({ selected, vials, assessment, status, loaded, busy, error, assess, reload, auto, onAuto }: {
  selected: Vial; vials: Vial[]; assessment?: RecipeAssessment; status: WorkflowStatus | null; loaded: boolean; busy: boolean; error: string;
  assess: (vial: string) => Promise<RecipeAssessment | null>; reload: () => void; auto: boolean; onAuto: (value: boolean) => void;
}) {
  const [batch, setBatch] = useState(false), [processed, setProcessed] = useState(0);
  const assessAll = async () => {
    setBatch(true); setProcessed(0);
    try { for (const vial of vials) { if (!await assess(vial.id)) break; setProcessed(n => n + 1); } }
    finally { setBatch(false); }
  };
  return <section className="card integration-card recipe-assessment" aria-label="Recipe Assessment">
    <div className="card__header"><div><p className="eyebrow">Observation Pattern Matching</p><h2>Recipe Assessment</h2></div><button className="ghost-button" disabled={busy || batch} onClick={reload}>Refresh Saved Assessments</button></div>
    <p>{selected.label} · Reviewed final sample: {timeLabel(selected.finalSampleSeconds)}</p>
    <p className="recipe-assessment-status" role="status">{loaded ? assessmentLabel(assessment) : error ? "Assessment Service Unavailable" : "Loading Saved Assessment…"}</p>
    <p>The reviewed dispense observations are checked against available timing and color reference patterns. Model 4's selected-recipe mixture comparison remains a separate analysis.</p>
    <label className="inline-check"><input type="checkbox" checked={auto} onChange={e => onAuto(e.target.checked)} />Assess Reviewed Fills at Their Final Sample</label>
    <div className="geometry-actions"><button className="primary-action" disabled={!loaded || busy || batch} onClick={() => void assess(selected.id)}>Assess Selected Vial</button><button className="ghost-button" disabled={!loaded || busy || batch} onClick={() => void assessAll()}>{batch ? `Assessing ${processed}/${vials.length}…` : "Assess All Reviewed Vials"}</button></div>
    {batch && <p role="status">Assessments are saved individually. Repeating this action reuses results for unchanged evidence and references.</p>}
    {!batch && processed > 0 && <p role="status">{processed} reviewed vials assessed. Select a vial to view its saved result.</p>}
    {error && <p role="alert" className="integration-error">{error}</p>}
    {status && <p className="callout">Comparable timing/color references: {status.coverage.comparable_reference_count}/{status.coverage.nominal_reference_count}. Nominal amounts and tank order alone cannot establish a recipe match or a new recipe.</p>}
    {assessment && <>
      {assessment.requires_reassessment && <p className="workspace-warning">Reference patterns or matching settings changed. Reassess this vial to create a new result; the old record remains in history.</p>}
      {assessment.assessment_status === "INSUFFICIENT_EVIDENCE" && <><h3>Evidence Needed</h3><ul>{assessment.intended_comparison.reasons.map(r => <li key={r}>{r === "Completed filling, dispenses, and final color are required" ? "The sampled review does not provide complete, verified ingredient-dispense measurements." : r.replaceAll("NO_MATCH", "a confirmed non-match")}</li>)}{assessment.evidence.limitations?.map(r => <li key={r}>{r}</li>)}</ul></>}
      {assessment.assessment_status === "UNMATCHED_CANDIDATE" && <p>{assessment.created_new_recipe ? "A new unmatched candidate was saved." : "This observation reuses an existing unmatched candidate."} The reference bank is unchanged pending review.</p>}
      {assessment.assessment_status === "MATCHED" && <p>The observed pattern matches an available intended reference. This does not verify actual composition, quality, or release.</p>}
      <p>Saved {new Date(assessment.inspected_at).toLocaleString()} · {assessment.persistence === "sqlite" ? "Persistent Local Storage" : "Temporary Memory Storage"}</p>
      <details><summary>Observation Evidence and Comparison Record</summary><pre className="result-json">{JSON.stringify(assessment, null, 2)}</pre></details>
    </>}
    <Link className="workflow-link" to="/recipes">View Reference Coverage and Unmatched Candidates →</Link>
  </section>;
}
