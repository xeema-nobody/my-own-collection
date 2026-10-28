// Read-only: explain() the card-search query shapes. Prints ms / docs examined / keys examined.
// Usage: docker compose exec -T mongo sh -c 'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" \
//   --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin' < scripts/perf_explain.js
// Bar (docs/architecture.md): every path < 250 ms at 20k cards.
const d = db.getSiblingDB("owncollection");
const REL = { "set.release_date": -1, "set.id": 1, number_sort: 1 };
function ex(label, flt, sort) {
  let c = d.cards.find(flt, { raw: 0 });
  if (sort) c = c.sort(sort);
  const e = c.limit(60).explain("executionStats").executionStats;
  print(label.padEnd(28), "ms=" + String(e.executionTimeMillis).padStart(4),
        "docs=" + String(e.totalDocsExamined).padStart(6), "keys=" + String(e.totalKeysExamined).padStart(6),
        "n=" + e.nReturned);
}
print("cards", d.cards.countDocuments({}));
ex("regex one token", { search_text: { $regex: "char" } });
ex("regex two tokens", { $and: [{ search_text: { $regex: "charizard" } }, { search_text: { $regex: "vstar" } }] });
ex("regex no match", { search_text: { $regex: "zzzz" } });
ex("all, sort release", {}, REL);
ex("all, sort name", {}, { name_norm: 1 });
ex("set filter, sort number", { "set.id": "sv3pt5" }, REL);
ex("tcg+rarity", { tcg: "pokemon", rarity: "Rare Holo" }, REL);
ex("sort price desc", {}, { price_base: -1, _id: 1 });
ex("has price", { price_base: { $ne: null } }, REL);
ex("price range", { price_base: { $gte: 1000, $lte: 5000 } }, { price_base: -1, _id: 1 });
ex("external id", { external_id: "base1-4" });
ex("number + printed total", { $and: [{ number: { $regex: "^0*4$", $options: "i" } }, { "set.printed_total": 102 }] });
print("indexes", JSON.stringify(d.cards.getIndexes().map((i) => i.name)));
