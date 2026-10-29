import { gradesOf, parseGrade } from "../lib/grades";
import { SegmentedControl } from "./ui";
import type { PriceGrade } from "../lib/priceGrade";

/** Company (Raw | Any | PSA …) then grade; shared by the price matrix and the chart. */
export default function GradeSelector({ pg }: { pg: PriceGrade }) {
  const grades = pg.company === "Raw" ? [] : gradesOf(pg.keys, pg.company);
  return (
    <div className="flex flex-wrap items-center gap-3">
      <SegmentedControl label="Grader" value={pg.company} onChange={pg.setCompany} options={pg.companies.map((c) => ({ value: c, label: c }))} />
      {grades.length > 0 && <SegmentedControl label="Grade" value={pg.grade} onChange={pg.setGrade}
        options={grades.map((g) => ({ value: g, label: parseGrade(g).grade }))} />}
    </div>);
}
