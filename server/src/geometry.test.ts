import { describe, expect, it } from "vitest";
import { containedMedia, guideAt, rectangleBetween, type Guide } from "../../client/src/inspection/geometry.js";

describe("Manual image and video geometry", () => {
  it("supports reverse dragging and clamps selection to image bounds", () => {
    expect(rectangleBetween({ x: 0.8, y: 1.2 }, { x: -0.1, y: 0.3 })).toEqual({ x: 0, y: 0.3, width: 0.8, height: 0.7 });
  });
  it("maps wide and portrait video guides to the visible media, excluding letterboxing", () => {
    expect(containedMedia(640, 480, 1280, 720)).toEqual({ x: 0, y: 60, width: 640, height: 360 });
    expect(containedMedia(640, 480, 1080, 1920)).toEqual({ x: 185, y: 0, width: 270, height: 480 });
  });
  const guides: Guide[] = [
    { time: 10, box: { x: 0.2, y: 0.1, width: 0.2, height: 0.8 }, surface: { left: 0.8, right: 0.82 } },
    { time: 20, box: { x: 0.4, y: 0.1, width: 0.2, height: 0.8 }, surface: { left: 0.4, right: 0.42 } }
  ];
  it("interpolates reviewed guides only when enabled, without extrapolating", () => {
    expect(guideAt(guides, 15, false)).toBeUndefined();
    expect(guideAt(guides, 5, true)).toBeUndefined();
    expect(guideAt(guides, 25, true)).toBeUndefined();
    const middle = guideAt(guides, 15, true)!;
    expect(middle.box.x).toBeCloseTo(0.3);
    expect(middle.surface?.left).toBeCloseTo(0.6);
    expect(middle.surface?.right).toBeCloseTo(0.62);
    expect(guideAt(guides, 10, false)).toEqual(guides[0]);
  });
  it("does not invent a surface when either bounding keyframe lacks one", () => {
    expect(guideAt([guides[0], { time: 20, box: guides[1].box }], 15, true)?.surface).toBeUndefined();
  });
});
