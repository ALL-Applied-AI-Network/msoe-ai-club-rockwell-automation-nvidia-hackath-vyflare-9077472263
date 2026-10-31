export type Decision = "MATCH" | "MISMATCH" | "UNABLE_TO_DECIDE";
export type ReviewStatus = "UNREVIEWED" | "IN_REVIEW" | "CONFIRMED";
export type Station = "VIAL_FILL" | "CAP_SEAL" | "TANK_LEVEL";
export type ProvenanceKind = "DATASET_RECORD" | "COMPUTED_RESULT" | "SIMULATED_DEMO_RESULT" | "ILLUSTRATIVE_OVERLAY";

export interface Recipe {
  recipeId: number;
  t100Ml: number | null;
  t200Ml: number | null;
  t400Ml: number | null;
  totalMl: number;
  dispenseOrder: string[];
  expectedAppearance: string | null;
  source: string;
}

export interface Overlay {
  id: string;
  kind: "REGION" | "BOUNDARY";
  label: string;
  coordinates: { x: number; y: number; width: number; height?: number };
  coordinateReference: "NORMALIZED_SOURCE_IMAGE_TOP_LEFT";
  provenance: ProvenanceKind;
}

export interface InspectionCase {
  caseId: string;
  sourceVialId: number | null;
  runId: string;
  station: Station;
  cameraId: string;
  capturedAt: string | null;
  imageUrl: string | null;
  recipeId: number;
  previousRecipeId: number | null;
  observation: {
    colorLabel: string | null;
    colorHex: string | null;
    fillRatio: number | null;
    boundaryY: number | null;
    calibratedVolumeMl: null;
    calibrationStatus: "IMAGE_RELATIVE_ONLY" | "NOT_AVAILABLE";
    provenance: ProvenanceKind;
  };
  decision: Decision;
  decisionProvenance: ProvenanceKind;
  finding: string;
  evidence: { label: string; value: string; source: string; provenance: ProvenanceKind }[];
  qualityFlags: { code: string; severity: "INFO" | "WARNING" | "BLOCKING"; message: string }[];
  hypotheses: { label: string; supportingEvidence: string[]; missingEvidence: string[] }[];
  recommendedActions: string[];
  reviewStatus: ReviewStatus;
  methodVersion: string;
  overlays: Overlay[];
}

export interface AppData {
  cases: InspectionCase[];
  recipes: Recipe[];
  meta: {
    dataset: string;
    mode: "RECORDED_DEMO";
    apiVersion: string;
    supportedStations: Station[];
  };
}
