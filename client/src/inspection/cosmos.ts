export const cosmosMethods: Record<string, string> = {
  cosmos: "Cosmos — Local GPU", cosmos_lite: "Cosmos — Local GPU (Lite Route)", cosmos_full: "Cosmos — Remote Worker"
};
export type CosmosResponse = { frame_id: string; model: string; mode: "real"; inference_ms: number;
  result: { text: string; implementation?: string; model_identity?: Record<string, unknown>; prompt_applied?: string; image_sha256?: string; task_scope?: string; integration_reference?: Record<string, string>; execution?: { system?: string; machine?: string; gpu?: string }; safety?: Record<string, string> } };
export function validateCosmosResponse(value: unknown, frameId: string, model: string): CosmosResponse {
  const v = value as Partial<CosmosResponse> | null;
  if (!v || v.mode !== "real" || (v.result as {mock?:boolean})?.mock) throw new Error("A real Cosmos response is required. Mock responses are not observations.");
  if (v.frame_id !== frameId || v.model !== model) throw new Error("Cosmos returned a response for different evidence or a different model.");
  if (typeof v.result?.text !== "string" || !v.result.text.trim() || typeof v.inference_ms !== "number" || !Number.isFinite(v.inference_ms) || v.inference_ms < 0) throw new Error("Cosmos returned an invalid observation.");
  return v as CosmosResponse;
}
