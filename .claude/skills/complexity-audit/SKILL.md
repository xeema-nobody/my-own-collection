---
name: complexity-audit
description: >-
  Use when the user asks to analyze code complexity — cyclomatic complexity,
  cognitive complexity, nested if/else or loop depth, functions over 50 lines,
  files over 300 lines, coupling (afferent/efferent/instability), cohesion, or
  wants to find the most complex functions and refactoring candidates. Produces a
  structured findings report with measured metrics and code-level splits, written
  to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Code Complexity Audit

Measure complexity across the codebase and write a structured report to
`audits/complexity-analysis.md`. Use real tools for numbers — do NOT eyeball CC.

## Measure first (tools, not estimates)

Try to install/run measurement tools; if unavailable, fall back to manual counting and say so.
- **Cyclomatic + maintainability:** `radon cc -s -n C <paths>` and `radon mi -s <paths>`
- **Length / nesting / params (and warnings):** `lizard -w <paths>`
- **File LOC:** `wc -l` over the source tree (exclude venv/tests as noted).
- **Coupling:** grep the internal import graph — for each module count Ce (modules it imports)
  and Ca (modules importing it); Instability I = Ce / (Ca + Ce).

Quote the actual numbers in the report. If a tool can't run, mark that metric
**Unable to verify** and state which command would produce it.

## Evaluate

- **Cyclomatic** — functions with CC > 10; nested if/else depth; switch/dispatch ladders.
  Recommend a refactor for each (extract predicate list, strategy, registry, guard clauses).
- **Cognitive** — how hard to follow: nested loops/conditions, recursion, shared-mutable
  state across closures, mixed levels of abstraction in one function. (Note: a function can
  be cognitively hard yet have modest CC, esp. with closures — radon may report closures
  separately; flag and verify with lizard.)
- **LOC metrics** — functions > 50 lines, files > 300 lines, classes > 500 lines → split
  candidates.
- **Coupling** — report Ca / Ce / I per module; flag tightly-coupled or wrong-direction
  dependencies (unstable should depend on stable, per the Stable Dependencies Principle).
- **Cohesion** — are related functions grouped? Is policy split across files that should be
  together? Is each module single-focus?

## Output format (write to `audits/`)

- **Header:** date, scope, tooling used (radon/lizard versions or "manual").
- **Headline metrics tables:** CC offenders (fn | file:line | CC | rating | NLOC | length),
  files > 300 LOC, functions > 50 NLOC, classes > 500.
- **Findings** per area (cyclomatic, cognitive, LOC, coupling, cohesion), each with a stable
  id, exact `file:line` / identifier, **Severity 1-10** (10 = fix now), and a **drop-in
  refactor snippet** (extracted helpers / strategy list / guard clauses) with the measured
  before→after CC.
- A **coupling table** (module | Ca | Ce | I | verdict) and a **prioritized order** — note
  where one change clears multiple findings (e.g. a move that fixes a LOC, a coupling, and a
  cohesion finding at once).

## Constraints & style (hard rules)

- Numbers must be **measured**, not estimated; show the command/tool. Mark anything you
  couldn't measure **Unable to verify**.
- Be concrete — cite exact locations and identifiers.
- Prefer minimal, drop-in refactor snippets over prose; snippets must match current
  identifiers and be pure extraction (no behavior change) unless the finding is a bug.
- Do **not** invent files or functions. Classes > 500 in a function-oriented codebase = N/A,
  say so rather than forcing it.
- Audit only — write the report; refactor only when the user says to proceed.
- Create `audits/` if absent.
