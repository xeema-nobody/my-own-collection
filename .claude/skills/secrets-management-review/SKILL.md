---
name: secrets-management-review
description: >-
  Use when the user asks to scan for exposed/hardcoded secrets or audit secrets
  management — hardcoded API keys, DB passwords, JWT/encryption keys, tokens;
  environment-variable and .env hygiene (.env not in git, prod vs dev configs);
  secret rotation capability; and encryption-key management (KDF, salt, storage).
  Produces a findings report with severity, CWE, remediation, risk score, and a
  Pass/Fail checklist, written to audits/. Hardcoded secrets are flagged CRITICAL.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Secrets Management Audit

Authorized defensive scan for exposed secrets and weak secret handling across the codebase
AND its git history surface. Write a report to `audits/secrets-management-analysis.md`. Cite
exact `file:line`. **Never print a real secret value — redact to `****` and cite location.**

## Scan (grep patterns + git)

- high-signal patterns:
  `grep -rnE '(api[_-]?key|secret|passwd|password|token|private[_-]?key|BEGIN .*PRIVATE KEY|aws_|client_secret)\s*[:=]' --include='*.*' . | grep -v -i 'example\|placeholder\|your_'`
- provider key shapes: `AKIA[0-9A-Z]{16}`, `AIza[0-9A-Za-z_-]{35}`, `sk_live_`, `ghp_`,
  `-----BEGIN`, long base64/hex literals assigned to a secret-looking name
- config & ignore files: `.env`, `*.json` creds, `service-account*.json`, `settings`,
  CI config; confirm `.env` / `*.json` keys are in `.gitignore`
- **git surface:** check whether secret files are tracked: `git ls-files | grep -Ei 'env|secret|cred|key|token'`; flag any committed secret file. (If deeper history scanning is
  warranted, recommend a dedicated tool — gitleaks/trufflehog — rather than guessing.)
- how secrets are LOADED at runtime: secret manager calls, `os.getenv`, config loaders.

## Check for

- **Hardcoded secrets** — API keys, DB passwords, JWT secrets, encryption keys, tokens
  embedded in source/committed files. **Any real hardcoded secret = CRITICAL.** (CWE-798
  hardcoded credentials; CWE-321 hardcoded crypto key)
- **Environment / secret-store usage** — secrets come from env vars or a secret manager, not
  code; `.env` is gitignored and not committed; prod vs dev configs separated; no secrets in
  CI logs/config.
- **Secret rotation capability** — can DB passwords / API keys / certs be rotated without a
  code change? Is there a documented/automated rotation path? Race-safety of rotation (a
  concurrent rotate must not destroy the live secret).
- **Encryption-key management** — KDFs used correctly; salts present and unique; keys stored
  in a KMS/secret manager not in code; key separation per environment. (CWE-320)

## Per-finding format (required)

**Title · Severity (Critical/High/Medium/Low) · CWE · Evidence(file, function, line ranges —
secret value REDACTED) · Why it matters · Exploitability (what the leaked secret grants; if
real & live, recommend immediate ROTATION as step 1) · Remediation (move to secret manager /
env, gitignore, rotate, snippet) + defense-in-depth.**

## Output (write to `audits/`)

- Header (date, scope, secret-loading mechanism identified, method = authorized self-review).
- **Findings** ordered by severity — hardcoded/committed secrets first.
- **Summary risk score 0-10** + **top 3-5 prioritized fixes** (rotation of any exposed live
  secret is always #1).
- **Checklist diff** — each "check for" item **Pass / Fail / N/A** + one-line reason.

## Constraints & style (hard rules)

- **Redaction is mandatory.** If you find a real secret, show only enough to locate it
  (`AKIA****`, last 4) — never the full value in the report.
- **A committed live secret is CRITICAL and the #1 remediation is ROTATE IT** (assume exposed
  = compromised), then remove from code/history, then move to a secret manager.
- Distinguish real secrets from placeholders/examples/test fixtures (`your_api_key`,
  `xxxx`, obvious dummies) — don't cry wolf, but flag anything that looks live.
- Credit good practice: secrets loaded from a secret manager at runtime, `.env` gitignored,
  per-env separation → Pass. Note rotation-race-safety where the code handles concurrent
  secret writes.
- Authorized DEFENSIVE review only. Do NOT exfiltrate, use, or validate found secrets against
  live services. Report + redact + recommend rotation.
- Be concrete — cite exact file:line; map to CWE (798/321/320).
- For deep git-history secret scanning, recommend gitleaks/trufflehog rather than asserting
  history is clean without checking — mark **Unable to verify** if history isn't scanned.
- Do **not** invent secrets or config. If secret loading isn't visible, mark **Unable to
  verify** and say what would prove it.
- Audit only — write the report; apply changes only when the user says to proceed.
- Create `audits/` if absent.
