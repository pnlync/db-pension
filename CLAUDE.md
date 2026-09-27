# CLAUDE.md

DB pension scheme model (portfolio project). **SPEC.md is the build specification — read it in full before any work, and follow §1 (how we work).**

## Key rules (from SPEC, repeated because they are the ones most often broken)
- One module at a time in SPEC §9 order (M0, M1, ...). Do not start the next module until the owner says "next".
- Before coding a module, explain it in Chinese (question, inputs, outputs, key formulas, common mistakes) and wait for the owner's OK.
- Write the module's acceptance tests first; report each as PASS/FAIL with numbers. Commit once per module: `M<n>: <module name>`.
- No statutory or market number in code: they live in `config/*.yaml` with source, paragraph and date, plus a row in `data/assumptions_register.csv`.
- The three assumption sets never read each other: `funding_standard.py` must not import IAS 19 assumptions, and vice versa (SPEC §8).
- Every public number comes from a file in `outputs/` written by the pipeline; nothing hand-typed in README, memo or CV (SPEC §11).
- Never call the buy-in price a third liability.
- If SPEC is ambiguous or looks wrong: stop and ask. Don't guess.

## Owner context
- The owner is learning pensions actuarial work through this project and must be able to explain every line in interviews. Prefer readable, explicit numpy over clever code.
- `private_notes/` holds the owner's planning guides. It is gitignored — never commit, quote into public files, or publish it.
- Sister project: `../assurance` (life protection model, package `lifemodel`); its Solvency II engine is reused for the buy-in RM (SPEC §8.2) and its EIOPA curves for the buy-in BEL.

## Environment
- Python 3.12 via uv (`uv sync`, `uv run pytest`). (uv's 3.11 build is killed by macOS on this machine.)
- GitHub: git@github.com:pnlync/db-pension.git (SPEC §10 calls the repo `db-pension-model`; the package is `pension`).
- Raw data is downloaded manually by the owner into `data/market/raw/` (see its README) and is not committed. Do not download it yourself; give the owner the list.

## Decision authority
The owner has given the agent full discretion over the whole project (27 Sep 2026). Make the call, record it in SPEC.md (bump the version line) or the module notes, and tell the owner what was decided and why.
