import { Link } from "react-router-dom";

export default function NotFound() {
  return <div className="card space-y-2"><h2 className="font-semibold">Page not found</h2>
    <Link className="underline" to="/">Back to search</Link></div>;
}
