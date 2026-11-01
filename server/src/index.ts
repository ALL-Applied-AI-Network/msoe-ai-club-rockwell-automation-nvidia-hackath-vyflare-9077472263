import cors from "cors";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { appData, cases, recipes } from "./data.js";
import { inferenceRouter } from "./inference.js";
import { inspectionRouter } from "./inspection.js";
import { recipeLibraryRouter } from "./recipe-library.js";
import { recipeWorkflowRouter } from "./recipe-workflow.js";
import { readFileSync } from "node:fs";

import { geometryRouter } from "./geometry.js";
import { recordedProducerRouter } from "./recorded-producer.js";

const app = express();
const port = Number(process.env.PORT ?? 8787);
app.use(cors());
app.use("/api/inference", inferenceRouter());
app.use("/api/inspection", inspectionRouter());
app.use("/api/recipe-library", recipeLibraryRouter());
app.use("/api/recipe-workflow", recipeWorkflowRouter());
app.use("/api/recorded-observer", recordedProducerRouter());
app.use("/api/geometry", geometryRouter());
app.use(express.json());

app.get("/api/experiments", (_req, res) => {
  const read = (file: string) => JSON.parse(readFileSync(path.resolve(file), "utf-8"));
  res.json({
    provenance: "RECORDED_EXPERIMENT", validated: false,
    anomaly: read("fluid-mixing-anomaly-detection/outputs/demo_data.json"),
    cosmos: read("cosmos-model-data/batch-results/20261025-batch01/summary.json"),
    limitations: ["Recorded Video 5 experiments; not new inference or independent production validation.",
      "Anomaly reference labels are rule-based/suspected. Threshold calibration reuses the evaluated pool.",
      "Original frame labels have an unresolved clock-alignment discrepancy; the anomaly branch uses a separately corrected dataset."]
  });
});

app.get("/api/health", (_req, res) => res.json({ status: "ok", mode: "experimental-workspace", inspectionMode: "recorded-review-and-camera-tracking", automaticVisualTracking: "experimental-fixed-station", automaticInspection: false, machineControl: false }));
app.get("/api/bootstrap", (_req, res) => res.json(appData));
app.get("/api/cases", (_req, res) => res.json(cases));
app.get("/api/cases/:id", (req, res) => {
  const item = cases.find((candidate) => candidate.caseId === req.params.id);
  if (!item) return res.status(404).json({ error: "Case not found" });
  return res.json(item);
});
app.get("/api/recipes", (_req, res) => res.json(recipes));

const here = path.dirname(fileURLToPath(import.meta.url));
const clientDist = path.resolve(here, "../../../../client/dist");
app.use("/experiment-thumbs", express.static(path.resolve("fluid-mixing-anomaly-detection/demo/thumbs")));
app.use(express.static(clientDist));
app.get("/{*splat}", (_req, res) => res.sendFile("index.html", { root: clientDist }));

app.listen(port, "0.0.0.0", () => console.log(`Vyflare API listening on port ${port}`));
