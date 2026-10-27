---
name: testing-review
description: >-
  Use when the user asks to evaluate the test suite — unit/integration/E2E
  coverage, uncovered critical paths, test quality (naming, Arrange-Act-Assert,
  independence, mock usage, test data), test-pyramid adherence, testing
  anti-patterns (testing implementation vs behavior, brittle tests, slow tests),
  and missing tests (error scenarios, edge cases, security, performance). Produces
  a findings report + a test-improvement plan, written to audits/.
allowed-tools: Read, Grep, Glob, Bash, Write
---

# Testing Implementation Review

Evaluate the test suite and write a report to `audits/testing-analysis.md`. Measure coverage
with the real tool where possible; cite exact test `file:line` / test names.

## Measure first

- run the suite + coverage if available:
  `pytest -q` / `pytest --cov=<pkg> --cov-report=term-missing` (or the project's runner)
- inventory tests: `grep -rn 'def test_\|it(\|describe(' tests/` and count per module
- map tests → source modules; find source files/functions with **no** corresponding test
- note test runtime (slow tests), and any integration/E2E vs unit split
- If coverage tooling can't run, mark the percentage **Unable to verify** and give the
  command that would produce it; still assess qualitatively.

## Analyze

- **Coverage** — unit %, integration presence, E2E presence, and the **uncovered critical
  paths** (the high-risk code with no test). Coverage % alone is weak — name the untested
  critical functions explicitly.
- **Test quality** — names describe behavior; clear Arrange-Act-Assert; tests are independent
  (no shared mutable state / order dependence); mocks used appropriately (mock at boundaries,
  not the unit under test); test data managed (fixtures, no magic blobs).
- **Test patterns** — test-pyramid shape (many unit > some integration > few E2E);
  anti-patterns: testing implementation details instead of behavior, **brittle tests**
  (assert on exact log strings / call internals / patch the wrong namespace), slow tests.
- **Missing tests** — error/failure scenarios, edge cases, concurrency/idempotency,
  security, performance.

## Output (write to `audits/`)

- **Header:** date, scope, tooling + measured coverage (or Unable to verify).
- **Coverage table:** module | has tests? | approx cover | untested critical paths.
- **Findings**, each with a stable id, exact test/source `file:line`, **Severity 1-10**
  (10 = fix now), and a **minimal drop-in test snippet** (the missing case, or the de-brittled
  rewrite).
- **Positives** — what the suite already does well.
- A **test-improvement plan**: ordered list of tests to add/fix with concrete examples,
  highest-risk-untested-path first.

## Constraints & style (hard rules)

- Be concrete — name the exact untested function and the exact brittle assertion; don't say
  "add more tests" in the abstract.
- Prefer minimal, drop-in test snippets over prose; match the project's test framework,
  fixtures, and patch conventions (e.g. patch where the symbol is *looked up*, not where it's
  defined — flag tests that get this wrong).
- Distinguish behavior tests (good) from implementation tests (brittle). A test that breaks on
  a pure refactor is a finding.
- Do **not** invent files, functions, or tests that exist. If coverage isn't measurable, mark
  **Unable to verify** and give the command.
- Audit only — write the report + plan; add tests only when the user says to proceed.
- Create `audits/` if absent.
