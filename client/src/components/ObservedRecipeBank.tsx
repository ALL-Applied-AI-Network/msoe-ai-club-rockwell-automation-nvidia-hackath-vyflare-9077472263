import { useEffect, useState } from "react";
import { readResponse } from "../inspection/types";
import type { ProducerStatus, PatternGroup } from "../inspection/recordedObserver";
type Pattern = { recipe_id: number; occurrence_count: number; profile: { duration_bounds_s: number[][]; raw_rgb: { nominal: number[] }; review_flags?: string[]; possible_baseline_recipe_ids?: number[] } };
export function ObservedRecipeBank({ revision }: { revision: number }) {
  const [groups, setGroups] = useState<PatternGroup[]>([]);
  const [coverage, setCoverage] = useState<ProducerStatus["coverage"]>();
  const [patterns, setPatterns] = useState<Pattern[]>([]), [enabled, setEnabled] = useState<boolean | null>(null), [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController(); setEnabled(null); setCoverage(undefined); setError(""); setPatterns([]); setGroups([]);
    fetch("/api/recorded-observer/status", { signal: abort.signal }).then(readResponse<ProducerStatus>).then(async status => {
      if (abort.signal.aborted) return;
      if (status.enabled) {
        const result = await fetch("/api/recorded-observer/patterns", { signal: abort.signal }).then(readResponse<{ groups: PatternGroup[]; recipes: Pattern[] }>);
        if (abort.signal.aborted) return;
        setPatterns(result.recipes); setGroups(result.groups);
      }
      setCoverage(status.coverage); setEnabled(status.enabled);
    }).catch(e => { if (!abort.signal.aborted) setError(e.message); });
    return () => abort.abort();
  }, [revision]);
  return <section className="card integration-card library-section" aria-labelledby="observed-patterns">
    <h2 id="observed-patterns">Discovered Recipes · Experimental Bank</h2>
    <p>New observed patterns created by the demonstration workflow, including recorded-video processing. Repeated matching fills reuse the pattern ID. This separate bank includes any earlier saved demonstration patterns; these IDs do not confirm chemical composition or nominal recipe identity.</p>
    {coverage && <p>Recorded Matching References: {coverage.observed_recipe_count}/{coverage.nominal_recipe_count} nominal recipes · {coverage.observed_profile_count} observed profiles. Discovered patterns extend this comparison bank; a new pattern does not prove a chemically new recipe.</p>}
    {error ? <p role="alert" className="integration-error">{error}</p> : enabled === null ? <p role="status">Loading discovered recipes…</p> : !enabled ? <p>Experimental recipe storage is disabled on this backend.</p> : !patterns.length ? <p>No discovered patterns have been saved.</p> : <div className="recipe-grid">{patterns.map(p => <article className="recipe-tile library-recipe" key={p.recipe_id}>
      <h3>Recipe {p.recipe_id}</h3><p>Discovered · Unverified · {p.occurrence_count} Linked Fills</p>
      <ol>{p.profile.duration_bounds_s.map((b, i) => <li key={i}>Dispense {i + 1}: {b[0].toFixed(2)}–{b[1].toFixed(2)} seconds</li>)}</ol>
      {p.profile.review_flags?.includes("COLOR_CONFLICT_REVIEW") && <p className="workspace-warning">Color Conflict Review · Original Timing Candidates: {p.profile.possible_baseline_recipe_ids?.join(", ")}</p>}
      <p>Final Appearance RGB: {p.profile.raw_rgb.nominal.map(v => v.toFixed(0)).join(", ")}</p>
    </article>)}</div>}
    {enabled && <div className="pending-patterns"><h3>Pending Patterns</h3><p>Two distinct qualifying fills are required to create a recipe ID from a repeated color conflict. Existing timing, visibility and color-quality holds still apply.</p>
      {!groups.some(g => g.status === "PENDING_REPEAT") ? <p>No pending patterns are awaiting another qualifying fill.</p> : <div className="recipe-grid">{groups.filter(g => g.status === "PENDING_REPEAT").map(g => <article className="recipe-tile library-recipe" key={g.group_id}>
        <h4>{g.label}</h4><p>{g.qualifying_fill_count}/{g.required_fill_count} Qualifying Fills · No Recipe ID Assigned</p>
        <p className="workspace-warning">Color Conflict Review · Original Timing Candidates: {g.baseline_timing_candidate_ids.join(", ")}</p>
        <ul>{g.members.map(m => <li key={m.observation_key}>{m.label}</li>)}</ul>
      </article>)}</div>}
    </div>}
  </section>;
}
