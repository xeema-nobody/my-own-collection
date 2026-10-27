import { NavLink, Route, Routes } from "react-router-dom";
import Search from "./pages/Search";
import CardDetail from "./pages/CardDetail";
import Collection from "./pages/Collection";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded text-sm ${isActive ? "bg-indigo-600 text-white" : "hover:bg-slate-200 dark:hover:bg-slate-700"}`;

export default function App() {
  return (
    <div className="mx-auto max-w-7xl p-4">
      <nav className="mb-4 flex items-center gap-2">
        <span className="mr-4 text-lg font-bold">My Collection</span>
        <NavLink to="/" end className={link}>Search</NavLink>
        <NavLink to="/collection" className={link}>Collection</NavLink>
        <NavLink to="/dashboard" className={link}>Dashboard</NavLink>
        <NavLink to="/settings" className={link}>Settings</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Search />} />
        <Route path="/cards/:id" element={<CardDetail />} />
        <Route path="/collection" element={<Collection />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </div>
  );
}
