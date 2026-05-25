# Shift-left checks (added by /development:bootstrap)

This repository enforces a Zero Tolerance Quality Gate on new code. To keep the
loop tight and avoid CI ping-pong, run the same checks **locally during
implementation** before declaring a task complete.

## After editing code

1. Lint the Python files you touched:
   - `ruff check <path>`
   - `ruff format --check <path>`
2. Run any tests that exercise the changed code.
3. If the file is in a security-sensitive area (auth, request handling, file
   I/O, deserialization), run `semgrep --config=auto` on it.

## Before declaring a task done

1. `pre-commit run --all-files` — must pass.
2. The full test suite must pass with coverage ≥ 90% on the new code:
   `pytest --cov --cov-report=term`
3. Surface any Sonar / Snyk / Trivy findings as part of your response — don't
   wait for CI to surface them.
4. If you introduced any code smell, bug, vulnerability, or security hotspot —
   fix it before declaring done. The Quality Gate is 0 tolerance; CI will block
   the PR anyway.

## What CI runs (so you don't surprise yourself)

- SonarCloud with the Zero Tolerance Quality Gate (90% coverage + 0 smells/bugs/vulns + all A ratings).
- Snyk Code (SAST), Snyk Open Source (deps), Snyk Container (image).
- Trivy license scan (filesystem + image).
- pytest + coverage upload to SonarCloud.
- Semgrep, CodeQL, OpenSSF Scorecard.
- Secret scanning (gitleaks) + pre-commit backstop.
