import { useEffect, useState } from "react";
import { readResponse, tanks, type Recipe } from "../inspection/types";
import type { WorkflowStatus } from "../inspection/recipeWorkflow";

import { ObservedRecipeBank } from "../components/ObservedRecipeBank";

type Reference = Recipe & { expected_order: string[] };
type Catalog = { source: string; recipes: Reference[] };
type Candidate = { id: number; final_color: string; dispense_count: number; dispenses: { color: string; duration_seconds: number; source: string | null }[] };
export function RecipesPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null), [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [referenceError, setReferenceError] = useState(""), [candidateError, setCandidateError] = useState("");
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [query, setQuery] = useState(""), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const abort = new AbortController(); setReferenceError(""); setCandidateError(""); setCandidates(null); setCatalog(null); setWorkflow(null);
    fetch("/api/recipe-library/references", { signal: abort.signal }).then(readResponse<Catalog>).then(setCatalog).catch(e => { if (e.name !== "AbortError") setReferenceError(e.message); });
    fetch("/api/recipe-library/candidates", { signal: abort.signal }).then(readResponse<{ recipes: Candidate[] }>).then(b => setCandidates(b.recipes)).catch(e => { if (e.name !== "AbortError") setCandidateError(e.message); });
    fetch("/api/recipe-workflow/status", { signal: abort.signal }).then(readResponse<WorkflowStatus>).then(setWorkflow).catch(() => {});
    return () => abort.abort();
  }, [refresh]);
  const filtered = catalog?.recipes.filter(r => !query.trim() || String(r.recipe_id).includes(query.trim()));
  return <>
    <div className="page-heading"><div><p className="eyebrow">Recipe Settings and Observed Patterns</p><h1>Recipe Library</h1><p>Documented reference settings and unmatched observations awaiting review.</p></div><button className="ghost-button" onClick={() => setRefresh(n => n + 1)}>Refresh Recipes</button></div>
    <nav className="overview-links library-nav" aria-label="Recipe Sections"><a href="#reference-recipes">Reference Recipes{catalog ? ` (${catalog.recipes.length})` : ""}</a><a href="#observed-patterns">Discovered Recipes</a><a href="#candidate-recipes">Unmatched Candidates{candidates ? ` (${candidates.length})` : ""}</a></nav>
    <section className="card integration-card library-section" aria-labelledby="reference-recipes">
      <div className="card__header"><div><h2 id="reference-recipes">Reference Recipes</h2><p>{catalog ? `${catalog.recipes.length} recipes · ${catalog.source}` : referenceError ? "Reference settings unavailable" : "Loading reference settings…"}</p></div><label>Find Recipe<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Recipe number" /></label></div>
      <p className="callout">These are documented dosing settings, not independently verified liquid compositions or measured delivery. Model 4 compares against a reference you select; it does not identify a recipe.</p>
      {workflow && <div className="reference-coverage"><h3>Earlier Review Reference Coverage</h3><p>{workflow.coverage.comparable_reference_count}/{workflow.coverage.nominal_reference_count} nominal recipes have patterns in the earlier reviewed-evidence service. Automatic recorded processing uses the experimental comparison bank below.</p><details><summary>Missing Comparison References</summary><p>{workflow.coverage.missing_reference_ids.length ? workflow.coverage.missing_reference_ids.join(", ") : "All nominal references have observation patterns."}</p></details></div>}
      {referenceError && <p role="alert" className="integration-error">{referenceError}</p>}
      {filtered?.length === 0 && <p role="status">No reference recipe matches this search.</p>}
      <div className="recipe-grid">{filtered?.map(r => <article className="recipe-tile library-recipe" key={r.recipe_id}>
        <div className="card__header"><h3>Recipe {r.recipe_id}</h3><strong>{r.total_ml} mL Nominal</strong></div>
        <div className="library-composition" aria-label={`Recipe ${r.recipe_id} nominal proportions`}>{tanks.map(t => <span key={t} className={`tank-${t}`} style={{ width: `${r.proportions[t] * 100}%` }} />)}</div>
        <dl className="definition-list">{tanks.map(t => <div key={t}><dt>{t}</dt><dd>{r.amounts_ml[t]} mL</dd></div>)}<div><dt>Dispense Order</dt><dd>{r.expected_order.join(" → ") || "Not documented"}</dd></div></dl>
      </article>)}</div>
    </section>
    <ObservedRecipeBank revision={refresh} />
    <section className="card integration-card library-section" aria-labelledby="candidate-recipes"><h2 id="candidate-recipes">Unmatched Recipe Candidates</h2>
      <p>Observed patterns retained by the matching service for review. No match does not establish a new recipe or a physical defect. Model 4 comparisons do not automatically create candidates.</p>
      <p className="callout">{workflow?.persistence === "sqlite" ? "Candidates and recipe assessments are saved locally and survive service restarts when the storage file is preserved." : workflow?.persistence === "in_memory" ? "This service uses temporary memory; records are lost on restart." : "Persistent storage status is unavailable; check the assessment service before relying on saved candidates."} This collection is separate from the nominal reference bank. This collection belongs to the earlier reviewed-evidence workflow. Automatic recorded processing saves patterns in the experimental bank above.</p>
      {candidateError ? <p role="alert" className="integration-error">{candidateError}</p> : candidates === null ? <p role="status">Loading candidate records…</p> : !candidates.length ? <div className="quiet-state">No unmatched candidates have been recorded by the connected service.</div> : <div className="recipe-grid">{candidates.map(c => <article className="recipe-tile library-recipe" key={c.id}><h3>Candidate {c.id}</h3><p>Awaiting Review · Final Color: {c.final_color}</p><ol>{c.dispenses.map((d, i) => <li key={i}>{d.color} · {d.duration_seconds} seconds{d.source ? ` · ${d.source}` : ""}</li>)}</ol><p>{c.dispense_count} observed dispenses · material quantities not established.</p></article>)}</div>}
    </section>
  </>;
}
