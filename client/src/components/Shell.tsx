import { Activity, BookOpen, ClipboardList, Flame, Info, LayoutDashboard, Menu, ShieldCheck, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

const links = [
  ["/inspect", "Inspection Workspace", Activity],
  ["/overview", "Overview", LayoutDashboard],
  ["/analyze", "Analyze an Image", Activity],
  ["/experiments", "Recorded Experiments", ClipboardList],
  ["/inspection", "Demo Case Review", Activity],
  ["/history", "Case History", ClipboardList],
  ["/recipes", "Recipes", BookOpen],
  ["/about", "System / About", Info]
] as const;

export function Shell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return <div className="app-shell">
    <button className="mobile-menu" onClick={() => setOpen(!open)} aria-label="Toggle navigation">{open ? <X /> : <Menu />}</button>
    <aside className={`sidebar ${open ? "sidebar--open" : ""}`}>
      <div className="brand"><span className="brand__mark"><Flame /></span><div><strong>VYFLARE</strong><small>Inspection Console</small></div></div>
      <nav aria-label="Main navigation">{links.map(([to,label,Icon]) => <NavLink key={to} to={to} onClick={() => setOpen(false)}><Icon aria-hidden="true" /><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar__foot"><ShieldCheck /><div><strong>No Control Path</strong><span>Advisory only</span></div></div>
    </aside>
    <main>
      <header className="topbar"><div className="demo-pill"><span /> Experimental Inspection Workspace</div><div className="advisory"><ShieldCheck /> Advisory only — no machine control</div></header>
      <div className="page">{children}</div>
    </main>
  </div>;
}
