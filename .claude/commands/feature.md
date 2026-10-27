---
description: Disciplined pipeline to build a feature — orient, plan+approve, branch, implement, verify, commit.
argument-hint: <what to build>
---

Build the feature described in: $ARGUMENTS

Follow this pipeline in order. Do not skip the approval gate.

## 1. Orient
- Read `CLAUDE.md` for layout, commands, and conventions.
- Read `docs/` for the affected feature and `docs/decisions.md` for discovery answers. Grep to confirm before assuming.
- Identify which layer the change belongs in (api → services → providers/db; frontend → web/src/lib/api.ts + pages).

## 2. Plan + approve (gate)
- Enter plan mode (EnterPlanMode).
- Produce a concrete plan: files to add/change, provider/registry impact, new endpoints + their client methods, tests to add, docs to update.
- Present it via ExitPlanMode and WAIT for explicit approval. Do not write code before approval.

## 3. Branch
- If on `main`, create a feature branch first (`git checkout -b feat/<slug>`). Never commit feature work directly to `main`.

## 4. Implement
- Keep routers thin; put logic in `app/services/`. Swap externals via provider registries, not inline.
- Backend config through `app/config.py` settings — no scattered `os.getenv`.
- Frontend: add API calls to `web/src/lib/api.ts`, not ad-hoc fetches in pages.
- Match surrounding style. Update the relevant `docs/<feature>/README.md`.

## 5. Verify
- Backend: `pytest` (add tests for new logic). Run the specific test file while iterating.
- Frontend (if touched): `cd web && npm run build` and `npm run lint`.
- Exercise the actual path (uvicorn / dev server) when there's runtime behavior to observe — don't rely on tests alone.
- Report results honestly: if something fails or was skipped, say so.

## 6. Commit (only when asked)
- Do NOT commit or push unless the user explicitly requests it.
- When asked: conventional-commit subject (e.g. `feat(trades): ...`), body only when the "why" isn't obvious.
