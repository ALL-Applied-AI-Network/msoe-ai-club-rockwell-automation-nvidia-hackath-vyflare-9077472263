import { describe, expect, it } from "vitest";
import { cases, recipes } from "./data.js";

describe("inspection fixtures", () => {
  it("covers exactly the supported decision states", () => {
    expect(new Set(cases.map((item) => item.decision))).toEqual(new Set(["MATCH", "MISMATCH", "UNABLE_TO_DECIDE"]));
  });
  it("never reports calibrated volume without calibration", () => {
    expect(cases.every((item) => item.observation.calibratedVolumeMl === null)).toBe(true);
  });
  it("keeps normalized overlay geometry in bounds", () => {
    for (const item of cases) for (const overlay of item.overlays) {
      expect(overlay.coordinates.x).toBeGreaterThanOrEqual(0);
      expect(overlay.coordinates.y).toBeGreaterThanOrEqual(0);
      expect(overlay.coordinates.x + overlay.coordinates.width).toBeLessThanOrEqual(1);
    }
  });
  it("contains authoritative recipes 5 through 14", () => {
    expect(recipes.map((recipe) => recipe.recipeId)).toEqual([5,6,7,8,9,10,11,12,13,14]);
  });
});
