import { useCallback, useEffect, useRef, useState } from "react";
import type { InspectionEvent } from "./inspectionLog";
import { readResponse } from "./types";
export type PatternMembership = {
  group_id: string | null; recipe_id: number | null; status: string; revision_id: number;
  qualifying_fill_count: number; required_fill_count: number; review_flags: string[];
  baseline_timing_candidate_ids: number[]; history: { revision_id: number; status: string; event: string; supersedes_revision_id: number | null }[];
};
export type PatternGroup = {
  group_id: string; label: string; recipe_id: number | null; status: string; qualifying_fill_count: number; required_fill_count: number;
  review_flags: string[]; baseline_timing_candidate_ids: number[];
  members: { label: string; observation_key: string }[];
};
export type DetectedAssessment = {
  recorded_tracking?: { status: "HELD" | "SUPPORTED" | "SUPPORTED_WITH_RECOVERY"; track_id: string | null; hold_reasons: string[]; numeric_surface_used: false };
  pattern_membership?: PatternMembership;
  observation_id: string; action: string; recipe_id: number | null; reason: string; hold_reasons: string[];
  timing: { possible_recipe_ids: number[] }; color: { status: string };
  observation: { label: string; video_id: string; vial_id: string; source_kind: string;
    source_episode_intervals: { start: number[]; end: number[] }[];
    duration_bounds_seconds: number[][]; departure_interval_seconds: number[] | null;
    candidate_appearance_window_seconds: number[] | null; raw_rgb: { nominal: number[] } | null };
};
export type ProducerJob = { state: "idle" | "queued" | "processing" | "completed" | "saved" | "failed";
  events?: InspectionEvent[]; analyzed_through_seconds?: number; source_sha256?: string;
  stage?: string; progress: number; error?: string; detected_fill_count?: number;
  held_visits?: { label: string; hold_reasons: string[] }[]; assessments: DetectedAssessment[] };
export type ProducerStatus = { enabled: boolean; available: boolean; reason: string | null; coverage?: { nominal_recipe_count: number; observed_recipe_count: number; observed_profile_count: number; missing_recipe_ids: number[] } };
export function effectiveRecipeId(assessment: DetectedAssessment) {
  if (assessment.recorded_tracking?.status === "HELD") return null;
  return assessment.pattern_membership?.recipe_id ?? assessment.recipe_id;
}
export function detectedRecipeLabel(assessment?: DetectedAssessment) {
  if (!assessment) return "Not Yet Observed";
  if (assessment.recorded_tracking?.status === "HELD") return "Unresolved · Tracking Evidence Held";
  if (assessment.pattern_membership?.status === "DISCOVERED_UNVERIFIED") return `Observed Recipe ${assessment.pattern_membership.recipe_id} · Unverified · Color Review Flag`;
  if (assessment.pattern_membership?.status === "PENDING_REPEAT") return `Pending Pattern · ${assessment.pattern_membership.qualifying_fill_count}/${assessment.pattern_membership.required_fill_count} Qualifying Fills · Color Review Flag`;
  if (assessment.action === "CREATE_DISCOVERED_PATTERN") return `Discovered Recipe ${assessment.recipe_id} · Unverified`;
  if (assessment.action === "REUSE_DISCOVERED_PATTERN") return `Reused Recipe ${assessment.recipe_id} · Unverified`;
  if (assessment.action === "REUSE_REFERENCE_PATTERN") return `Reference Pattern ${assessment.recipe_id} · Identity Unconfirmed`;
  return assessment.color.status === "CONFLICTING" ? "Unresolved · Color Review Flag" : "Unresolved";
}
export function useRecordedObserver(videoId?: string, automatic=false) {
  const [job, setJob] = useState<ProducerJob | null>(null), [status, setStatus] = useState<ProducerStatus | null>(null);
  const [error, setError] = useState(""), [requesting, setRequesting] = useState(false), [refresh, setRefresh] = useState(0);
  const generation = useRef(0), started=useRef(new Set<string>());
  useEffect(() => {
    generation.current++;
    const abort = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    setJob(null); setStatus(null); setError(""); setRequesting(false);
    if (!videoId) return () => abort.abort();
    const poll = async () => {
      try {
        const value = await fetch(`/api/recorded-observer/videos/${videoId}`, { signal: abort.signal }).then(readResponse<ProducerJob>);
        if (abort.signal.aborted) return;
        setJob(value);
        if (value.state === "processing" || value.state === "queued") timer = setTimeout(() => void poll(), 1500);
      } catch (e) { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : "Could not load observations."); }
    };
    fetch("/api/recorded-observer/status", { signal: abort.signal }).then(readResponse<ProducerStatus>).then(value => {
      if (abort.signal.aborted) return;
      setStatus(value); if (value.enabled) void poll();
    }).catch(e => { if (!abort.signal.aborted) setError(e.message); });
    return () => { generation.current++; abort.abort(); if (timer) clearTimeout(timer); };
  }, [videoId, refresh]);
  const start = useCallback(async (retry=false) => {
    if (!videoId) return;
    const requestGeneration = generation.current;
    setRequesting(true); setError("");
    try {
      await fetch(`/api/recorded-observer/videos/${videoId}${retry ? "" : "/ensure"}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(readResponse<ProducerJob>);
      if (requestGeneration === generation.current) setRefresh(n => n + 1);
    } catch (e) { if (requestGeneration === generation.current) setError(e instanceof Error ? e.message : "Could not start processing."); }
    finally { if (requestGeneration === generation.current) setRequesting(false); }
  }, [videoId]);
  useEffect(() => {
    if (!automatic || !videoId || !status?.enabled || !status.available || started.current.has(videoId)) return;
    started.current.add(videoId); void start();
  }, [automatic,videoId,status,start]);
  return { job, status, error, start, busy: requesting || job?.state === "processing" || job?.state === "queued", reload: () => setRefresh(n => n + 1) };
}
