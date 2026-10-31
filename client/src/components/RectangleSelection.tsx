import { useRef, type PointerEvent } from "react";
import { clamp, rectangleBetween, type Point, type Rectangle } from "../inspection/geometry";

export function RectangleSelection({ value, onChange, disabled = false }: {
  value: Rectangle; onChange: (rectangle: Rectangle) => void; disabled?: boolean;
}) {
  const drag = useRef<{ start: Point; original: Rectangle } | null>(null);
  const point = (e: PointerEvent<SVGSVGElement>) => {
    const bounds = e.currentTarget.getBoundingClientRect();
    return { x: clamp((e.clientX - bounds.left) / bounds.width), y: clamp((e.clientY - bounds.top) / bounds.height) };
  };
  const update = (e: PointerEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    const next = rectangleBetween(drag.current.start, point(e));
    if (next.width >= 0.005 && next.height >= 0.005) onChange(next);
  };
  return <svg className="rectangle-selection" viewBox="0 0 1 1" preserveAspectRatio="none" role="img" aria-label="Draw a rectangle on the image to select pixels" style={{ pointerEvents: disabled ? "none" : "auto" }}
    onPointerDown={e => { if (disabled || e.button !== 0) return; e.preventDefault(); e.currentTarget.focus(); e.currentTarget.setPointerCapture(e.pointerId); drag.current = { start: point(e), original: value }; }}
    onPointerMove={update} onPointerUp={e => { update(e); drag.current = null; if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); }}
    onPointerCancel={() => { if (drag.current) onChange(drag.current.original); drag.current = null; }} tabIndex={disabled ? -1 : 0}
    onKeyDown={e => { if (e.key === "Escape" && drag.current) { onChange(drag.current.original); drag.current = null; } }}>
    <rect x={value.x} y={value.y} width={value.width} height={value.height} vectorEffect="non-scaling-stroke" />
  </svg>;
}
