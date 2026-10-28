import { NavLink, Route, Routes } from "react-router-dom";
import Search from "./pages/Search";
import CardDetail from "./pages/CardDetail";
import Collection from "./pages/Collection";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";
import Alerts from "./pages/Alerts";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded text-sm ${isActive ? "bg-indigo-600 text-white" : "hover:bg-slate-200 dark:hover:bg-slate-700"}`;

function AlertsLink() {
  const unread = useQuery({ queryKey: ["alerts", "unread"], queryFn: api.alertUnread, refetchInterval: 60_000 });
  const n = unread.data?.count ?? 0;
  return <NavLink to="/alerts" className={link}>Alerts{n > 0 && <span className="ml-1.5 rounded-full bg-red-500 px-1.5 text-xs text-white" aria-label={`${n} unread`}>{n}</span>}</NavLink>;
}

export default function App() {
  return (
    <div className="mx-auto max-w-7xl p-4">
      <nav className="mb-4 flex items-center gap-2">
        <span className="mr-4 text-lg font-bold">My Collection</span>
        <NavLink to="/" end className={link}>Search</NavLink>
        <NavLink to="/collection" className={link}>Collection</NavLink>
        <NavLink to="/dashboard" className={link}>Dashboard</NavLink>
        <AlertsLink />
        <NavLink to="/settings" className={link}>Settings</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Search />} />
        <Route path="/cards/:id" element={<CardDetail />} />
        <Route path="/collection" element={<Collection />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </div>
  );
}
