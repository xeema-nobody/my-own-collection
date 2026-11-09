import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { refreshCardPrices } from "./CardFetch";
import { Button } from "./ui";

/** Catalog price of ONE card. Prices are stored only for tracked cards (collection + wishlist); an
 *  unpriced card says so and offers a one-card fetch (a user action, never automatic). */
export default function CatalogPrice({ card }: { card: any }) {
  const qc = useQueryClient();
  const go = useMutation({ mutationFn: () => api.refreshCardPrice(card.id), onSuccess: () => refreshCardPrices(qc, card.id) });
  const tracked = (card.owned?.length ?? 0) > 0;
  if (card.price_base != null && !go.isSuccess) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-line pb-3 text-sm">
      {go.isSuccess ? (
        <span className="text-muted">{go.data.found && go.data.prices > 0 ? "Catalog price fetched." : "The catalog has no price for this card."}</span>
      ) : (
        <>
          <span className="text-muted">{tracked ? "No catalog price yet." : "No price (not tracked): add it to the collection or wishlist, or fetch just this card."}</span>
          <Button variant="secondary" disabled={go.isPending} onClick={() => go.mutate()}>Fetch price</Button>
        </>
      )}
      {go.error && <span className="text-danger">{String(go.error instanceof Error ? go.error.message : go.error)}</span>}
    </div>
  );
}
