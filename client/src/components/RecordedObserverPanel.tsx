import { detectedRecipeLabel, effectiveRecipeId, type useRecordedObserver } from "../inspection/recordedObserver";
import { timeLabel } from "../inspection/types";
export function RecordedObserverPanel({ observer, name, onSeek }: {
  observer: ReturnType<typeof useRecordedObserver>; name: string; onSeek: (time: number) => void;
}) {
  const { job, status, error, busy, start, reload } = observer;
  return <section className="card integration-card" aria-label="Automatic Recorded Observation">
    <div className="card__header"><div><p className="eyebrow">Recorded Video · Experimental</p><h2>Automatic Fill and Recipe Observation</h2></div><button className="ghost-button" disabled={busy} onClick={reload}>Refresh Results</button></div>
    <p>Process {name} to detect fill visits and dispense intervals, sample final appearance, and create or reuse observed recipe patterns.</p>
    <p>Fixed 640 × 480 camera view only. Discovered recipes are unverified patterns; timing and color do not identify chemical composition. Boundary matches remain unresolved and conflicting colors receive a review flag.</p>
    {status && !status.enabled && <p role="status" className="callout">Recorded processing is disabled. Enable the backend demonstration with a separate recipe database and inference token.</p>}
    {status?.enabled && !status.available && <p role="status" className="callout">{status.reason}</p>}
    <button className="primary-action" disabled={!status?.enabled || !status.available || busy} onClick={() => void start()}>{busy ? "Processing Recording…" : job?.assessments.length ? "Reprocess Recording" : "Process Recording"}</button>
    <p className="workspace-note">Processing runs independently of playback. Replay reads saved results; reprocessing uses fresh video frames and reuses unchanged assessments.</p>
    {busy && <div role="status"><p>{job?.stage ?? "Starting"} · {job?.progress ?? 0}%</p><progress max={100} value={job?.progress ?? 0} aria-label="Recording Processing Progress" /></div>}
    {job?.state === "completed" && <p role="status">Processing Complete · Fresh Video Observations Saved</p>}
    {(error || job?.error) && <p role="alert" className="integration-error">{error || job?.error}</p>}
    {job && <p role="status">{job.assessments.length} saved fill assessments · {job.assessments.filter(a => effectiveRecipeId(a) !== null).length} recipe links · {job.assessments.filter(a => effectiveRecipeId(a) === null).length} unresolved{job.assessments.some(a => a.pattern_membership?.status === "PENDING_REPEAT") ? ` (${job.assessments.filter(a => a.pattern_membership?.status === "PENDING_REPEAT").length} pending repeat)` : ""}{job.held_visits?.length ? ` · ${job.held_visits.length} incomplete visits held` : ""}{busy && job.assessments.length > 0 ? " · Previous saved results remain visible during processing" : ""}</p>}
    {job?.assessments.map(a => <article className="detected-fill" key={a.observation_id}>
      <div className="card__header"><h3>{a.observation.label}</h3><button className="ghost-button" onClick={() => onSeek(Math.max(0, a.observation.source_episode_intervals[0].start[0] - 1))}>View Fill</button></div>
      <strong>{detectedRecipeLabel(a)}</strong>
      <p>{a.observation.duration_bounds_seconds.map((b, i) => `Dispense ${i + 1}: ${b[0].toFixed(2)}–${b[1].toFixed(2)} s`).join(" · ")}</p>
      <p>First dispense: {timeLabel(a.observation.source_episode_intervals[0].start[0])} · Reference color comparison: {a.color.status === "NOT_EVALUATED" ? "no compatible reference" : a.color.status.toLowerCase().replaceAll("_", " ")}</p>
      {effectiveRecipeId(a) === null && <p>{a.reason.replaceAll("_", " ").toLowerCase()}{a.hold_reasons.length ? ` · ${a.hold_reasons.join(", ").replaceAll("_", " ").toLowerCase()}` : ""}</p>}
      {a.timing.possible_recipe_ids.length > 0 && effectiveRecipeId(a) === null && <p>Possible patterns: {a.timing.possible_recipe_ids.join(", ")} · No identity assigned</p>}
      {a.pattern_membership && <div className="membership-status">
        <p>Color Conflict Review · Original Timing Candidates: {a.pattern_membership.baseline_timing_candidate_ids.join(", ") || "None"}. Nominal identity remains unconfirmed.</p>
        <p>{a.pattern_membership.status === "DISCOVERED_UNVERIFIED" ? "Two distinct qualifying fills support this observed pattern. Earlier assessments are preserved." : a.pattern_membership.status === "PENDING_REPEAT" ? "A second distinct qualifying fill is required before a recipe ID is created. Replaying this fill does not count again." : "No new recipe ID was assigned by the pattern workflow."}</p>
        <details><summary>Pattern Membership History</summary><ol>{a.pattern_membership.history.map(r => <li key={r.revision_id}>Revision {r.revision_id}: {r.status === "PENDING_REPEAT" ? "Pending Repeat" : r.status === "DISCOVERED_UNVERIFIED" ? "Discovered · Unverified" : r.status.replaceAll("_", " ")} · {r.event.replaceAll("_", " ").toLowerCase()}</li>)}</ol></details>
      </div>}
      <details><summary>Observation Evidence</summary><pre className="result-json">{JSON.stringify(a, null, 2)}</pre></details>
    </article>)}
    {job?.held_visits?.map(v => <p key={v.label}>{v.label}: Unresolved · {v.hold_reasons.join(", ").replaceAll("_", " ").toLowerCase()}</p>)}
    {job && !busy && !job.assessments.length && !job.held_visits?.length && job.state !== "failed" && <p>No automatic fill results have been saved for this recording.</p>}
  </section>;
}
