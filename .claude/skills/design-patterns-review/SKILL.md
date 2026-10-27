---
name: design-patterns-review
description: >-
  Use when the user asks to review or evaluate design pattern usage — creational
  (Singleton, Factory, Builder), structural (Adapter, Facade, Decorator, Proxy),
  behavioral (Strategy, Observer, Chain of Responsibility, Command), or domain
  patterns (Repository, Service layer, DTO/Value object, Domain model) — whether
  patterns are appropriate, correctly implemented, over-engineered, or missing.
  Produces a structured findings report with code-level fixes, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Design Pattern Review

Review how design patterns are used (and misused, and missing) across the codebase and write
a structured report to `audits/design-patterns-analysis.md`. Cite exact `file:line`.

## Find the patterns (grep for the tells)

Don't assume — locate concrete evidence. Useful tells:
- Singleton: module-global `_instance`/`None` guard, `get_*_client()` memoization
- Factory: `*_factory`, functions returning constructed objects, `build(...)`, `create_*`
- Builder: step-by-step assembly, fluent/chained construction
- Adapter: wrappers around third-party SDKs translating their API to yours
- Facade: a thin module exposing a simplified surface over several subsystems (e.g. a shim)
- Decorator: `@decorator`, middleware wrapping, FastAPI/Flask route wrappers
- Proxy: lazy loading, caching layers, deferred init
- Strategy: a list/registry of interchangeable callables; what replaced an if/else ladder
- Observer / pub-sub: event emit/subscribe, webhook → queue → handler
- Chain of Responsibility: ordered handlers each given a chance to handle
- Command: queued/serialized actions, task objects
- Repository / Service layer / DTO / Domain model: data-access abstractions, value objects

## Evaluate each pattern found

For every instance, answer:
1. **Appropriate?** Does the use case justify it, or is it ceremony?
2. **Correct?** Implemented properly (e.g. Singleton thread-safe? Factory truly inverting
   construction? Adapter actually isolating the third party)?
3. **Simpler alternative?** Could a plain function / stdlib feature do the same with less?
4. **Missing patterns** — where would introducing one genuinely improve the code (e.g. a
   Strategy to kill a dispatch ladder, a Repository to isolate data access, a Protocol/port
   for DIP)?

## Output format (write to `audits/`)

- **Header:** date, scope, method.
- **Pattern inventory table:** pattern | location(s) | appropriate? | correct? | verdict.
- **Findings**, each with a stable id, exact `file:line` / identifier, **Severity 1-10**
  (10 = fix now), and a **minimal drop-in code example** for the fix or the new pattern.
- A **"missing patterns"** section and an **"over-engineering"** section (patterns to remove
  in favor of something simpler) — both matter.
- **Prioritized recommendations.**

## Constraints & style (hard rules)

- Be concrete — name the pattern AND cite exact locations/identifiers. No hand-waving.
- Prefer minimal, drop-in snippets over prose; snippets must match current identifiers.
- Do **not** invent files or functions. If a pattern is absent, say "not present" — do not
  pretend to find one. If context is missing, mark **Unable to verify** and state what code
  would prove it.
- Recommend the SIMPLEST thing that works — flag patterns applied where a plain function
  suffices; don't recommend a pattern just to have one.
- Fixes should keep observable behavior unless the finding is a bug; say so if one changes it.
- Audit only — write the report; refactor only when the user says to proceed.
- Create `audits/` if absent.
