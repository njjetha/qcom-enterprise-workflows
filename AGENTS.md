# AGENTS.md — Qualcomm enterprise GitHub Actions central workflows

Source-of-truth context for AI agents and maintainers working in this repository.
Keep this file current; it is the canonical record of decisions and constraints.

> This repository is **public**. Do not add internal-only operational detail,
> security-bypass specifics, or unreleased rollout timelines here. Keep this file
> high-level and consumer-safe. Maintainer-only detail lives outside the repo.

## Goal

Central home for GitHub Actions workflows that are distributed across the Qualcomm
GitHub enterprise as **required workflows** (no per-repo file) and enforced via
enterprise **rulesets**. Two use cases currently live here:

- **zizmor scan** — a GitHub Actions security gate, enforced via a Code Scanning
  merge-protection ruleset.
- **qcom-preflight-checks-for-pkg** — preflight checks for `pkg-*` repos.

## Repository layout

- `.github/workflows/zizmor-scan.yml` — zizmor security scan (required workflow)
- `.github/workflows/qcom-preflight-checks-for-pkg.yml` — preflight checks (required workflow)
- `.github/zizmor-enterprise-policy.yml` — central zizmor policy (single source of truth)
- `.github/zizmor.md` — maintainer + consumer docs for the zizmor gate

Note: the zizmor policy file lives OUTSIDE `.github/workflows/` on purpose —
GitHub treats every file under `workflows/` as a workflow, and the policy is a
zizmor config, not a workflow.

## Actions are disabled on this repo

GitHub Actions is disabled in this repository's settings so the central workflows
do not self-trigger here. These files are consumed by OTHER repos via enterprise
rulesets; they are not meant to run against this repo.

## Commit conventions

- Commit as the repo owner (Mark Matyas). Use a `Signed-off-by:` trailer
  (`git commit --signoff`).
- Credit AI assistance with an `Assisted-by: <tool>:<model>` trailer, matching
  existing history.
- Do **not** add a `Co-Authored-By: Claude` trailer.

## Workflow directory / ruleset constraints

- "Require workflows to pass" rulesets support events **`pull_request`,
  `pull_request_target`, `merge_group` ONLY**; event filters (branches/paths/types)
  are ignored. Add `merge_group` if target repos use a merge queue.
- Required workflows MUST NOT use `concurrency.cancel-in-progress: true` — a
  cancelled run can leave the required check unreported and block merge.
  `zizmor-scan.yml` uses `cancel-in-progress: false`.
- Renaming a workflow file changes the path the enterprise ruleset references —
  coordinate renames with the ruleset owner.
- `push:` / `workflow_dispatch:` blocks only matter inside a consuming repo's own
  context; they are not ruleset events.

### `merge_group` event

Merge queues check a queued PR against a temporary combined commit via the
`merge_group` event — separate from `pull_request`/`push`. Without `on: merge_group`,
the required check is never reported for the merge group and the merge stalls.
No-op for repos without a queue. `merge_group` is included in `zizmor-scan.yml`.

## Trust model & config (zizmor gate)

- Central config is fetched via a **separate pinned-SHA checkout** and passed with
  `config:` (zizmor global discovery) so any repo-local `zizmor.yml` is IGNORED.
  **Fail closed** if the config is missing.
- The required workflow runs in the **consuming repo** context, so a second
  checkout of this central repo is always needed to obtain the policy.
- `ZIZMOR_CONFIG_REPO = qualcomm/qcom-enterprise-workflows` (this repo is the
  canonical policy source).
- `ZIZMOR_CONFIG_REF` is pinned to an immutable commit SHA of this repo; bump it
  via PR whenever the policy changes.
- Consuming repos' `GITHUB_TOKEN` must be able to read this repo (public, so reads
  succeed).
- The policy lists **only deviations** from zizmor defaults.

## Policy / severity

- zizmor severities: `info < low < medium < high` (no "critical"). `high` = blocking.
- Blocking rules: `dangerous-triggers`, `template-injection`, `github-env`.
- `unpinned-uses`: advisory in phase 1 (remapped to low + policy `*: ref-pin`).
  A later phase switches policies to hash-pin and removes the remap so it blocks.
- `persona: regular` (auditor/pedantic are too noisy for a fleet gate).
- Pins: `zizmor-action` v0.5.6; `actions/checkout` v6.0.2.

## Graceful degradation

`zizmor-scan.yml` degrades when SARIF upload to code scanning isn't possible
(e.g. code scanning not available, or a context with a read-only token). In that
case it runs in advisory annotations mode and writes a job summary instead of
uploading SARIF. Advisory runs surface findings for visibility but do not arm the
merge gate; see `.github/zizmor.md`.

## Code-scanning tool bootstrap

The "Require code scanning results" ruleset can only require a tool that has
already produced an analysis for the repo. Ensure the scan runs (and uploads an
analysis) before/while enabling enforcement, and use the ruleset's "Do not require
on creation" option so a repo's first PR can seed the initial analysis.

## Exceptions / governance direction

- Inline `# zizmor: ignore[rule]` comments are the intentional escape hatch.
- A later phase adds tooling to govern ignores of protected rules so they remain
  reviewable. (Details tracked outside this public repo.)
- Dismissals are gated to **Security Managers**.

## Open follow-ups

- [ ] Confirm consuming repos can read this repo's policy via `GITHUB_TOKEN`.
- [ ] Later phase: hash-pin `unpinned-uses` (remove remap → restore blocking).
- [ ] Later phase: tooling to govern protected-rule inline ignores.
