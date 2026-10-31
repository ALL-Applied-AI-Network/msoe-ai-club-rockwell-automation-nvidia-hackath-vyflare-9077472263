import { useEffect, useRef, useState, type PointerEvent, type RefObject } from "react";
import { createPortal } from "react-dom";
import { RectangleSelection } from "./RectangleSelection";
import { clamp, containedMedia, guideAt, type Guide, type Point } from "../inspection/geometry";
import { timeLabel } from "../inspection/types";

export function VideoGeometry({ media, currentTime, scope, scopeLabel, disabled, onSeek }: {
  media: RefObject<HTMLVideoElement | null>; currentTime: number; scope: string | null; scopeLabel: string; disabled: boolean; onSeek: (time: number) => void;
}) {
  const [byScope, setByScope] = useState<Record<string, Guide[]>>({});
  const [draft, setDraft] = useState<Guide | null>(null), [tool, setTool] = useState<"box" | "surface" | null>(null);
  const [interpolate, setInterpolate] = useState(false), [show, setShow] = useState(true);
  const [fit, setFit] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const surfaceStart = useRef<Point | null>(null);
  useEffect(() => {
    const player = media.current; if (!player) return;
    const update = () => setFit(containedMedia(player.clientWidth, player.clientHeight, player.videoWidth, player.videoHeight));
    const stopEditing = () => { setTool(null); setDraft(null); surfaceStart.current = null; };
    const observer = new ResizeObserver(update); observer.observe(player); update();
    player.addEventListener("loadedmetadata", update); player.addEventListener("play", stopEditing);
    return () => { observer.disconnect(); player.removeEventListener("loadedmetadata", update); player.removeEventListener("play", stopEditing); };
  }, [media]);
  useEffect(() => { setDraft(null); setTool(null); surfaceStart.current = null; }, [scope]);
  useEffect(() => { if (draft && Math.abs(draft.time - currentTime) > 0.1) { setDraft(null); setTool(null); } }, [currentTime, draft]);
  useEffect(() => { if (disabled) { setDraft(null); setTool(null); } }, [disabled]);
  const guides = scope ? byScope[scope] ?? [] : [];
  const visible = draft ?? guideAt(guides, currentTime, interpolate);
  const validBox = visible && visible.box.width >= 0.005 && visible.box.height >= 0.005;
  const enabled = !disabled && !!scope && fit.width > 0 && !!media.current?.videoWidth;
  const startTool = (next: "box" | "surface") => {
    if (!enabled || (next === "surface" && !validBox)) return;
    media.current?.pause(); media.current?.scrollIntoView({ block: "center" }); setShow(true); setTool(next);
    setDraft(visible ? { ...visible, time: currentTime } : { time: currentTime, box: { x: 0, y: 0, width: 0, height: 0 } });
  };
  const reuseBox = () => {
    if (!enabled || !guides.length) return;
    const nearest = guides.reduce((best, g) => Math.abs(g.time - currentTime) < Math.abs(best.time - currentTime) ? g : best);
    media.current?.pause(); media.current?.scrollIntoView({ block: "center" });
    setDraft({ time: currentTime, box: { ...nearest.box } }); setTool("surface"); setShow(true);
  };
  const point = (e: PointerEvent<SVGSVGElement>) => {
    const bounds = e.currentTarget.getBoundingClientRect();
    return { x: clamp((e.clientX - bounds.left) / bounds.width), y: clamp((e.clientY - bounds.top) / bounds.height) };
  };
  const surfaceTo = (start: Point, end: Point) => setDraft(g => !g ? g : { ...g, surface: {
    left: clamp(start.x <= end.x ? start.y : end.y, g.box.y, g.box.y + g.box.height),
    right: clamp(start.x <= end.x ? end.y : start.y, g.box.y, g.box.y + g.box.height)
  } });
  const save = () => {
    if (!scope || !draft || !validBox) return;
    setByScope(all => ({ ...all, [scope]: [...(all[scope] ?? []).filter(g => Math.abs(g.time - draft.time) >= 0.06), draft].sort((a, b) => a.time - b.time) }));
    setDraft(null); setTool(null);
  };
  const portal = media.current?.parentElement;
  return <>
    {portal && fit.width > 0 && show && (visible || tool) && createPortal(<div className="video-geometry-layer" style={{ left: fit.x, top: fit.y, width: fit.width, height: fit.height }}>
      {tool === "box" && draft ? <RectangleSelection value={draft.box} onChange={box => setDraft(g => g ? { ...g, box, surface: undefined } : g)} /> : visible && <svg className="geometry-display" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="Manual vial box and liquid surface guide">
        <rect x={visible.box.x} y={visible.box.y} width={visible.box.width} height={visible.box.height} vectorEffect="non-scaling-stroke" />
        {visible.surface && <line x1={visible.box.x} x2={visible.box.x + visible.box.width} y1={visible.surface.left} y2={visible.surface.right} vectorEffect="non-scaling-stroke" />}
      </svg>}
      {tool === "surface" && <svg className="geometry-surface-tool" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="Drag along the top of the liquid to set its surface guide"
        onPointerDown={e => { if (e.button !== 0) return; e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); const p = point(e); surfaceStart.current = p; surfaceTo(p, p); }}
        onPointerMove={e => { if (surfaceStart.current) surfaceTo(surfaceStart.current, point(e)); }}
        onPointerUp={e => { if (surfaceStart.current) surfaceTo(surfaceStart.current, point(e)); surfaceStart.current = null; if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); }}
        onPointerCancel={() => { surfaceStart.current = null; }} />}
      {validBox && <span className="geometry-guide-label" style={{ left: `${visible.box.x * 100}%`, top: `${visible.box.y * 100}%` }}>Manual Guide{draft ? " · Editing" : guides.some(g => Math.abs(g.time - currentTime) < 0.06) ? " · Keyframe" : " · Interpolated"}</span>}
      {tool && <div className="geometry-floating-actions"><span>{tool === "box" ? "Draw the Vial Box" : "Mark the Liquid Surface"}</span><button className="ghost-button" disabled={!validBox} onClick={() => startTool("surface")}>Draw Surface</button><button className="ghost-button" disabled={!validBox} onClick={save}>Save Guide</button><button className="ghost-button" onClick={() => { setDraft(null); setTool(null); }}>Cancel</button></div>}
    </div>, portal)}
    <section className="card integration-card geometry-workbench" aria-label="Video Geometry Guides">
      <div className="card__header"><div><p className="eyebrow">Manual Video Annotation</p><h2>Vial Box and Liquid Surface</h2></div><label className="inline-check"><input type="checkbox" checked={show} onChange={e => setShow(e.target.checked)} />Show Guides</label></div>
      <p>Pause at the frame you want to annotate. Draw a vial box, then drag along the liquid surface to create a dashed line. Save multiple keyframes to follow changes during filling.</p>
      <p className="callout">Manual guides are visual annotations. They do not detect vials, measure volume, confirm camera registration, or change the images sent to Model 4. Guides stay in this page until you change the video or mode, or leave.</p>
      <p>{scope ? `${scopeLabel} · ${timeLabel(currentTime)} · ${guides.length} saved keyframes` : "Seek to a reviewed vial to add guides."}</p>
      <div className="geometry-actions"><button className="ghost-button" disabled={!enabled} aria-pressed={tool === "box"} onClick={() => startTool("box")}>Draw Vial Box</button>{guides.length > 0 && <button className="ghost-button" disabled={!enabled} onClick={reuseBox}>Reuse Saved Vial Box</button>}<button className="ghost-button" disabled={!enabled || !validBox} aria-pressed={tool === "surface"} onClick={() => startTool("surface")}>Set Liquid Surface</button><button className="primary-action" disabled={!draft || !validBox || disabled} onClick={save}>Save Guide at This Time</button>{draft && <button className="ghost-button" onClick={() => { setDraft(null); setTool(null); }}>Cancel Edit</button>}</div>
      {tool && <p role="status">{tool === "box" ? "Drag a rectangle around the vial in the paused video." : "Drag from one side of the liquid surface to the other. A click creates a horizontal line."}</p>}
      {draft?.surface && <div className="geometry-surface-fields">{(["left", "right"] as const).map(side => <label key={side}>Surface {side === "left" ? "Left" : "Right"} (% Image Height)<input type="number" step="0.1" min={draft.box.y * 100} max={(draft.box.y + draft.box.height) * 100} value={Math.round(draft.surface![side] * 1000) / 10} onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n)) setDraft(g => g?.surface ? { ...g, surface: { ...g.surface, [side]: clamp(n / 100, g.box.y, g.box.y + g.box.height) } } : g); }} /></label>)}</div>}
      <label className="inline-check"><input type="checkbox" checked={interpolate} onChange={e => setInterpolate(e.target.checked)} />Interpolate Between Saved Guides</label>
      <p>Interpolation uses your manual keyframes within this vial's reviewed time span. Guides are hidden outside their saved time range; this is not automatic tracking.</p>
      <ul className="geometry-keyframes">{guides.map(g => <li key={g.time}><button className="ghost-button" onClick={() => onSeek(g.time)} disabled={disabled}>Guide at {timeLabel(g.time)}{g.surface ? " · Surface Set" : " · Box Only"}</button><button className="ghost-button" disabled={disabled} aria-label={`Remove guide at ${timeLabel(g.time)}`} onClick={() => scope && setByScope(all => ({ ...all, [scope]: guides.filter(item => item !== g) }))}>Remove</button></li>)}</ul>
    </section>
  </>;
}
