# Setup — manual steps after `/development:bootstrap`

The bootstrap skill wrote the config files and workflows. Some setup steps
require human action — account creation, token storage, runner registration —
and are listed below.

---

## 1. Install local toolchain

```sh
# pre-commit framework
pip install pre-commit
# or
brew install pre-commit

pre-commit install
pre-commit run --all-files   # initial run, may take a minute
```

Python tooling:

```sh
pip install ruff pytest pytest-cov coverage
# or, with the project's dev extras (after `pytest-cov` is added):
pip install -e ".[dev]"
```

Cross-language:

```sh
brew install gitleaks
brew install semgrep         # or: pip install semgrep
```

---

## 2. SonarCloud setup

### 2.1 Create the project

1. Sign in to [sonarcloud.io](https://sonarcloud.io) with your GitHub account.
2. Click **Analyze new project** → select this repository.
3. Choose **With GitHub Actions** as the analysis method.
4. Copy the `SONAR_TOKEN` shown — you'll only see it once.

### 2.2 Add secrets to GitHub

In repo Settings → Secrets and variables → Actions → New repository secret:

| Name | Required? | Value |
|---|---|---|
| `SONAR_TOKEN` | Yes | from step 2.1 |
| `SNYK_TOKEN` | Yes | from step 2.5 below |
| `SEMGREP_APP_TOKEN` | **Optional** | only needed if you connect Semgrep AppSec Platform for managed rules / dashboards. CI runs the free OSS ruleset without it. |

### 2.3 Create the Zero Tolerance Quality Gate

```sh
# Set these once for the snippet below:
export SONAR_TOKEN=<the token from 2.1>
export SONAR_HOST=https://sonarcloud.io
export ORG_KEY=timo-jakob
export PROJECT_KEY=timo-jakob_ai-doc-organizer

# Create the gate
GATE_ID=$(curl -sS -u "$SONAR_TOKEN:" -X POST \
  "$SONAR_HOST/api/qualitygates/create?name=Zero%20Tolerance&organization=$ORG_KEY" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# Helper to add a condition
add() {
  curl -sS -u "$SONAR_TOKEN:" -X POST \
    "$SONAR_HOST/api/qualitygates/create_condition" \
    --data-urlencode "gateId=$GATE_ID" \
    --data-urlencode "organization=$ORG_KEY" \
    --data-urlencode "metric=$1" \
    --data-urlencode "op=$2" \
    --data-urlencode "error=$3" > /dev/null
  echo "  + $1 $2 $3"
}

add new_coverage              LT  90
add new_code_smells           GT  0
add new_bugs                  GT  0
add new_vulnerabilities       GT  0
add new_security_hotspots_reviewed LT 100
add new_reliability_rating    GT  1   # 1 = A
add new_security_rating       GT  1
add new_maintainability_rating GT 1
add new_security_review_rating GT  1
add new_duplicated_lines_density GT 3

# Assign the gate to this project
curl -sS -u "$SONAR_TOKEN:" -X POST \
  "$SONAR_HOST/api/qualitygates/select" \
  --data-urlencode "gateName=Zero Tolerance" \
  --data-urlencode "projectKey=$PROJECT_KEY" \
  --data-urlencode "organization=$ORG_KEY"
```

Verify in the SonarCloud UI: **Quality Gates** → "Zero Tolerance" → it should
show the 10 conditions above. The project should now show this gate.

### 2.4 OpenSSF Scorecard — supply-chain health badge

The generated `.github/workflows/scorecard.yml` runs weekly and publishes
a score to <https://scorecard.dev/viewer/?uri=github.com/timo-jakob/ai-doc-organizer>.
Nothing to set up — the workflow uses GitHub's OIDC token to publish, no
secrets needed.

**Add the badge to your README** (optional but recommended):

```markdown
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/timo-jakob/ai-doc-organizer/badge)](https://scorecard.dev/viewer/?uri=github.com/timo-jakob/ai-doc-organizer)
```

### 2.5 Sign up for Snyk

1. Go to [snyk.io](https://snyk.io), sign in with GitHub.
2. Account Settings → Auth Token → copy.
3. Add as repo secret `SNYK_TOKEN` (already listed in 2.2 above).
4. (Optional) Import the repo in Snyk's UI to enable PR comments.

---

## 3. License compliance policy

The `license-fs` and `license-image` (inside the `image` job) jobs run
Trivy in license-only mode and gate merges on `CRITICAL,HIGH` severity.
Trivy classifies licenses into categories:

| Category | Examples | Default severity | Default CI behaviour |
|---|---|---|---|
| Forbidden | AGPL-1.0/3.0, SSPL-1.0 | **HIGH** | **Blocks merge** |
| Restricted | GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0 | MEDIUM | Reported, does not block |
| Reciprocal | MPL-2.0, EPL-2.0 | LOW | Reported, does not block |
| Notice / Permissive | Apache-2.0, MIT, BSD, ISC | LOW | Reported, does not block |

You've chosen **MIT** for this project. MIT is compatible with all permissive
licenses (Apache-2.0, BSD, ISC) and reciprocal/restricted licenses (MPL, LGPL,
GPL) at the dep level. If you ever consider relicensing, customize
`trivy.yaml` to gate stricter rules — there's a commented `license:` block.

---

## 4. Weekly drift scan

The quality workflow runs on a weekly schedule (Monday 06:00 UTC) in
addition to PR + push triggers. Vulnerability and license databases
update continuously; the weekly schedule means newly-disclosed CVEs
surface within ~7 days, even when no PR touches the affected area.

## 5. Dependabot — what's tracked

`.github/dependabot.yml` opens weekly grouped PRs for:

| Ecosystem | What it tracks |
|---|---|
| `github-actions` | Actions versions in `.github/workflows/*.yml` |
| `pip` | `requirements.txt` / `pyproject.toml` |
| `docker` | `FROM` lines in your Dockerfile(s) |

Minor and patch updates are grouped into a single PR per ecosystem.
Major version updates always open as separate PRs.

## 6. Security disclosure — enable Private Vulnerability Reporting

`.github/SECURITY.md` directs reporters to **GitHub Security Advisories
(GHSA)**. Confirm it's enabled:

1. Repo Settings → **Code security and analysis**.
2. Find **Private vulnerability reporting** → click **Enable**.

## 7. Push protection — block secrets at the server

GitHub's **secret scanning + push protection** rejects any `git push`
containing a detected token at the server. **Free and on by default** for
public repos since 2024. Confirm: Settings → Code security and analysis →
"Push protection" should be on.

---

## 8. GitHub branch protection on `main`

The bootstrap skill offers to apply these automatically via `gh api`. If you
want to do it manually: repo Settings → Branches → Add rule for `main`:

- [x] Require a pull request before merging (1 approval, dismiss stale reviews)
- [x] Require status checks to pass before merging:
  - `sonarcloud`, `snyk-open-source`, `snyk-code`, `license-fs`, `image`, `semgrep`, `analyze` (CodeQL), `pre-commit`, `test-and-coverage`
- [x] Require branches to be up to date before merging
- [x] Require linear history
- [x] Do not allow bypassing the above settings
- [x] Block force pushes
- [x] Block deletions

---

## 9. Container image publishing

The workflow publishes your container image to **GitHub Container Registry**
(`ghcr.io/timo-jakob/ai-doc-organizer`).

| Trigger | Tags | Platforms |
|---|---|---|
| Push to `main` | `latest`, `sha-<7>`, `main` | `linux/amd64` + `linux/arm64` |
| Release `v1.2.3` | `1.2.3`, `1.2`, `1`, `latest` | `linux/amd64` + `linux/arm64` |
| PR | Built + scanned, not pushed | `linux/amd64` only |

The scan runs **before** the push. A vulnerable image never reaches the registry.

### SBOM + provenance + signature

Every published image carries:
- **CycloneDX JSON SBOM** (via Syft / BuildKit)
- **SLSA provenance** attestation
- **Sigstore cosign signature** (keyless OIDC)

**Inspect the SBOM:**
```sh
docker buildx imagetools inspect ghcr.io/timo-jakob/ai-doc-organizer:latest \
  --format '{{ json .SBOM }}' | jq .
```

**Verify the image signature:**
```sh
brew install cosign
cosign verify ghcr.io/timo-jakob/ai-doc-organizer:latest \
  --certificate-identity-regexp "^https://github.com/timo-jakob/ai-doc-organizer/" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

### Image visibility — one-time manual step

GHCR creates new container packages as **private** by default. After your
first publish:

- Go to: `https://github.com/users/timo-jakob/packages/container/ai-doc-organizer/settings`
- Scroll to "Danger Zone" → "Change visibility" → Public.

---

## 10. First run

1. Commit the bootstrap output (the `/development:bootstrap` skill offers this).
2. Push to a feature branch and open a PR.
3. Watch CI — all checks should run. The first run takes longer (SonarCloud
   needs to index the project; Snyk pulls dep graphs).
4. If anything fails, fix it locally — `pre-commit run --all-files` reproduces
   most of the checks.
