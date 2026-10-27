---
name: solid-review
description: >-
  Use when the user asks to evaluate or audit code against the SOLID principles —
  Single Responsibility (SRP), Open/Closed (OCP), Liskov Substitution (LSP),
  Interface Segregation (ISP), or Dependency Inversion (DIP) — or asks about
  responsibilities, polymorphism vs if/else chains, fat interfaces, abstractions
  vs concretions, or dependency injection. Produces a structured findings report
  with a SOLID compliance score and code-level fixes, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# SOLID Principles Review

Audit the codebase against the five SOLID principles and write a structured report to
`audits/solid-principles-analysis.md`. Evidence first; cite exact `file:line` / identifiers.

## Adapt to the language

SOLID is class-oriented. In function-oriented or non-OO code, map each principle to its
analogue and SAY you are doing so:
- module = unit of responsibility (SRP)
- function / parameter list = interface (ISP)
- import edge / direct instantiation = dependency (DIP); the `new`/`build()`/global-singleton
  equivalent is the concretion smell
- few/no class hierarchies → LSP is often **N/A**; say so rather than inventing violations.

## Check each principle (record concrete evidence)

- **SRP** — does each module/class have one reason to change? Flag units doing unrelated
  jobs (e.g. a controller handling emails + payments + auth; a function doing IO + policy +
  formatting).
- **OCP** — can behavior be extended without modifying existing code? Flag hardcoded
  switch/if-else dispatch ladders that should be polymorphism / a strategy list / a registry.
- **LSP** — do derived classes honor the base contract (no surprise exceptions, weakened
  postconditions, narrowed inputs)? If no real hierarchy exists, mark **N/A** with why.
- **ISP** — are interfaces/params too fat? Do clients depend on methods/objects they don't
  use (e.g. taking a whole god-object to call one method)? Suggest a narrow Protocol/interface.
- **DIP** — do high-level modules depend on abstractions or concretions? Is there injection,
  or are collaborators hardcoded (`new X()`, `build()`, module-global singletons, direct
  library calls)? Check for a seam.

## Output format (write to `audits/`)

- **Header:** date, scope, method, and (if non-OO) the principle→analogue mapping.
- **Overall SOLID compliance score 1-10** + a per-principle score table with one-line verdicts.
- **Findings per principle**, each with a stable id, exact `file:line` / identifier cites,
  **Severity 1-10** (10 = fix now), and a **minimal drop-in remediation snippet**.
- Call out **positives** too (good OCP/DIP examples) so the report is balanced.
- A **prioritized remediation order** and recommended sequence.

## Constraints & style (hard rules)

- Be concrete — cite exact locations and identifiers, never vague areas.
- Prefer minimal, drop-in fix snippets over prose; snippets must match current identifiers.
- Do **not** invent files or functions. If context is missing, mark the finding
  **Unable to verify** and state what code would prove it. LSP with no hierarchy is N/A,
  not a fabricated violation.
- Remediations introduce a seam (strategy list, port, Protocol, factory) and should keep the
  default wiring identical — no observable behavior change unless the finding is a bug.
- Audit only — write the report; do not refactor unless the user then says to proceed.
- Create `audits/` if absent.
