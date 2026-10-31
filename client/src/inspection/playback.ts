import type { Vial } from "./types.js";

// These are reviewed video-time brackets, not events produced by a detector.
export function playbackObservation(vials: Vial[], seconds: number) {
  const vial = vials.find(v => seconds >= Math.max(0, v.pulses[0].startLower - 2) && seconds < v.stationaryUntil);
  if (!vial) return { vial: undefined, state: "Between reviewed fills", detail: "No reviewed vial observation at this video time.", appearance: undefined };
  const pulse = vial.pulses.find(p => seconds >= p.startLower && seconds <= p.endUpper);
  if (pulse) {
    const boundary = seconds < pulse.startUpper || seconds >= pulse.endLower;
    return { vial, state: boundary ? "Dispense timing boundary" : `Dispensing · pulse ${pulse.order}`,
      detail: boundary ? "The sampled review does not establish an exact start or stop time." : `Observed liquid: ${pulse.appearance}`,
      appearance: boundary ? undefined : pulse.appearance };
  }
  if (seconds < vial.pulses[0].startLower) return { vial, state: "Before first reviewed dispense", detail: "Liquid appearance has not been assessed at this time.", appearance: undefined };
  if (seconds > vial.flowEndUpper) return { vial, state: "After final reviewed dispense", detail: "Post-fill evidence is available for review.", appearance: seconds >= vial.finalSampleSeconds ? vial.appearance : undefined };
  return { vial, state: "Between reviewed dispenses", detail: "No flow observed in this interval.", appearance: undefined };
}
