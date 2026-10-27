---
name: resilience-review
description: >-
  Use when the user asks to evaluate system resilience / fault tolerance —
  timeout handling (HTTP, DB query, long-running ops), retry logic (exponential
  backoff, max retries, idempotency), circuit breakers, the bulkhead pattern
  (resource/thread/connection-pool isolation), and graceful degradation (feature
  flags, fallback data sources, cached responses, default values). Produces a
  findings report with a resilience score and code/config fixes, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Resilience / Fault-Tolerance Review

Assess how the system survives partial failure and overload. Write a report to
`audits/resilience-analysis.md`. Cite exact `file:line` / config keys.

## Find the resilience surfaces (grep + config)

- timeouts: `timeout=`, `--timeout`, request/client timeouts, deadline settings, default
  (often infinite) timeouts on HTTP/SDK/DB calls
- retries: retry loops, backoff math, `max_retries`, queue redelivery, scheduler attempt
  limits; whether the retried operation is idempotent
- circuit breaker: failure-count thresholds, open/half-open state, fallbacks on repeated fail
- bulkhead: thread pools, connection-pool sizes, concurrency caps, per-instance limits,
  isolation between workloads
- degradation: feature flags, cached/last-known-good responses, fallback sources, default
  values, "skip and continue" on a non-critical failure
- also check infra/deploy config (Cloud Run/k8s/etc): instance min/max, concurrency, CPU,
  request timeout, scaling — resilience often lives there, not just in code.

## Evaluate each area

- **Timeout handling** — does every outbound call (HTTP, DB/datastore, third-party SDK) have
  a bounded timeout? Long-running ops capped? Flag any unbounded call.
- **Retry logic** — exponential backoff present? max-retry limit? is the retried action
  idempotent (or guarded so a retry can't double-apply)? Flag retry-without-idempotency and
  retry-storm risk (no cap / too-aggressive).
- **Circuit breaker** — is repeated downstream failure detected and short-circuited with a
  fallback, or does every request keep hammering a dead dependency? If absent but warranted,
  recommend one (or a simpler equivalent).
- **Bulkhead** — are resources isolated so one slow/failing workload can't exhaust the pool
  shared by others? Check connection/thread/instance limits.
- **Graceful degradation** — on dependency failure, does the system degrade (cache, default,
  fallback) or hard-fail? Note where a soft path would help.

## Output (write to `audits/`)

- **Header:** date, scope, method (incl. infra config inspected).
- **Resilience score 1-10** with justification + a per-area table (timeout/retry/CB/bulkhead/
  degradation: present? adequate?).
- **Findings**, each with a stable id, exact `file:line` / config key, **Severity 1-10**
  (10 = fix now), and a **minimal drop-in fix** (a timeout arg, a backoff snippet, an
  idempotency guard, a concurrency limit, a fallback branch, or a config change).
- **Positives** (existing resilience: redelivery, locks, idempotency guards, scaling caps).
- **Prioritized improvement recommendations.**

## Constraints & style (hard rules)

- Be concrete — cite the exact unbounded call / missing-cap / config key. "Add retries
  somewhere" is not acceptable.
- Prefer minimal, drop-in snippets/config over prose; match current identifiers and the
  actual platform (cite the real deploy config, not a hypothetical one).
- Recommend the simplest mechanism that fits — don't prescribe a full circuit-breaker library
  where a bounded timeout + a cap suffices.
- Couple retry advice with idempotency: never recommend retries on a non-idempotent action
  without a guard.
- Do **not** invent files, functions, or config. If infra/runtime config isn't visible, mark
  **Unable to verify** and state which file/setting would prove it.
- Audit only — write the report; apply changes only when the user says to proceed.
- Create `audits/` if absent.
