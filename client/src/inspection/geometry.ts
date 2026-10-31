export type Point = { x: number; y: number };
export type Rectangle = { x: number; y: number; width: number; height: number };
export type Surface = { left: number; right: number };
export type Guide = { time: number; box: Rectangle; surface?: Surface };
export const clamp = (value: number, min = 0, max = 1) => Math.max(min, Math.min(max, value));
const rounded = (value: number) => Math.round(value * 10000) / 10000;
export function rectangleBetween(a: Point, b: Point): Rectangle {
  const x = rounded(clamp(Math.min(a.x, b.x))), y = rounded(clamp(Math.min(a.y, b.y)));
  return { x, y, width: rounded(clamp(Math.max(a.x, b.x)) - x), height: rounded(clamp(Math.max(a.y, b.y)) - y) };
}
export function containedMedia(width: number, height: number, sourceWidth: number, sourceHeight: number) {
  if (!sourceWidth || !sourceHeight) return { x: 0, y: 0, width, height };
  const scale = Math.min(width / sourceWidth, height / sourceHeight);
  const w = sourceWidth * scale, h = sourceHeight * scale;
  return { x: (width - w) / 2, y: (height - h) / 2, width: w, height: h };
}
// Manual keyframes are interpolated only inside their reviewed time span.
export function guideAt(guides: Guide[], time: number, interpolate: boolean): Guide | undefined {
  const exact = guides.find(g => Math.abs(g.time - time) < 0.06);
  if (exact) return exact;
  if (!interpolate) return undefined;
  const sorted = [...guides].sort((a, b) => a.time - b.time);
  const right = sorted.findIndex(g => g.time > time);
  if (right <= 0) return undefined;
  const a = sorted[right - 1], b = sorted[right], ratio = (time - a.time) / (b.time - a.time);
  const mix = (x: number, y: number) => x + (y - x) * ratio;
  return { time, box: { x: mix(a.box.x, b.box.x), y: mix(a.box.y, b.box.y), width: mix(a.box.width, b.box.width), height: mix(a.box.height, b.box.height) },
    surface: a.surface && b.surface ? { left: mix(a.surface.left, b.surface.left), right: mix(a.surface.right, b.surface.right) } : undefined };
}
