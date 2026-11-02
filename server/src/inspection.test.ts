import express from "express";
import type { Server } from "node:http";
import { afterEach, describe, expect, it } from "vitest";
import { inspectionRouter } from "./inspection.js";
import { readFileSync } from "node:fs";
import { playbackObservation } from "../../client/src/inspection/playback.js";

let server: Server | undefined;
afterEach(async () => { if (server) await new Promise<void>(resolve => server!.close(() => resolve())); });
describe("Recorded inspection evidence", () => {
  it("exposes reviewed video-1/2 annotations and rejects arbitrary video paths", async () => {
    const app = express(); app.use(inspectionRouter()); server = app.listen(0, "127.0.0.1");
    await new Promise<void>((resolve, reject) => { server!.once("listening", resolve); server!.once("error", reject); });
    const address = server.address(); if (!address || typeof address === "string") throw Error("Missing port");
    const url = `http://127.0.0.1:${address.port}`;
    const response = await fetch(`${url}/evidence`); expect(response.status).toBe(200);
    const body = await response.json(); expect(body.provenance).toBe("sampled_visual_review");
    expect(body.videos.slice(0,2).map((v: { vials: unknown[] }) => v.vials.length)).toEqual([19, 3]);
    expect(body.videos[0].vials[0].flowEndUpper).toBe(27.75);
    expect(body.videos[0].vials[0].label).toBe("Video 1 · Vial 1");
    expect(body.videos[0].vials[0]).not.toHaveProperty("recipe_id");
    const unknown = await fetch(`${url}/videos/not-a-video`); expect(unknown.status).toBe(404); expect((await unknown.json()).error).toBe("Unknown recorded video.");
  });
});

describe("Playback annotations", () => {
  const vials = JSON.parse(readFileSync("evidence/recorded-inspection.json", "utf8")).videos[0].vials;
  it("follows video time without showing a future final color or stale vial", () => {
    expect(playbackObservation(vials, 4.5).appearance).toBeUndefined();
    expect(playbackObservation(vials, 10).state).toBe("Dispensing · pulse 1");
    expect(playbackObservation(vials, 20).state).toBe("Between reviewed dispenses");
    expect(playbackObservation(vials, 27.8).appearance).toBeUndefined();
    expect(playbackObservation(vials, 28).appearance).toBe("Blue");
    expect(playbackObservation(vials, 31).vial).toBeUndefined();
    expect(playbackObservation(vials, 60).vial?.label).toBe("Video 1 · Vial 2");
    expect(playbackObservation(vials, 4.5).appearance).toBeUndefined();
  });
  it("keeps sampled boundaries uncertain and handles videos without annotations", () => {
    expect(playbackObservation(vials, 27.6).state).toBe("Dispense timing boundary");
    expect(playbackObservation(vials, 27.6).appearance).toBeUndefined();
    expect(playbackObservation([], 10).vial).toBeUndefined();
  });
});
