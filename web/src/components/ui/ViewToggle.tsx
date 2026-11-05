import { LayoutGrid, Table2 } from "lucide-react";
import { SegmentedControl } from "./Tabs";

export type View = "table" | "grid";
export const VIEWS: readonly View[] = ["table", "grid"];

/** Table | image grid switch for list pages. */
export function ViewToggle({ value, onChange }: { value: View; onChange: (v: View) => void }) {
  return <SegmentedControl label="View" value={value} onChange={onChange} options={[
    { value: "table", label: <span className="inline-flex items-center gap-1"><Table2 size={12} />Table</span> },
    { value: "grid", label: <span className="inline-flex items-center gap-1"><LayoutGrid size={12} />Grid</span> }]} />;
}
