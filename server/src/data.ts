import type { AppData, Decision, InspectionCase, Recipe } from "../../shared/domain.js";

export const recipes: Recipe[] = [
  [5,10,10,10,30,"T200>T400>T100","Mixed — low even"],
  [6,30,10,null,40,"T200>T100","Pale orange"],
  [7,20,null,50,70,"T400>T100","Pale blue"],
  [8,20,20,20,60,"T200>T400>T100","Even"],
  [9,10,35,35,80,"T200>T400>T100","Dark saturated"],
  [10,45,15,15,75,"T200>T400>T100","Pale wash"],
  [11,10,10,50,70,"T200>T400>T100",null],
  [12,10,50,10,70,"T200>T400>T100",null],
  [13,null,50,20,70,"T200>T400",null],
  [14,60,null,10,70,"T400>T100",null]
].map(([recipeId,t100Ml,t200Ml,t400Ml,totalMl,order,expectedAppearance]) => ({
  recipeId: recipeId as number,
  t100Ml: t100Ml as number | null,
  t200Ml: t200Ml as number | null,
  t400Ml: t400Ml as number | null,
  totalMl: totalMl as number,
  dispenseOrder: (order as string).split(">"),
  expectedAppearance: expectedAppearance as string | null,
  source: "video5_vial_recipes.csv"
}));

const profiles: Array<[number,number,string,string,Decision,string,string,number|null,string,string]> = [
  [1,5,"vial-01.jpg","2026-09-23T19:47:11.630429","MATCH","Balanced violet","#6e5c89",0.62,"CONFIRMED","Recorded Frame Aligns with the Predefined Simulated Recipe Fixture."],
  [4,6,"vial-04.jpg","2026-09-23T19:49:28.350582","MISMATCH","Deep orange","#a9511e",0.66,"IN_REVIEW","Observed Color Differs from the Documented Pale-Orange Appearance."],
  [10,8,"vial-10.jpg","2026-09-23T19:54:26.002825","MISMATCH","Muted violet","#665b78",0.38,"UNREVIEWED","Estimated Liquid-Height Ratio Is Below the Predefined Demo Expectation."],
  [16,10,"vial-16.jpg","2026-09-23T20:00:48.210606","UNABLE_TO_DECIDE","Unavailable","#5d5d65",null,"UNREVIEWED","Glare Obscures the Liquid Boundary; Fill Comparison Cannot Be Completed."],
  [22,12,"vial-22.jpg","2026-09-23T20:06:50.289027","MISMATCH","Orange dominant","#bd5b22",0.71,"IN_REVIEW","Color Is Orange-Dominant; the Documented Expected Appearance Is Unavailable."],
  [28,14,"vial-28.jpg","2026-09-23T20:13:30.512836","MATCH","Pale blue","#7892a7",0.73,"CONFIRMED","The Predefined Simulated Comparison Found No Mismatch."],
];

export const cases: InspectionCase[] = profiles.map((p, index) => {
  const [vial, recipeId, file, capturedAt, decision, colorLabel, colorHex, fillRatio, reviewStatus, finding] = p;
  const blocking = decision === "UNABLE_TO_DECIDE";
  return {
    caseId: `DEMO-V5-${String(vial).padStart(2,"0")}`,
    sourceVialId: vial,
    runId: "VIDEO-5",
    station: "VIAL_FILL",
    cameraId: "VialFillCam",
    capturedAt,
    imageUrl: `/demo/${file}`,
    recipeId,
    previousRecipeId: index > 0 ? profiles[index - 1][1] : null,
    observation: {
      colorLabel: blocking ? null : colorLabel,
      colorHex: blocking ? null : colorHex,
      fillRatio,
      boundaryY: fillRatio === null ? null : 1 - fillRatio,
      calibratedVolumeMl: null,
      calibrationStatus: fillRatio === null ? "NOT_AVAILABLE" : "IMAGE_RELATIVE_ONLY",
      provenance: "SIMULATED_DEMO_RESULT"
    },
    decision,
    decisionProvenance: "SIMULATED_DEMO_RESULT",
    finding,
    evidence: [
      { label: "Source Frame", value: file, source: "CSI Vial-Fill dataset / video 5", provenance: "DATASET_RECORD" },
      { label: "Recipe Record", value: `Recipe ${recipeId}`, source: "video5_vial_recipes.csv", provenance: "DATASET_RECORD" },
      { label: "Comparison", value: "Deterministic presentation fixture", source: "Vyflare demo adapter", provenance: "SIMULATED_DEMO_RESULT" }
    ],
    qualityFlags: blocking
      ? [{ code: "BOUNDARY_OCCLUDED", severity: "BLOCKING", message: "Glare prevents a reliable liquid-boundary estimate." }]
      : [{ code: "UNCALIBRATED", severity: "INFO", message: "Fill is image-relative; physical volume is not established." }],
    hypotheses: decision === "MISMATCH" && index > 0 ? [{
      label: "Possible Recipe-Transition Carryover",
      supportingEvidence: [`Previous included case used Recipe ${profiles[index - 1][1]}.`],
      missingEvidence: ["No residue or line-state sensor measurement is available."]
    }] : [],
    recommendedActions: blocking
      ? ["Inspect adjacent recorded frames.", "Obtain clearer evidence before making a fill comparison."]
      : ["Confirm the intended recipe in the batch record.", "Inspect the frame and its neighboring frames."],
    reviewStatus: reviewStatus as InspectionCase["reviewStatus"],
    methodVersion: "demo-fixture/1.0",
    overlays: blocking ? [] : [
      { id: `roi-${vial}`, kind: "REGION", label: "Vial Measurement Region", coordinates: { x: .42, y: .2, width: .18, height: .64 }, coordinateReference: "NORMALIZED_SOURCE_IMAGE_TOP_LEFT", provenance: "ILLUSTRATIVE_OVERLAY" },
      { id: `boundary-${vial}`, kind: "BOUNDARY", label: "Estimated Liquid Boundary", coordinates: { x: .42, y: 1 - (fillRatio ?? 0), width: .18 }, coordinateReference: "NORMALIZED_SOURCE_IMAGE_TOP_LEFT", provenance: "ILLUSTRATIVE_OVERLAY" }
    ]
  };
});

export const appData: AppData = {
  cases,
  recipes,
  meta: { dataset: "CSI Vial-Fill Multi-Camera Dataset", mode: "RECORDED_DEMO", apiVersion: "1.0", supportedStations: ["VIAL_FILL"] }
};
