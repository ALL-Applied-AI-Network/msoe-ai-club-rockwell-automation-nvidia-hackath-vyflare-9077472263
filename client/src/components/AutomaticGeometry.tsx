import { useEffect, useState, type RefObject } from "react";
import { containedMedia } from "../inspection/geometry";
import type { GeometryFrame } from "../inspection/automaticGeometry";
export function AutomaticGeometry({ media, frame }: { media: RefObject<HTMLVideoElement | null>; frame: GeometryFrame | null }) {
  const [fit, setFit] = useState({ x: 0, y: 0, width: 0, height: 0 });
  useEffect(() => {
    const player = media.current; if (!player) return;
    const update = () => { const r = player.getBoundingClientRect(); setFit(containedMedia(r.width, r.height, player.videoWidth, player.videoHeight)); };
    const observer = new ResizeObserver(update); observer.observe(player); player.addEventListener("loadedmetadata", update); update();
    return () => { observer.disconnect(); player.removeEventListener("loadedmetadata", update); };
  }, [media, !!frame]);
  if (!frame || !fit.width) return null;
  return <svg className="automatic-geometry" viewBox="0 0 640 480" preserveAspectRatio="none" style={{ left: fit.x, top: fit.y, width: fit.width, height: fit.height }} aria-label="Automatic Vial and Liquid Surface Tracking">
    {frame.detections.map(d => <g key={d.position} className={d.status === "TRACKING" ? "is-tracked" : "is-uncertain"}>
      <rect x={d.box.x * 640} y={d.box.y * 480} width={d.box.width * 640} height={d.box.height * 480} vectorEffect="non-scaling-stroke" />
      <text x={d.box.x * 640} y={Math.max(14, d.box.y * 480 - 5)}>{d.track_id?.replace(/^Vial /, "Track ") ?? d.position} · {d.status === "TRACKING" ? "Tracked" : d.status === "MOVING" ? "Moving" : "Confirming"}</text>
      {d.surface && <line x1={d.surface.x1 * 640} x2={d.surface.x2 * 640} y1={d.surface.y1 * 480} y2={d.surface.y2 * 480} vectorEffect="non-scaling-stroke" />}
    </g>)}
  </svg>;
}
