import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { detectedRecipeLabel, effectiveRecipeId, type DetectedAssessment } from "../../client/src/inspection/recordedObserver";
import { RecordedObserverPanel } from "../../client/src/components/RecordedObserverPanel";
vi.stubGlobal("React", React);
function assessment(status: string): DetectedAssessment {
  return { observation_id: "fixture", action: "UNRESOLVED", recipe_id: null, reason: "COLOR_CONFLICT", hold_reasons: [],
    timing: { possible_recipe_ids: [7] }, color: { status: "CONFLICTING" },
    observation: { label: "Video 1 · Vial 13", video_id: "video-1", vial_id: "V1-V13", source_kind: "TEST_FIXTURE",
      source_episode_intervals: [{ start: [1, 1.1], end: [2, 2.1] }], duration_bounds_seconds: [[.9, 1.1]],
      departure_interval_seconds: [5, 5.2], candidate_appearance_window_seconds: [3, 4], raw_rgb: { nominal: [10, 12, 12] } },
    pattern_membership: { group_id: "pending-conflict-002", recipe_id: status === "DISCOVERED_UNVERIFIED" ? 102 : null,
      status, revision_id: 2, qualifying_fill_count: status === "DISCOVERED_UNVERIFIED" ? 2 : 1, required_fill_count: 2,
      review_flags: ["COLOR_CONFLICT_REVIEW"], baseline_timing_candidate_ids: [7],
      history: [{ revision_id: 1, status: "PENDING_REPEAT", event: "FILL_PENDING", supersedes_revision_id: null },
        ...(status === "DISCOVERED_UNVERIFIED" ? [{ revision_id: 2, status, event: "PATTERN_CONFIRMED_BY_TWO_FILLS", supersedes_revision_id: 1 }] : [])] } };
}
describe("Observed pattern presentation", () => {
  it("keeps pending groups without recipe IDs and retains the review flag", () => {
    const a = assessment("PENDING_REPEAT");
    expect(effectiveRecipeId(a)).toBeNull();
    expect(detectedRecipeLabel(a)).toContain("1/2 Qualifying Fills");
    expect(detectedRecipeLabel(a)).toContain("Color Review Flag");
  });
  it("counts confirmed membership as a link while leaving the baseline unresolved", () => {
    const a = assessment("DISCOVERED_UNVERIFIED");
    expect(effectiveRecipeId(a)).toBe(102);expect(a.recipe_id).toBeNull();expect(a.action).toBe("UNRESOLVED");
    expect(detectedRecipeLabel(a)).toBe("Observed Recipe 102 · Unverified · Color Review Flag");
  });
  it("renders effective counts, prior candidate and append-only membership history", () => {
    const a = assessment("DISCOVERED_UNVERIFIED");
    const html = renderToStaticMarkup(<RecordedObserverPanel name="Video 1" onSeek={() => {}} observer={{
      job: { state: "saved", progress: 100, assessments: [a] }, status: { enabled: true, available: true, reason: null },
      error: "", busy: false, start: async () => {}, reload: () => {}
    }} />);
    expect(html).toContain("1 recipe links");expect(html).toContain("0 unresolved");
    expect(html).toContain("Original Timing Candidates: 7");
    expect(html).toContain("Pattern Membership History");expect(html).toContain("Revision 1");expect(html).toContain("Revision 2");
    expect(html).toContain("Nominal identity remains unconfirmed");
  });
});
