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

- **zizmor scan** — a GitHub Actions security gate, enforced via a "Require
  workflows to pass" ruleset (the merge gate is the scan job's exit status).
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

- Commit as the repo owner (Mark Matyas) or other human directing an agent to author contributions. Use a `Signed-off-by:` trailer
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
- The ruleset injects the workflow **only** on `pull_request` /
  `pull_request_target` / `merge_group`. It does **not** run on `push`. Therefore
  `zizmor-scan.yml` lists ONLY those events — no `push`/`workflow_dispatch`, which
  would be no-ops in target repos. Push-time scanning is a SEPARATE surface handled
  by the reusable orchestrator (see "Two enforcement surfaces").
- "Require workflows to pass" (in **Active** mode) **blocks direct pushes** to the
  protected branch (observed: `GH013: Required workflow '...' is not satisfied`),
  forcing every change through a scanned PR. In **Evaluate** mode the workflow
  still runs (annotations posted) but pushes are NOT blocked — use Evaluate during
  rollout so teams aren't impacted.

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

- zizmor severities: `info < low < medium < high` (no "critical").
- The merge gate blocks on findings **≥ `ZIZMOR_FAIL_SEVERITY`** (env in the
  workflow, default `high`). The policy remaps footgun audits to `high`, so at the
  default the gate blocks exactly on those.
- Blocking rules (remapped to `high`): `dangerous-triggers`, `template-injection`,
  `github-env`.
- `unpinned-uses`: advisory in phase 1 (remapped to low + policy `*: ref-pin`).
  A later phase switches policies to hash-pin and removes the remap so it blocks.
- `persona: regular` (auditor/pedantic are too noisy for a fleet gate).
- Pins: `zizmor-action` v0.5.6; `actions/checkout` v6.0.2.

## Two enforcement surfaces (PR gate + push scan)

The requirements split into two problems that need two different mechanisms:

| Surface | Requirement | Mechanism | Lives in |
| --- | --- | --- | --- |
| **PR** | Block PRs that introduce high-severity issues / abuse the escape hatch | Ruleset "Require workflows to pass" → gate on **job exit status** | `zizmor-scan.yml` (this repo) |
| **Push** | Scan default-branch pushes and create **reviewable code-scanning alerts** for security managers, WITHOUT blocking the push | zizmor job in the shared **reusable orchestrator**, run `on: push`, **upload-only** (never fails) | `qualcomm/qcom-reusable-workflows` |

Why two: a ruleset can only inject a workflow on PR events (never push), and the
PR gate must *block* while the push scan must *not* block. A caller file for the
reusable workflow physically exists in each repo, so its `on: push` fires
normally — that is the only central way to run on push short of the GitHub App.

Push-surface design (in `qcom-reusable-workflows`, planned):

- Add a zizmor job to `reusable-qcom-preflight-checks-orchestrator.yml`. Caller
  repos already trigger it `on: push` to the default branch with
  `security-events: write`, and adopt updates via a **floating major tag** rewritten
  on minor releases — so this reaches the ~100+ callers without per-repo edits.
- On `push` the job runs **upload-only** (SARIF → code scanning, exit 0), so it
  creates dismissible alerts for security-manager review and NEVER fails the push.
- Enable/disable is an **admin decision, not a caller toggle**: gate the job on an
  enterprise-level custom property **`run-zizmor-on-push`** (default `true`, only
  admins can set `false` per repo). Do NOT expose it as an optional `enable-*`
  workflow input that any repo dev could flip off.
- Coverage boundary: this surface only reaches repos that CALL the reusable
  workflow. Repos that don't get PR-gate coverage only (no push scan) until the
  **GitHub App** long-term replacement lands (server-side scan on push webhooks
  with its own credentials — covers fork PRs and non-adopting repos regardless of
  local workflow files).

## PR gate: ONE ruleset rule, gate on job status

Enforce with a SINGLE ruleset rule: **"Require workflows to pass before merging"**,
source repo `qualcomm/qcom-enterprise-workflows`, workflow
`.github/workflows/zizmor-scan.yml`. (Verified: the ruleset triggers the workflow
with only this rule enabled.) The workflow has two steps:

- **`Scan and enforce (gate)`** — the gate; always runs. `annotations:true`,
  `advanced-security:false`, `min-severity:<fail-severity>`. Preserves zizmor's
  severity exit codes, so the job fails when the highest finding is ≥
  `ZIZMOR_FAIL_SEVERITY` (default `high`). Identical on fork PRs, no-GHAS repos,
  and normal PRs — needs no analysis, GHAS license, or write token.
- **`Upload results to code scanning (best-effort)`** — GHAS repos only (fork PRs
  INCLUDED). `advanced-security:true` (SARIF, exits 0) + `continue-on-error:true`,
  so it is purely COSMETIC (populates the Security tab, never affects the gate).
  Skipped, not failed, on no-GHAS repos.

**Why NOT "Require code scanning results".** That rule can only require a tool that
has **already produced an analysis** for the repo — and nothing central produces
one (a ruleset injects only on PR events, never `on: push`). A repo not yet reached
by the push surface has no analysis, so the rule **fails closed** and blocks every
PR (*"Waiting for Code Scanning results…"*). Job-status gating has no such
dependency. This mirrors **Grafana's** at-scale rollout. Note: this is NOT a
fork-token problem — fork PRs CAN upload SARIF (GitHub's endpoint accepts the
read-only fork token on `pull_request` runs, verified empirically). The blocker is
analysis provenance, which only the push surface / GitHub App resolves.

## Exceptions / governance direction

- The **only** escape hatch is an inline `# zizmor: ignore[rule]` comment, which
  is reviewable in the PR diff. Code-scanning alert dismissals still *exist* (and
  can be governed via delegated-dismissal approval), but they are **not in the
  merge path**: the gate is the zizmor job's exit status, so dismissing an alert
  does nothing to clear a failing check. Verified empirically — with both "require
  workflows to pass" and "require code scanning results" enabled, dismissing +
  approving the alert still left the PR unmergeable because the zizmor job was red.
  This sidesteps the dismissal-oversight problem for the merge decision.
- A later phase adds tooling to govern ignores of protected rules so they remain
  reviewable. (Details tracked outside this public repo.)

## Open follow-ups

- [ ] **PR gate**: create the org ruleset in **Evaluate** mode first; flip to Active
      once teams have adjusted.
- [ ] **Push surface**: add a zizmor (upload-only) job to
      `qcom-reusable-workflows` orchestrator, gated on the enterprise custom
      property `run-zizmor-on-push` (default true, admin-only to disable); ship via
      the floating major tag.
- [ ] Define the enterprise custom property `run-zizmor-on-push` (default `true`,
      only admins can set `false` per repo).
- [ ] Confirm consuming repos can read this repo's policy via `GITHUB_TOKEN`.
- [ ] Later phase: hash-pin `unpinned-uses` (remove remap → restore blocking).
- [ ] Later phase: tooling to govern protected-rule inline ignores.
- [ ] Long-term: GitHub App + backend — replaces the push surface, covers fork PRs
      and non-adopting repos, governs dismissals; then "require code scanning
      results" becomes a viable gate.
