---
name: logging-monitoring-review
description: >-
  Use when the user asks to review logging and monitoring — sensitive data leaking
  into logs (passwords, tokens, PII, API keys), security-event logging (failed
  logins, authz failures, validation failures, system errors), log-injection /
  forging prevention, structured logging, log storage/retention/rotation, and
  monitoring alerts (anomaly detection, error-rate, performance). Produces a
  findings report + logging compliance checklist with severity, CWE, PoC,
  remediation, risk score, and Pass/Fail, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Logging & Monitoring Review

Authorized defensive review of what gets logged, how, where, and what's monitored. Write a
report to `audits/logging-monitoring-analysis.md`. Cite exact `file:line`.

## First: inventory the logging

Grep every log/print site and what it interpolates:
`grep -rn 'print(\|logging\.\|logger\.\|console\.' --include='*.py' .` (+ language equivalents).
For each, note: level, message, and the variables interpolated (the leak risk is in the
interpolated values). Identify the logging mechanism (stdlib logger vs bare `print`), and
whether logs are structured.

## Check for

- **Sensitive data not logged** — no passwords, tokens, refresh tokens, API keys, secrets,
  credit-card/PII, full auth headers, or raw request bodies in log output. Watch for
  exception logs that dump a credential-bearing object, and "debug" dumps of tokens/config.
  (CWE-532 info exposure through logs; CWE-312 cleartext storage)
- **Security-event logging** — failed logins, authorization failures, input-validation
  failures, and system errors ARE logged (with enough context to investigate, without the
  secret). Absence of security logging is itself a finding. (CWE-778 insufficient logging)
- **Log injection / forging prevention** — user-controlled input written into logs is
  sanitized/escaped (newline/CRLF stripped) so an attacker can't forge log lines or break
  parsers. Structured logging (key/value/JSON) preferred over string concatenation. (CWE-117)
- **Storage & retention** — logs stored securely, rotation policy, retention/backup, access-
  controlled; PII retention bounded.
- **Monitoring & alerts** — unusual-activity detection, error-rate monitoring, performance
  anomalies, alerting on security events (e.g. repeated auth failure, token-reuse). Note where
  the platform (Cloud Logging/Monitoring, Sentry, etc.) provides this.

## Per-finding format (required)

**Title · Severity (Critical/High/Medium/Low) · CWE · Evidence(file, function, line ranges) ·
Why it matters · Exploitability (+ safe PoC / repro — e.g. "a username containing `\n` forges a
second log line"; placeholders, never a real secret) · Remediation (snippet + defense-in-depth).**

## Output (write to `audits/`)

- Header (date, scope, logging mechanism identified, method = authorized self-review).
- **Findings** in the format above, ordered by severity (secret-leak first).
- **Summary risk score 0-10** + **top 3-5 prioritized fixes**.
- **Logging compliance checklist** — each "check for" item **Pass / Fail / N/A** + one-line
  reason; include a short "what to log vs never log" table for this app.

## Constraints & style (hard rules)

- The two highest-value checks: **secrets/PII in logs** (high/critical) and **security events
  NOT logged** (a gap, not just style). Grep specifically for logging of token/secret/
  credential variables and of full request/response objects.
- Distinguish a deliberate, safe operational log (status, ids, counts) from a leak. Don't flag
  benign logs; DO flag any interpolation of a secret/PII/credential.
- For log injection: any time **user-controlled text** (filename, username, payload field) is
  logged unescaped, flag it (CRLF → forged lines / broken structured logs).
- Account for the platform: storage/rotation/retention/alerting may be handled by the runtime
  (Cloud Logging, log router, SIEM) — mark such items **N/A / enforced-by-platform** with
  where, not **Fail**. But app-side redaction is still the app's job.
- If the app uses bare `print()` instead of a logger, note the limitation (no levels, no
  redaction hook, no structured fields) and recommend a logger with a redaction filter.
- Authorized DEFENSIVE review only. PoCs are placeholder repro steps; never print real secrets
  — redact (`****`) and cite location.
- Be concrete — cite exact log statements/identifiers; map to CWE.
- Prefer minimal, drop-in fix snippets (redaction filter, sanitized log call, structured field).
- Do **not** invent log sites or config. If retention/monitoring config isn't visible, mark
  **Unable to verify** and state what would prove it.
- Audit only — write the report; apply changes only when the user says to proceed.
- Create `audits/` if absent.
