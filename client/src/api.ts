import type { AppData } from "../../shared/domain";

export async function loadAppData(signal?: AbortSignal): Promise<AppData> {
  const response = await fetch("/api/bootstrap", { signal });
  if (!response.ok) throw new Error(`Inspection API returned ${response.status}`);
  return response.json();
}
