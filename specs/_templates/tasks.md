# F00 — tasks

Each task takes 45–90 minutes, writes its tests first, and ends green with one commit. `/sdd-build F00` runs the next unchecked task. Every requirement ID appears in at least one task line.

- [ ] **T01 — <title>** · F00-R1 · ~60 min
    - Tests first: `tests/...::test_...`
    - Change: `app/...`
    - Done when: <those tests pass and `make lint` is clean>
- [ ] **T02 — Config, docs and manual-check prep** · F00-R2 · ~45 min
    - Change: `.env.example`, `render.yaml`, `docs/PRODUCTION.md`, `CHANGELOG.md`
    - Done when: <the preview environment is deployed with the new settings, ready for /sdd-verify>
