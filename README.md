# qcom-enterprise-workflows

Central home for GitHub Actions workflows that are distributed across the
Qualcomm GitHub enterprise as **required workflows** and enforced via enterprise
**rulesets**. These workflows run against *other* repositories in the enterprise;
there is nothing to copy into your own repository to adopt them.

> **GitHub Actions is disabled on this repository** so the central workflows do
> not self-trigger here. The files are consumed by other repos via enterprise
> rulesets — they are not meant to run against this repo.

## What's here

| Workflow | Purpose |
| --- | --- |
| [`.github/workflows/zizmor-scan.yml`](.github/workflows/zizmor-scan.yml) | GitHub Actions security scan ([zizmor](https://github.com/zizmorcore/zizmor)), enforced as a Code Scanning merge gate. See [`.github/zizmor.md`](.github/zizmor.md). |
| [`.github/workflows/qcom-preflight-checks-for-pkg.yml`](.github/workflows/qcom-preflight-checks-for-pkg.yml) | Preflight checks (license/copyright, dependency review, Semgrep, repolinter, commit email) for `pkg-*` repositories. |
| [`.github/workflows/semgrep-org-scan.yml`](.github/workflows/semgrep-org-scan.yml) | Centralized weekly [Semgrep](https://semgrep.dev) scan of every public repository across the organizations in [`.github/semgrep-scan-organizations.yml`](.github/semgrep-scan-organizations.yml); uploads SARIF into each repo's own Code scanning tab. |

Supporting files:

- [`.github/zizmor-enterprise-policy.yml`](.github/zizmor-enterprise-policy.yml) —
  the central zizmor policy (single source of truth). It lives outside
  `.github/workflows/` because GitHub treats every file under `workflows/` as a
  workflow, and this is a zizmor config, not a workflow.
- [`.github/zizmor.md`](.github/zizmor.md) — what the zizmor gate does, how to fix
  findings, and how exceptions work.
- [`.github/semgrep-scan-organizations.yml`](.github/semgrep-scan-organizations.yml) —
  the list of organizations covered by the centralized Semgrep scan. It lives
  outside `.github/workflows/` because it is configuration, not a workflow.
- [`.github/scripts/semgrep_org_scan.py`](.github/scripts/semgrep_org_scan.py) —
  the scan logic invoked by `semgrep-org-scan.yml` (repo discovery, Semgrep
  execution, SARIF upload).

## Centralized org-wide Semgrep scan

[`semgrep-org-scan.yml`](.github/workflows/semgrep-org-scan.yml) runs Semgrep
centrally, on a weekly schedule, across every eligible public repository in the
organizations listed in
[`.github/semgrep-scan-organizations.yml`](.github/semgrep-scan-organizations.yml).
Results are uploaded as SARIF into each scanned repository's own **Security →
Code scanning** tab.

- **Scope:** every public, non-archived, non-fork, non-empty repository in each
  configured org.
- **Parallelism:** a `prepare` job turns the org list into a matrix, and each org
  is scanned in its own parallel job (`fail-fast: false`), so one org failing
  does not block the others.
- **Auth:** cross-org access uses an enterprise GitHub App (same App ID / private
  key installed on each org, with `contents: read` and `security-events: write`).
  All GitHub API access goes through PyGithub.
- **Clean repos:** a valid SARIF is uploaded even when there are no findings, so
  previously-reported alerts that are now fixed are cleared.

To add or remove an org, edit
[`.github/semgrep-scan-organizations.yml`](.github/semgrep-scan-organizations.yml)
and ensure the GitHub App is installed on that org.

## For repositories subject to these checks

You don't need to add anything. The checks appear on your pull requests
automatically because they are enforced at the enterprise level. To understand a
specific result:

- **zizmor / security scan** — see [`.github/zizmor.md`](.github/zizmor.md).
- **preflight checks** — see the
  [qcom-reusable-workflows](https://github.com/qualcomm/qcom-reusable-workflows)
  repository, which provides the underlying reusable workflow.

## Branches

**main**: Primary development branch. Contributors should base submissions on this
branch and open pull requests against it.

## Maintaining these workflows

Changes here affect every repository in the enterprise that the corresponding
ruleset targets. Treat changes carefully:

- The zizmor policy is fetched by the scan workflow from a **pinned commit SHA**.
  After changing the policy, bump that pin via pull request. See the maintainer
  notes in [`.github/zizmor.md`](.github/zizmor.md).
- Renaming a workflow file changes the path the enterprise ruleset references —
  coordinate renames with the ruleset owner.
- See [AGENTS.md](AGENTS.md) for the design constraints and decisions behind these
  files.

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Getting in contact

- [Report an Issue on GitHub](../../issues)
- [Open a Discussion on GitHub](../../discussions)

## License

`qcom-enterprise-workflows` is licensed under the
[BSD-3-Clause License](https://spdx.org/licenses/BSD-3-Clause.html). See
[LICENSE.txt](LICENSE.txt) for the full license text.
