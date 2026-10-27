---
name: database-security-review
description: >-
  Use when the user asks to audit database / datastore security — SQL/NoSQL
  injection (string-concatenated queries, raw operators), connection-string &
  secret handling, least-privilege DB accounts, encryption at rest & in transit
  (TLS), PII handling, query timeouts & connection pools, transactions, row/tenant
  isolation, audit logging, migrations safety, backup security, pagination caps,
  and caching of sensitive data. Produces a findings report with severity, CWE,
  PoC, remediation, risk score, and a Pass/Fail checklist, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Database / Datastore Security Audit

Authorized defensive review of ALL data-store interactions. Write a report to
`audits/database-security-analysis.md`. Cite exact `file:line`. "Datastore" includes SQL,
NoSQL, and managed stores (e.g. Secret Manager, Drive/object storage, Firestore) — map the
checklist to whatever this project actually uses.

## First: find every data interaction

Grep query builders / drivers / ORMs / clients: `execute`, `query`, `raw`, `cursor`, `.find(`,
`SELECT`, `INSERT`, f-string/`+`/`%`/`.format` near SQL, `mongoose`/`prisma`/`sqlalchemy`/
`knex`, and managed-store clients. List each call site, its inputs, and where they come from.

## Check for (review those that apply)

- **Parameterized queries / ORM bindings** — placeholders (`?`,`$1`,`:p`) or ORM bindings
  everywhere. **Direct string concatenation / f-strings of user input into a query =
  CRITICAL** (CWE-89). NoSQL: raw user JSON into filters, `$where`/`$ne`/`$gt`/`$or` operator
  injection = **CRITICAL** (CWE-943). Audit every raw escape hatch (`queryRaw`, `.raw`,
  `session.execute(text(...))`).
- **Connection-string / secret security** — no hardcoded passwords/DSNs in code or git; use
  env/secret manager. (CWE-798)
- **Least privilege** — app account has only needed rights (no SUPERUSER/DROP/GRANT); separate
  read-only / migration / admin accounts.
- **Encryption at rest** — disk/db-native encryption; column-level/tokenization for sensitive
  fields; sensitive fields not indexed in plaintext.
- **TLS in transit** — `sslmode=require/verify-full` or equivalent; cert validation + rotation.
- **PII handling** — minimized, redacted in logs/metrics/ORM-debug, retention/deletion policy;
  GDPR/CCPA only if applicable (else N/A).
- **Query timeouts & resource guards** — statement timeouts at driver + server; caps to
  prevent expensive-query DoS. (CWE-770)
- **Connection pool** — bounded min/max, idle timeout, no unbounded connections.
- **Transactions** — multi-step ops wrapped; rollback paths exist/tested (no partial updates).
- **Row/tenant isolation** — RLS or server-side ownership/tenant filters; never client-scoped.
- **Audit logging** — sensitive-table access, schema/permission changes, failed logins;
  centralized, immutable, monitored.
- **Migrations safety** — controlled privileges; destructive ops reviewed; rollback plan.
- **Schema integrity** — FKs, unique constraints, NOT NULL; tenant/owner columns NOT NULL.
- **Field minimization & pagination** — avoid `SELECT *`; hard LIMIT/page caps.
- **LIKE/regex input** — escape `%`,`_`, regex metacharacters.
- **Backup/restore** — encrypted, access-controlled, restore-tested; no unprotected dumps in
  CI/object storage.
- **Networking** — store not publicly exposed; VPC/ACL/firewall; only app servers connect.
- **Secret rotation & account lifecycle** — rotated creds; no shared admin; purpose-specific
  service accounts; periodic privilege review.
- **Caching & ETL** — sensitive data not cached plaintext; cache requires auth/not exposed;
  exports masked/de-identified, encrypted.

## Per-finding format (required)

**Title · Severity (Critical/High/Medium/Low) · CWE · Evidence(file, function, line ranges) ·
Why it matters · Exploitability (+ safe PoC / repro, placeholders — e.g. a benign payload that
demonstrates concatenation, never a destructive one) · Remediation (snippet + defense-in-depth).**

## Output (write to `audits/`)

- Header (date, scope, datastores identified, method = authorized self-review).
- **Findings** in the format above, ordered by severity (CRITICAL injection first).
- **Summary risk score 0-10** + **top 3-5 prioritized fixes**.
- **Checklist diff** — each "check for" item **Pass / Fail / N/A** + one-line reason.

## Constraints & style (hard rules)

- **CRITICAL flags, no softening:** string-concatenated queries, and raw-user-input NoSQL
  filters/operators. Call them Critical with the exact concatenation site.
- Map the checklist to the ACTUAL store. If the project has no SQL/NoSQL DB (e.g. uses a
  managed Secret Manager + object storage), mark SQL/NoSQL items **N/A** and audit the
  managed-store equivalents (IAM least-privilege, encryption, access scope, secret rotation,
  injection into store queries).
- Authorized DEFENSIVE review only. PoCs are placeholder, non-destructive repro steps — never
  `DROP`/`DELETE` payloads or attacks on real data. Never print real secrets/DSNs — redact.
- Be concrete — cite exact locations/identifiers; map to CWE (89 SQLi, 943 NoSQLi, 798
  hardcoded creds, 311/312 missing/cleartext encryption, 770 missing limits).
- Prefer minimal, drop-in fix snippets (parameterized version of the exact query); match the
  real driver/ORM.
- Credit infra-enforced controls (managed encryption, IAM, private networking) as
  N/A-enforced-by-infra, not Fail.
- Do **not** invent tables/queries/config. If DB config (TLS, grants, pool) isn't visible,
  mark **Unable to verify** and state what would prove it.
- Audit only — write the report; apply changes only when the user says to proceed.
- Create `audits/` if absent.
