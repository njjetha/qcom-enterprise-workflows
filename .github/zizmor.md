# zizmor security gate

This document explains the enterprise GitHub Actions security scan powered by
[zizmor](https://github.com/zizmorcore/zizmor) and how it affects pull requests.

`zizmor` statically analyzes GitHub Actions workflows for common security issues
(dangerous triggers, template injection, credential/permission mistakes, unpinned
actions, and more). It runs centrally as a **required workflow** and is enforced
as a merge gate — there is no file to add to your repository. The gate is the
scan **check status**: if zizmor finds a high-severity issue in your workflows,
the check fails and the PR cannot merge until you fix it (or add a reviewed
inline ignore). See *For maintainers* for the ruleset details.

## What you'll see on a pull request

- A **GitHub Actions Security Scan (zizmor)** check appears on PRs automatically.
- If there are **high-severity** findings, the check **fails** and blocks the
  merge. Lower-severity findings are advisory (surfaced, non-blocking).
- Findings always appear as **inline annotations** on the check (GitHub shows at
  most 10 per step; the step log has the full list). On repos with GitHub Advanced
  Security, all findings (all severities) are *also* uploaded to the **Security →
  Code scanning** tab; repos without it get annotations only. The run's job summary
  explains what happened for that run.
- This all works the same on **pull requests from forks**, Security-tab upload
  included: GitHub's code-scanning endpoint accepts SARIF from a fork PR's
  read-only token on `pull_request` runs, so no write token is required.

## Fixing a finding

1. Open the failing **GitHub Actions Security Scan (zizmor)** check and read the
   annotation (rule description + flagged location). On repos with code scanning,
   you can also open the alert in the Security tab.
2. Apply the recommended remediation to your workflow (for example, scope
   `permissions:`, avoid interpolating untrusted input into `run:` blocks, or pin
   an action).
3. Push the fix — the scan re-runs and the check goes green when resolved.

zizmor's rule documentation has remediation guidance for every audit:
<https://docs.zizmor.sh/audits/>.

## Currently blocking rules

The following are treated as **blocking** (high severity):

- `dangerous-triggers` — e.g. `pull_request_target` / `workflow_run` used unsafely.
- `template-injection` — untrusted `${{ ... }}` expansion in `run:` and similar.
- `github-env` — unsafe writes to `GITHUB_ENV` / `GITHUB_PATH`.

`unpinned-uses` (action pinning) is currently **advisory** and will become
blocking in a later phase once migration tooling and communications are in place.
All other zizmor audits run at their default severity.

## Exceptions

If a finding is a verified false positive or an accepted risk, the supported
escape hatch is an inline comment on the offending line:

```yaml
- uses: some/action@v1 # zizmor: ignore[rule-name]
```

Because the merge gate is the **check status** (not code-scanning alerts), an
inline ignore is the only way to clear a blocking finding, and it lands in the PR
diff where a reviewer sees it. Use these sparingly and with justification — ignores
of protected rules are reviewed.

## Policy configuration

The single source of truth for the policy is
[`.github/zizmor-enterprise-policy.yml`](zizmor-enterprise-policy.yml) in this
repository. It lists only the **deviations** from zizmor's built-in defaults. The
scan workflow fetches this config from a pinned commit and passes it to zizmor
explicitly, so a repository-local `zizmor.yml` cannot weaken the policy.

## For maintainers

### Ruleset setup — ONE rule, gate on job status

Enforce with a **single** ruleset rule: **"Require workflows to pass before
merging"**, source repo `qualcomm/qcom-enterprise-workflows`, workflow
`.github/workflows/zizmor-scan.yml`. The merge gate is the scan **job's exit
status** — the `Scan and enforce (gate)` step fails the job when zizmor finds an
issue at or above `ZIZMOR_FAIL_SEVERITY` (default `high`).

**Do NOT use "Require code scanning results" as the fleet gate.** That rule can
only require a tool that has *already produced an analysis* for the repo — and
nothing in the central ruleset produces one, because a "require workflows to pass"
ruleset can only inject a workflow on PR events, never `on: push`. So a repo with
no local zizmor workflow (and not yet reached by the push-scan surface) has no
analysis, and the rule **fails closed** — blocking every PR with *"Waiting for
Code Scanning results — Code Scanning may not be configured for the target
branch."* Gating on **job status** avoids this entirely: the scan runs on the PR
and reports pass/fail directly, needing no pre-existing analysis, no GHAS license,
and no write token. This mirrors Grafana's at-scale zizmor rollout, which also
gates on the job exit code.

Notes:

- Prefer an **org-level** ruleset (Settings → Repository → Rulesets) targeting the
  default branch, scoped to repos via a custom property. An enterprise-level rule
  works too; the choice does not affect how the gate behaves.
- In **Active** mode this rule **blocks direct pushes** to the protected branch
  (`GH013: Required workflow '...' is not satisfied`), forcing all changes through
  a scanned PR. Only apply it to branches where every change already goes via PR.
- **Roll out in Evaluate mode.** For this rule, Evaluate mode STILL runs the
  workflow (PR annotations + job summary are posted, developers see findings) but
  blocks nothing — neither merges nor direct pushes. Use it during rollout so the
  push block doesn't impact teams, then flip to **Active** to start blocking.
- This ruleset does not run on `push`. Push-time scanning is a separate surface
  (the reusable orchestrator; see below), not this rule.
- The workflow's visibility must match the targets. This repo is **public**, so its
  workflow runs on any repo (public/internal/private) in the org.
- Private/internal targets should enable **GitHub Advanced Security** so the
  best-effort SARIF upload can populate the Security tab (including on fork PRs).
  It is not required for enforcement — the gate is the job status, which does not
  depend on GHAS.
- **Severity lever:** onboard a fleet with `ZIZMOR_FAIL_SEVERITY: never` (advisory:
  scan + annotate, never block), then ratchet `high → medium → low`.

### Push-time scanning (separate surface)

The ruleset only covers pull requests. To scan **pushes to the default branch**
and create reviewable code-scanning alerts for security managers WITHOUT blocking
the push, add a zizmor job to the shared reusable orchestrator
(`qualcomm/qcom-reusable-workflows`), which caller repos already trigger `on: push`
with `security-events: write` and adopt via a floating major tag:

- On `push`, the job runs **upload-only** (SARIF → code scanning, exit 0): it
  creates dismissible alerts and never fails the push.
- Enable/disable is an **admin decision**, gated on the enterprise custom property
  **`run-zizmor-on-push`** (default `true`; only admins can set `false` per repo) —
  not an optional workflow input that any repo dev could turn off.
- This surface only reaches repos that call the reusable workflow. Repos that don't
  get PR-gate coverage only until the GitHub App lands.
- Long term this surface is replaced by the GitHub App (server-side scan on push
  webhooks, covering fork PRs and repos that don't call the reusable workflow).

### Policy pinning

- The policy is fetched by [`.github/workflows/zizmor-scan.yml`](workflows/zizmor-scan.yml)
  from this repo at an **immutable commit SHA** (`ZIZMOR_CONFIG_REF`). Never point
  it at a branch or tag.
- To change the policy: edit `.github/zizmor-enterprise-policy.yml`, merge the
  change, then bump `ZIZMOR_CONFIG_REF` to the new commit SHA via PR.
- Pinned versions: `zizmor-action` and `actions/checkout` are pinned by SHA in the
  scan workflow; bump them deliberately.
