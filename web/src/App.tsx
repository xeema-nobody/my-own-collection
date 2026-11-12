import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import Search from "./pages/Search";
import CardDetail from "./pages/CardDetail";
import Collection from "./pages/Collection";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";
import Wishlist from "./pages/Wishlist";
import Alerts from "./pages/Alerts";
import NotFound from "./pages/NotFound";
import Scan from "./pages/Scan";
import ScanToast from "./components/scan/ScanToast";
import ErrorBoundary from "./components/ErrorBoundary";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import FetcherBadge from "./components/FetcherBadge";
import Reprice from "./pages/Reprice";
import ThemeToggle from "./components/ThemeToggle";

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded px-3 py-1.5 text-sm font-medium transition ${isActive ? "bg-accent/15 text-accent" : "text-muted hover:bg-surface-2 hover:text-fg"}`;

function AlertsLink() {
  const unread = useQuery({ queryKey: ["alerts", "unread"], queryFn: api.alertUnread, refetchInterval: 60_000 });
  const n = unread.data?.count ?? 0;
  return <NavLink to="/alerts" className={link}>Alerts{n > 0 && <span className="num ml-1.5 rounded-full bg-danger px-1.5 text-xs text-white" aria-label={`${n} unread`}>{n}</span>}</NavLink>;
}

export default function App() {
  // The phone page is its own shell: no laptop nav, and none of the laptop's background polling (the phone may
  // only reach /api/scan/*).
  const loc = useLocation();
  const sealedView = loc.pathname === "/collection" && new URLSearchParams(loc.search).get("kind") === "sealed";
  if (loc.pathname.startsWith("/scan")) return <ErrorBoundary><Scan /></ErrorBoundary>;
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur">
        <nav className="mx-auto flex max-w-[1800px] items-center gap-1 px-6 py-2">
          <span className="mr-6 text-base font-semibold tracking-tight">My Collection</span>
          <NavLink to="/" end className={link}>Search</NavLink>
          <NavLink to="/collection" className={({ isActive }) => link({ isActive: isActive && !sealedView })}>Collection</NavLink>
          <NavLink to="/wishlist" className={link}>Wishlist</NavLink>
          <NavLink to="/collection?kind=sealed" className={() => link({ isActive: sealedView })}>Sealed</NavLink>
          <NavLink to="/dashboard" className={link}>Dashboard</NavLink>
          <NavLink to="/reprice" className={link}>Reprice</NavLink>
          <AlertsLink />
          <NavLink to="/settings" className={link}>Settings</NavLink>
          <div className="ml-auto flex items-center gap-4"><FetcherBadge /><ThemeToggle /></div>
        </nav>
      </header>
      <div className="mx-auto max-w-[1800px] px-6 py-6">
      <ErrorBoundary><Routes>
        <Route path="/" element={<Search />} />
        <Route path="/cards/:id" element={<CardDetail />} />
        <Route path="/collection" element={<Collection />} />
        <Route path="/wishlist" element={<Wishlist />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/reprice" element={<Reprice />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Routes></ErrorBoundary>
      </div>
      <ScanToast />
    </div>
  );
}
