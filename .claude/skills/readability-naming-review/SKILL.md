---
name: readability-naming-review
description: >-
  Use when the user asks to review code readability and naming — descriptive vs
  cryptic names, verb-based functions / noun-based classes, UPPER_CASE constants,
  underscore-private convention, camelCase vs snake_case consistency, abbreviation
  and domain-term usage, magic numbers/strings, complex booleans, ternary abuse,
  comment smell, and function signatures (param count, boolean params, return
  clarity). Produces a findings report + a naming-convention guide, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Readability & Naming Review

Review naming and readability across the codebase and write a report to
`audits/readability-naming-analysis.md`. Cite exact `file:line` / identifiers for every claim.

## Find the issues (grep first)

- single/double-char or cryptic names: locals like `u`, `df`, `tmp`, `x` in non-trivial scope
- magic numbers/strings: bare numeric literals and repeated string literals in logic
- naming-style mixing: camelCase vs snake_case (`grep -rnE '[a-z]+[A-Z][a-z]'` for camelCase
  in a snake_case codebase), inconsistent abbreviations
- long parameter lists / boolean params: `def f(..., flag: bool ...)`, 4+ params
- complex booleans / nested ternaries: long `and/or` chains, `x if a else y if b else z`
- comment smell: dense block comments explaining *what* (vs *why*); commented-out code

## Review areas

- **Naming conventions** — variables descriptive (not cryptic); functions verb-based with
  clear intent; classes noun-based, single responsibility; constants UPPER_CASE; private
  helpers `_underscore`-prefixed.
- **Naming consistency** — one case style (respect the language default: snake_case for
  Python); consistent abbreviations; consistent domain terminology; consistent spelling
  (British vs American — pick one).
- **Readability** — is the code self-documenting? Are comments compensating for unclear
  names (smell)? Magic numbers/strings that should be named constants. Complex boolean
  expressions that should be extracted to a named predicate. Ternary abuse.
- **Function signatures** — parameter count (>3 is a smell → group into an object/params);
  boolean parameters (prefer an enum / two functions / keyword-only); optional-param
  handling; return-type clarity (and tuple returns that should be named).

## Output (write to `audits/`)

- **Header:** date, scope, method.
- **Findings table:** id | area | location | current → suggested | severity.
- **Findings**, each with a stable id, exact `file:line` / identifier, **Severity 1-10**
  (10 = fix now), and a **minimal drop-in rename/extract snippet** (old → new).
- A **naming-convention guide** derived from the findings: the rules this codebase should
  follow (case style, prefixes, constant policy, abbreviation list, param/boolean rules),
  written as a short adoptable standard — reflecting existing good practice where present.

## Constraints & style (hard rules)

- Be concrete — cite exact identifiers and locations; show `current → suggested`, never
  "use better names" in the abstract.
- Respect context: a short name in a tiny well-scoped lambda/comprehension is fine; a domain
  abbreviation that is standard in the codebase (cite it) is not a defect. Don't churn names
  that are already clear.
- Severity should weight reader-confusion and bug-risk (e.g. a misleading name) above pure
  style nits.
- Prefer minimal, drop-in snippets over prose; renames must be consistent across all call
  sites — note that a rename touches every usage.
- Do **not** invent files or functions. If intent is genuinely unclear from the code, mark
  **Unable to verify** and state what would clarify it.
- Audit only — write the report + guide; apply renames only when the user says to proceed.
- Create `audits/` if absent.
