import { useCallback, useEffect, useRef, useState } from "react";
import { readResponse } from "./types";
export type Coverage = { nominal_reference_count: number; comparable_reference_count: number; missing_reference_ids: number[]; reference_pattern_ids: number[]; required_fields: string[]; note: string };
export type WorkflowStatus = { coverage: Coverage; persistence: "sqlite" | "in_memory"; saved_assessment_count: number; catalog_sha256: string };
export type RecipeAssessment = {
  inspection_id: string; assessment_status: "MATCHED" | "UNMATCHED_CANDIDATE" | "INSUFFICIENT_EVIDENCE";
  recipe_id: number | null; created_new_recipe: boolean; inspected_at: string; requires_reassessment: boolean;
  evidence: { vial_id?: string; video_id?: string; revision?: string; source_observation?: unknown; limitations?: string[] };
  coverage: Coverage; persistence: "sqlite" | "in_memory";
  intended_comparison: { reasons: string[] }; unmatched_comparison: { reasons: string[] } | null;
};
export function assessmentLabel(value?: RecipeAssessment) {
  if (!value) return "Not Yet Assessed";
  if (value.requires_reassessment) return "Reassessment Needed";
  if (value.assessment_status === "MATCHED") return `Matched Reference Recipe ${value.recipe_id}`;
  if (value.assessment_status === "UNMATCHED_CANDIDATE") return `Unmatched Candidate ${value.recipe_id}`;
  return "Insufficient Evidence";
}
export function useRecipeWorkflow(videoId?: string) {
  const [assessments, setAssessments] = useState<Record<string, RecipeAssessment>>({});
  const [status, setStatus] = useState<WorkflowStatus | null>(null), [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(""), [pendingCount, setPendingCount] = useState(0), [refresh, setRefresh] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const pending = useRef(new Map<string, Promise<RecipeAssessment | null>>());
  useEffect(() => {
    const abort = new AbortController(); abortRef.current = abort; pending.current.clear();
    setPendingCount(0); setAssessments({}); setStatus(null); setError(""); setLoaded(false);
    if (videoId) {
      Promise.all([
        fetch("/api/recipe-workflow/status", { signal: abort.signal }).then(readResponse<WorkflowStatus>),
        fetch(`/api/recipe-workflow/videos/${encodeURIComponent(videoId)}/assessments`, { signal: abort.signal }).then(readResponse<{ assessments: RecipeAssessment[] }>)
      ]).then(([next, saved]) => {
        setStatus(next); setAssessments(previous => ({ ...Object.fromEntries(saved.assessments.filter(a => a.evidence.vial_id).map(a => [a.evidence.vial_id!, a])), ...previous })); setLoaded(true);
      }).catch(e => { if (e.name !== "AbortError") setError(e.message); });
    }
    return () => abort.abort();
  }, [videoId, refresh]);
  const assess = useCallback((vialId: string): Promise<RecipeAssessment | null> => {
    const abort = abortRef.current;
    if (!videoId || !abort || abort.signal.aborted) return Promise.resolve(null);
    const existing = pending.current.get(vialId); if (existing) return existing;
    setError(""); setPendingCount(n => n + 1);
    const promise = fetch(`/api/recipe-workflow/recorded/${encodeURIComponent(videoId)}/${encodeURIComponent(vialId)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal: abort.signal
    }).then(readResponse<{ assessment: RecipeAssessment }>).then(body => {
      if (abort.signal.aborted) return null;
      setAssessments(values => ({ ...values, [vialId]: body.assessment }));
      setStatus(value => value ? { ...value, coverage: body.assessment.coverage } : value);
      return body.assessment;
    }).catch(e => { if (e.name !== "AbortError") setError(e.message); return null; })
      .finally(() => { if (!abort.signal.aborted) { pending.current.delete(vialId); setPendingCount(n => n - 1); } });
    pending.current.set(vialId, promise); return promise;
  }, [videoId]);
  return { assessments, status, loaded, error, busy: pendingCount > 0, assess, reload: () => setRefresh(n => n + 1) };
}
