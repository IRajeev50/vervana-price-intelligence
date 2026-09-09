# M0 — Foundations · DONE

- **Status:** COMPLETE (pending CI-green confirmation on first push — see caveats).
- **Date:** 2026-09-10
- **ADR:** 0001 approved by founder 2026-09-10. Gate 1 (YouTube legal) still closed —
  no data-collection code exists in M0, so it was not a blocker.

## Definition of done vs actual

| Criterion (from plan) | Result |
|---|---|
| `make test` green from a clean clone, one command | ✅ Verified — copied the tree without `.venv`/`.git` into a temp dir; `make setup && make test` → **22 passed**. |
| Lint + format clean | ✅ `make lint` → "All checks passed!"; `ruff format --check` → all 22 files formatted. |
| Structured logging works | ✅ `vervana healthcheck` emits one JSON line and confirms `timezone=Asia/Kolkata`. |
| Config from env, secrets never defaulted | ✅ `test_config.py`: secrets absent → `None`; env overrides work. `.env` git-ignored; `.env.example` ships an empty secret. |
| RISK-register generator exists + deterministic + not hand-edited | ✅ `make risks` → 13 risks, **0 code tags** (correct for M0). Regen is byte-identical. Generator excludes its own docstring; scans `src`+`scripts` only (not test fixtures). |
| Docker Compose for local dev | ⚠️ **Written and YAML-valid, but not run** — Docker is not installed on this build machine. Needs a one-time `make up` on a Docker-capable host to confirm. |
| CI green | ⚠️ **Workflow written and YAML-valid; not yet executed** — requires the first push to GitHub. It runs the exact commands proven locally (sync, ruff, pytest, risk-register drift check). |
| Python 3.12 despite system 3.14 | ✅ uv installed and pinned CPython **3.12.14**; tests run on it. |

## Real output (captured this session)

```
$ make test
uv run pytest
......................                                                   [100%]
22 passed in 0.17s

$ make lint
All checks passed!

$ make risks
Wrote docs/RISK_REGISTER.md: 13 risks, 0 code tags.

$ uv run vervana healthcheck
{"environment": "development", "timezone": "Asia/Kolkata", "version": "0.0.1",
 "event": "healthcheck", "level": "info", "timestamp": "2026-09-09T23:38:23.929135Z"}
ok

# clean-clone (temp dir, no .venv):
$ make setup && make test
...
22 passed in 1.24s
```

## What was built

- `src/vervana/`: `config.py` (pydantic-settings, secrets Optional), `logging.py`
  (structlog JSON), `time.py` (UTC/IST, naive rejected), `money.py` (integer paise,
  floats rejected), `cli.py` (Typer: `version`, `healthcheck`).
- `tests/`: 22 tests across config, time, money, smoke, and the risk generator — all
  offline.
- `scripts/gen_risk_register.py` + `scripts/risks_seed.yaml`: generates
  `docs/RISK_REGISTER.md` from seed definitions + live code-tag grep.
- Tooling: `pyproject.toml` (uv), `Makefile`, `.pre-commit-config.yaml`, `Dockerfile`,
  `docker-compose.yml`, `.github/workflows/ci.yml`, `.env.example`.
- Docs: README + `RISK_REGISTER`, `RUNNING_COSTS`, `OPEN_QUESTIONS`, `DATA_DICTIONARY`
  (skeleton), `RUNBOOK` (skeleton).

## Deviations from plan

- **Scan scope narrowed** from `src/scripts/tests` to `src/scripts`. Reason discovered
  during testing: test files contain tag-shaped string literals as fixtures, which the
  scanner counted as real tags and polluted the register. RISK tags mark load-bearing
  assumptions in *application* code, not tests — so tests are excluded. (Two bugs the
  test suite caught and I fixed: this, and the generator matching its own docstring.)
- **Two "done" criteria are environment-limited here** (Docker not installed; CI needs a
  GitHub push). Both artifacts are written and YAML-validated; neither could be *executed*
  on this machine, and per the no-fabrication rule I am not claiming they ran. First
  Docker host / first push confirms them.

## Cost impact

₹0 fixed (local dev + free GitHub Actions). First fixed cost (VPS) appears at deploy.
`RUNNING_COSTS.md` updated to reflect M0 = ₹0.

## Next

M1 — data model + entity registry. I'll write `docs/milestones/M1-plan.md` and stop for
review before building, per the milestone flow.
