import { Link } from "react-router-dom";
import { Card } from "../components/ui";

export default function NotFound() {
  return <Card className="space-y-2"><h2 className="font-semibold">Page not found</h2>
    <Link className="underline" to="/">Back to search</Link></Card>;
}
