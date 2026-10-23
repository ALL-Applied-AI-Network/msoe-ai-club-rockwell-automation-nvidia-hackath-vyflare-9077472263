import cors from "cors";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { appData, cases, recipes } from "./data.js";

const app = express();
const port = Number(process.env.PORT ?? 8787);
app.use(cors());
app.use(express.json());

app.get("/api/health", (_req, res) => res.json({ status: "ok", mode: "recorded-demo", machineControl: false }));
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
app.use(express.static(clientDist));
app.get("/{*splat}", (_req, res) => res.sendFile(path.join(clientDist, "index.html")));

app.listen(port, "0.0.0.0", () => console.log(`Vyflare API listening on port ${port}`));
