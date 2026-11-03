/** Price-matrix grade keys: "raw", "G9.5" (company-agnostic bucket), "PSA10", "CGC10Pristine", "BGS10Black". */
export type ParsedGrade = { company: string; grade: string };
const BUCKET = /^G(\d+(?:\.\d+)?)$/;
const COMPANY = /^([A-Za-z]+?)(\d+(?:\.\d+)?)(.*)$/;

export function parseGrade(key: string): ParsedGrade {
  if (key === "raw") return { company: "Raw", grade: "" };
  const b = BUCKET.exec(key);
  if (b) return { company: "Any", grade: b[1] };
  const m = COMPANY.exec(key);
  return m ? { company: m[1].toUpperCase(), grade: m[2] + m[3] } : { company: "Other", grade: key };
}

/** "PSA10" -> "PSA 10", "G9" -> "9 (any grader)". */
export const gradeLabel = (key: string) => {
  const p = parseGrade(key);
  return p.company === "Raw" ? "Raw" : p.company === "Any" ? `${p.grade} (any grader)` : `${p.company} ${p.grade}`;
};

const num = (g: string) => parseFloat(g) || 0;

/** Segments for the company selector: Raw and Any always, then graders that have data in `graders` order. */
export function companies(keys: string[], graders: string[] = []): string[] {
  const have = new Set(keys.map((k) => parseGrade(k).company));
  return ["Raw", "Any", ...graders.filter((g) => have.has(g.toUpperCase())).map((g) => g.toUpperCase())];
}

/** Grade keys of one company, best grade first (10 before 10Pristine before 9.5). */
export function gradesOf(keys: string[], company: string): string[] {
  return keys.filter((k) => parseGrade(k).company === company)
    .sort((a, b) => num(parseGrade(b).grade) - num(parseGrade(a).grade) || parseGrade(a).grade.localeCompare(parseGrade(b).grade));
}

/** Sort order for grade keys: Raw first, then company A-Z, best grade first within a company. */
export function compareGrades(a: string, b: string): number {
  const pa = parseGrade(a), pb = parseGrade(b);
  if ((pa.company === "Raw") !== (pb.company === "Raw")) return pa.company === "Raw" ? -1 : 1;
  return pa.company.localeCompare(pb.company) || num(pb.grade) - num(pa.grade) || pa.grade.localeCompare(pb.grade);
}
