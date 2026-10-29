import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "./api";
import { companies, gradesOf, parseGrade } from "./grades";

/** Grade shown by the price matrix and chart, shared through `?grade=` so the card page is linkable. */
export function usePriceGrade(cardId: string) {
  const [sp, setSp] = useSearchParams();
  const matrix = useQuery({ queryKey: ["matrix", cardId], queryFn: () => api.priceMatrix(cardId) });
  const keys: string[] = matrix.data?.grades ?? ["raw"];
  const asked = sp.get("grade");
  const grade = asked && keys.includes(asked) ? asked : "raw";
  const setGrade = (g: string) => setSp((p) => { const n = new URLSearchParams(p); g === "raw" ? n.delete("grade") : n.set("grade", g); return n; }, { replace: true });
  const cos = companies(keys, matrix.data?.graders ?? []);
  const company = parseGrade(grade).company;
  const setCompany = (c: string) => setGrade(c === "Raw" ? "raw" : gradesOf(keys, c)[0] ?? "raw");
  return { matrix, keys, grade, setGrade, company, setCompany, companies: cos };
}
export type PriceGrade = ReturnType<typeof usePriceGrade>;
