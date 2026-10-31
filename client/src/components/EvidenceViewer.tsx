import { ImageOff, Layers3 } from "lucide-react";
import type { InspectionCase } from "../../../shared/domain";

export function EvidenceViewer({ item, showOverlays, onToggle }: { item: InspectionCase; showOverlays: boolean; onToggle: () => void }) {
  return <section className="evidence card" aria-labelledby="evidence-title">
    <div className="card__header">
      <div><p className="eyebrow">Camera Evidence</p><h2 id="evidence-title">{item.cameraId}</h2></div>
      <button className={`ghost-button ${showOverlays ? "is-active" : ""}`} onClick={onToggle} disabled={!item.overlays.length} title={!item.overlays.length ? "No overlay geometry is available" : undefined}>
        <Layers3 aria-hidden="true" /> {showOverlays ? "Hide Overlays" : "Show Overlays"}
      </button>
    </div>
    <div className="evidence__viewport">
      {item.imageUrl ? <>
        <img src={item.imageUrl} alt={`Recorded Vial Fill frame for source vial ${item.sourceVialId ?? "unknown"}`} />
        {showOverlays && item.overlays.map((overlay) => overlay.kind === "REGION"
          ? <span key={overlay.id} className="overlay overlay--region" style={{ left: `${overlay.coordinates.x * 100}%`, top: `${overlay.coordinates.y * 100}%`, width: `${overlay.coordinates.width * 100}%`, height: `${(overlay.coordinates.height ?? 0) * 100}%` }} />
          : <span key={overlay.id} className="overlay overlay--boundary" style={{ left: `${overlay.coordinates.x * 100}%`, top: `${overlay.coordinates.y * 100}%`, width: `${overlay.coordinates.width * 100}%` }} />)}
      </> : <div className="empty-state"><ImageOff /><strong>Source Image Unavailable</strong><span>No captured frame is attached to this case.</span></div>}
    </div>
    <div className="evidence__footer">
      <span><b>Run</b> {item.runId}</span><span><b>Source Vial</b> {item.sourceVialId ?? "Unavailable"}</span><span><b>Frame</b> Dataset record</span>
      {item.overlays.length > 0 && <span className="legend"><i /> Illustrative Overlay</span>}
    </div>
  </section>;
}
