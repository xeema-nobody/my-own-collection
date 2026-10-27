---
name: architecture-audit
description: >-
  Use when the user asks to analyze, review, or audit software architecture or
  design — separation of concerns, architectural pattern (MVC/Layered/
  Microservices), God objects/modules, dependency flow / circular dependencies,
  modularity rating, or anti-patterns (spaghetti, copy-paste, tight coupling,
  missing abstractions). Produces a structured findings report with per-finding
  severity (1-10) and concrete code-level remediations, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Architecture / Design Audit

Analyze the architecture of the codebase and write a structured findings report to
`audits/<topic>-analysis.md`. Evidence first, prose second.

## Procedure

1. **Map before judging.** Use Grep/Glob/Bash to find the real structure — entry points,
   modules, import edges, file/function sizes. Do NOT rely on memory or assumptions.
   - module list + LOC: `find . -name '*.py' -not -path './*venv/*' | xargs wc -l | sort -rn`
   - internal import graph (efferent/afferent coupling): grep the `import`/`from` lines
   - large files/functions = split candidates
2. **Evaluate** each of these and record concrete evidence (file:line, identifiers):
   - Separation of concerns — clear, partial, or fused?
   - Architectural pattern — MVC / Layered / Microservices / event-driven / other.
   - God objects/modules — one unit doing too much (CRUD + policy + IO).
   - Dependency flow — direction, and any **circular** imports.
   - Modularity rating **1-10** with justification.
3. **Diagram** the architecture in a fenced ASCII block: layer dependencies, data flow,
   external-service integrations, and likely bottlenecks.
4. **Identify anti-patterns** with locations: spaghetti, copy-paste programming, God
   classes/modules, tight coupling, missing abstractions.

## Output format (write to `audits/`)

A markdown file containing:
- **Header:** date, scope, method (what was scanned).
- **Architecture overview** + the ASCII diagram (layers, data flow, integrations, bottlenecks).
- **Separation-of-concerns verdict** and **Modularity score (1-10)** with a justification table.
- **Findings**, each with:
  - a stable id (F1, F2, …), the anti-pattern type, and exact `file:line` / identifier cites
  - **Severity 1-10** = how much it should weigh on remediation priority (10 = fix now)
  - **Remediation:** a minimal, drop-in code/config fix (snippet preferred over prose)
- **Anti-pattern scorecard** (present? + evidence) and a **prioritized remediation order**.

## Constraints & style (hard rules)

- Be concrete — cite exact code locations and identifiers, never vague areas.
- Prefer minimal, drop-in fix snippets over prose. Snippets must match current identifiers.
- Do **not** invent files or functions that aren't present. If context is missing, mark the
  finding **Unable to verify** and state exactly what code would prove it.
- Remediations should not change observable behavior unless the finding is a bug; if one
  does, say so explicitly.
- Audit only — write the report; do not refactor unless the user then says to proceed.
- Create the `audits/` directory if absent. Name the file for the topic
  (e.g. `software-design-analysis.md`).
