---
name: input-validation-review
description: >-
  Use when the user asks to review input validation / injection defenses across
  the app — SQL injection, NoSQL injection ($where/$ne/$gt), command injection
  (child process / system calls), XSS (sanitization, output encoding), XXE (XML
  parsing), path traversal (file ops), and request validation (body size limits,
  parameter pollution, type checking, required fields). Produces a per-endpoint
  validation matrix + findings report with severity, CWE, PoC, remediation, risk
  score, and a Pass/Fail checklist, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Input Validation & Injection Review

Authorized defensive review of how untrusted input is validated/sanitized at every entry
point. Write a report to `audits/input-validation-analysis.md`. Cite exact `file:line`.

## First: enumerate untrusted-input entry points

List every place external data enters: HTTP routes (path/query/body/headers), webhook/Pub-Sub
payloads, file contents, env/CLI args, message-queue data. For each, trace input → validation
→ sink (query, shell, file path, response, parser). The sink is where injection lands.

## Check for

- **SQL injection** — raw SQL without parameterization, dynamic query building, string-
  concatenated queries, unsafe stored-proc calls. (CWE-89)
- **NoSQL injection** — unvalidated query operators (`$where`,`$ne`,`$gt`,`$or`), raw user JSON
  into filters, JS execution in queries. (CWE-943)
- **Command injection** — `subprocess`/`os.system`/`exec`/`child_process` with user-influenced
  args; `shell=True` + interpolation. (CWE-78)
- **XSS** — unescaped user input reflected/stored into HTML/JS; missing output encoding;
  missing/incorrect `Content-Type`. (CWE-79)
- **XXE** — XML parsers with external entities / DTDs enabled; user-supplied XML/SVG/docs.
  (CWE-611)
- **Path traversal** — user input in file paths (`open`, read/write, download dest, archive
  extract) without sanitization; `..`/absolute-path/null-byte. (CWE-22)
- **Request validation** — body/payload size limits, parameter pollution (duplicate params),
  type checking, required-field & schema validation, allowlist of expected fields.

## Validation matrix (required deliverable)

A table: **endpoint/entry point | inputs | validation present (type/size/schema/sanitize) |
sink | status (Pass/Partial/Fail)**. One row per entry point so gaps are obvious at a glance.

## Per-finding format (required)

**Title · Severity (Critical/High/Medium/Low) · CWE · Evidence(file, function, line ranges) ·
Why it matters · Exploitability (+ safe PoC / repro — a benign demonstrative payload with
placeholders, never a destructive or live one) · Remediation (snippet + defense-in-depth).**

## Output (write to `audits/`)

- Header (date, scope, entry points identified, method = authorized self-review).
- The **validation matrix**.
- **Findings** in the format above, ordered by severity (injection-to-dangerous-sink first).
- **Summary risk score 0-10** + **top 3-5 prioritized fixes**.
- **Checklist diff** — each "check for" item **Pass / Fail / N/A** + one-line reason.

## Constraints & style (hard rules)

- Validate at the SINK, not just the edge: trace each input to where it's used and check the
  defense there (parameterized query, escaped path, encoded output, safe parser config).
- Map the checklist to what the app actually has. No HTML rendering → XSS likely **N/A**; no
  XML parsing → XXE **N/A**; no SQL/NoSQL DB → those **N/A** (but still review the real sinks:
  Drive query-string building, shell calls, file-path/download handling, image parsing).
- Pay attention to less-obvious sinks in this codebase class: **query-string assembly for an
  API** (escape user values in `name=` filters), **download destination paths** (a malicious
  filename → path traversal in the local temp dir), and **`subprocess`/tool invocation**.
- Authorized DEFENSIVE review only. PoCs are benign, placeholder demonstrations; never produce
  working exploit payloads or attacks on third parties. Never print real secrets.
- Be concrete — cite exact locations/identifiers; map to CWE.
- Prefer minimal, drop-in fix snippets (the parameterized/escaped version of the exact sink);
  match the real stack.
- Credit infra-enforced controls (platform body-size cap, WAF, private OIDC endpoints) as
  N/A-enforced-by-infra, not Fail — but app-layer sink defenses are still required.
- Do **not** invent endpoints or sinks. If a sink's handling isn't visible, mark **Unable to
  verify** and state what code would prove it.
- Audit only — write the report; apply changes only when the user says to proceed.
- Create `audits/` if absent.
