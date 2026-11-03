import { QueryError } from "../components/QueryState";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import PriceChart from "../components/PriceChart";
import PriceMatrix from "../components/PriceMatrix";
import CardFetch from "../components/CardFetch";
import SourceStatus from "../components/SourceStatus";
import SalesList from "../components/SalesList";
import { CompareCopies } from "../components/SourceCompare";
import CardCollection from "../components/CardCollection";
import CardWishlist from "../components/CardWishlist";
import { Section } from "../components/ui";
import { usePriceGrade } from "../lib/priceGrade";


export default function CardDetail() {
  const id = decodeURIComponent(useParams().id!);
  const card = useQuery({ queryKey: ["card", id], queryFn: () => api.card(id) });
  const matches = useQuery({ queryKey: ["match", id], queryFn: () => api.cardMatches(id) });
  const owned = useQuery({ queryKey: ["owned-values", id], queryFn: () => api.ownedItems(id) });
  const rawCompare = useQuery({ queryKey: ["compare", id], queryFn: () => api.cardCompare(id) });
  const pg = usePriceGrade(id);

  if (card.isLoading) return <p>Loading…</p>;
  if (card.error) return <QueryError q={card} label="Card" />;
  const c = card.data;

  return (
    <div className="grid gap-8 md:grid-cols-[340px_1fr]">
      <img src={c.images?.large} alt={c.name} className="w-full max-w-sm self-start rounded-lg shadow-card md:sticky md:top-20" />
      <div className="max-w-5xl space-y-5">
        <div><h1 className="text-3xl font-semibold tracking-tight">{c.name}</h1>
          <p className="text-muted">{c.set?.name} · #{c.number}/{c.set?.printed_total} · {c.rarity} · {c.types?.join(", ")}</p>
          {c.flavor_text && <p className="mt-1 text-sm italic">{c.flavor_text}</p>}</div>

        <Section title="Prices" collapsible id="card-prices">
          <CardFetch cardId={id} />
          <h3 className="mb-1 text-sm font-semibold">Compare sources</h3>
          <div className="mb-3">
            {rawCompare.data ? <CompareCopies matches={matches.data} copies={[
              { label: "Raw copy", row: rawCompare.data },
              ...(owned.data?.items ?? []).filter((i: any) => i.grading).map((i: any) =>
                ({ label: `Owned: ${i.grading.company} ${i.grading.grade} × ${i.quantity}`, row: i }))]} />
              : <p className="text-sm text-muted">Loading…</p>}
          </div>
          <PriceMatrix pg={pg} />
        </Section>

        <Section title="Sources" collapsible id="card-sources" defaultOpen={false}><SourceStatus cardId={id} sales={c.sales ?? []} /></Section>

        <SalesList sales={c.sales ?? []} stats={c.sales_stats ?? []} />

        <Section title="Price history" collapsible id="card-history"><PriceChart cardId={id} pg={pg} /></Section>

        <CardCollection card={c} />
        <CardWishlist card={c} />
      </div>
    </div>
  );
}
