import { AlertTriangle, CheckCircle2, CircleHelp } from "lucide-react";
import type { Decision } from "../../../shared/domain";

const config = {
  MATCH: { label: "Match", icon: CheckCircle2 },
  MISMATCH: { label: "Mismatch", icon: AlertTriangle },
  UNABLE_TO_DECIDE: { label: "Unable to Decide", icon: CircleHelp }
} as const;

export function DecisionBadge({ decision, large = false }: { decision: Decision; large?: boolean }) {
  const { label, icon: Icon } = config[decision];
  return <span className={`decision decision--${decision.toLowerCase()} ${large ? "decision--large" : ""}`}><Icon aria-hidden="true" />{label}</span>;
}
