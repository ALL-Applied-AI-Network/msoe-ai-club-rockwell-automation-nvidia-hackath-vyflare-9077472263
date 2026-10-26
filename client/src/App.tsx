import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import type { AppData } from "../../shared/domain";
import { loadAppData } from "./api";
import { Shell } from "./components/Shell";
import { AboutPage } from "./pages/AboutPage";
import { HistoryPage } from "./pages/HistoryPage";
import { InspectionPage } from "./pages/InspectionPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RecipesPage } from "./pages/RecipesPage";
import { AnalyzePage } from "./pages/AnalyzePage";
import { ExperimentsPage } from "./pages/ExperimentsPage";

function InspectionRoute({ data, selected, setSelected }: { data: AppData; selected: string; setSelected: (id: string) => void }) {
  const { caseId } = useParams(); const nav = useNavigate(); const valid = data.cases.some((item) => item.caseId === caseId); const active = valid ? caseId! : selected;
  const select = (id: string) => { setSelected(id); nav(`/inspection/${id}`); };
  return <InspectionPage data={data} selectedId={active} onSelect={select} />;
}

export default function App() {
  const [data,setData] = useState<AppData | null>(null); const [error,setError] = useState<string | null>(null); const [selected,setSelected] = useState("");
  useEffect(() => { const controller = new AbortController(); loadAppData(controller.signal).then((next) => { setData(next); setSelected(next.cases[1]?.caseId ?? next.cases[0]?.caseId ?? ""); }).catch((e) => { if (e.name !== "AbortError") setError(e.message); }); return () => controller.abort(); }, []);
  if (error) return <div className="app-state"><strong>Inspection data could not be loaded</strong><span>{error}</span><button onClick={() => location.reload()}>Retry</button></div>;
  if (!data || !selected) return <div className="app-state" role="status"><span className="loader" /><strong>Loading recorded demo</strong><span>Connecting to the local inspection API…</span></div>;
  return <Shell><Routes><Route path="/analyze" element={<AnalyzePage />} /><Route path="/experiments" element={<ExperimentsPage />} /><Route path="/overview" element={<OverviewPage data={data} onSelect={setSelected} />} /><Route path="/inspection/:caseId?" element={<InspectionRoute data={data} selected={selected} setSelected={setSelected} />} /><Route path="/history" element={<HistoryPage data={data} onSelect={setSelected} />} /><Route path="/recipes" element={<RecipesPage data={data} />} /><Route path="/about" element={<AboutPage />} /><Route path="*" element={<Navigate to={`/inspection/${selected}`} replace />} /></Routes></Shell>;
}
