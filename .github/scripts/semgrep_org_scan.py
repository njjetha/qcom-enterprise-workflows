#!/usr/bin/env python3
"""Weekly org-wide Semgrep scan.

Scans each public repository in an org with Semgrep and uploads the SARIF into
that repo's own Code scanning tab.

Cross-repo access uses an enterprise GitHub App: per-org installation tokens
list repos and upload results (contents:read, security_events:write). All
GitHub API access goes through PyGithub. SARIF is POSTed to
/code-scanning/sarifs via PyGithub's requester.

Env:
  GITHUB_APP_ID            App ID
  BASE64_PRIVATE_PEM_KEY   base64-encoded App private key (PEM)
  SCAN_ORG                 optional single org to scan (else all configured)
"""

import base64
import gzip
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml
from github import Auth, Github, GithubIntegration

ORG_LIST_FILE = ".github/semgrep-scan-organizations.yml"
MATRIX_LIMIT = 256

# Minimal valid SARIF with zero findings. Uploaded when Semgrep reports no
# vulnerabilities but does not leave a usable output file, so Code scanning
# still records that analysis ran and clears any previously-open alerts.
EMPTY_SARIF = {
    "version": "2.1.0",
    "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
    "runs": [
        {
            "tool": {"driver": {"name": "Semgrep OSS", "rules": []}},
            "automationDetails": {"id": "semgrep/"},
            "results": [],
        }
    ],
}


def load_private_key() -> str:
    """Return the App private key PEM as a string.

    Accepts either the raw PEM or a base64-encoded PEM in
    BASE64_PRIVATE_PEM_KEY, so it works regardless of how the secret is stored.
    """
    raw = os.environ["BASE64_PRIVATE_PEM_KEY"].strip()
    if "-----BEGIN" in raw:
        return raw
    return base64.b64decode(raw).decode("utf-8")


def build_integration(pem: str, app_id: int) -> GithubIntegration:
    return GithubIntegration(auth=Auth.AppAuth(app_id, pem))


def installations_by_org(integration: GithubIntegration) -> dict:
    return {inst.account.login: inst.id for inst in integration.get_installations()}


def installation_token(integration: GithubIntegration, installation_id: int) -> str:
    return integration.get_access_token(installation_id).token


def scoped_upload_token(integration: GithubIntegration, installation_id: int) -> str:
    return integration.get_access_token(
        installation_id,
        permissions={
            "contents": "read",
            "security_events": "write",
            "metadata": "read",
        },
    ).token


def list_public_repos(gh: Github, org: str) -> list[dict]:
    repos = []
    for repo in gh.get_organization(org).get_repos(type="public"):
        if repo.archived or repo.fork or repo.size == 0 or not repo.default_branch:
            continue
        repos.append({"name": repo.name, "default_branch": repo.default_branch})
    return repos


def scan_repo(org: str, repo: str, branch: str, token: str, workdir: Path) -> Path | None:
    clone_url = f"https://x-access-token:{token}@github.com/{org}/{repo}.git"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, clone_url, str(workdir)],
        check=True, capture_output=True,
    )
    sarif = workdir.parent / f"{repo}.sarif"
    proc = subprocess.run(
        ["semgrep", "scan", "--sarif", "--output", str(sarif), *os.getenv("SEMGREP_CLI_OPTIONS", "").split()],
        cwd=workdir, capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):  # 1 == findings; treat as success
        print(f"::warning::semgrep failed for {org}/{repo}: {proc.stderr.strip()}")
        return None

    # A clean (no-findings) scan still emits a valid SARIF with results:[]. If
    # the file is missing/empty despite success, fall back to an empty SARIF so
    # we always upload and clear any previously-reported alerts.
    if not (sarif.is_file() and sarif.stat().st_size > 0):
        sarif.write_text(json.dumps(EMPTY_SARIF))
    return sarif


def upload_sarif(gh: Github, org: str, repo: str, branch: str, sarif: Path, workdir: Path) -> None:
    commit = subprocess.run(
        ["git", "-C", str(workdir), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()

    # Tag the SARIF run with an automation category so it shows up as a named
    # analysis configuration in the Code scanning UI.
    sarif_data = json.loads(sarif.read_text())
    if sarif_data.get("runs"):
        sarif_data["runs"][0]["automationDetails"] = {"id": "semgrep/"}
    encoded = base64.b64encode(gzip.compress(json.dumps(sarif_data).encode())).decode()

    requester = gh.requester
    _, data = requester.requestJsonAndCheck(
        "POST",
        f"/repos/{org}/{repo}/code-scanning/sarifs",
        input={
            "commit_sha": commit,
            "ref": f"refs/heads/{branch}",
            "sarif": encoded,
            "tool_name": "Semgrep OSS",
        },
    )
    status_url = data["url"]

    for _ in range(30):
        time.sleep(10)
        _, status = requester.requestJsonAndCheck("GET", status_url)
        state = status.get("processing_status", "unknown")
        print(f"  {org}/{repo}: {state}")
        if state == "complete":
            return
        if state == "failed":
            raise RuntimeError(f"SARIF processing failed for {org}/{repo}")
    print(f"::warning::{org}/{repo}: processing did not complete in time")


def configured_orgs() -> list[str]:
    return yaml.safe_load(Path(ORG_LIST_FILE).read_text()).get("organizations") or []


def scan_org(integration: GithubIntegration, installations: dict, org: str) -> int:
    """Scan every eligible public repo in one org. Returns the failure count."""
    if org not in installations:
        print(f"::error::GitHub App not installed on org '{org}'")
        return 1

    inst = installations[org]
    org_gh = Github(auth=Auth.Token(installation_token(integration, inst)))
    repos = list_public_repos(org_gh, org)
    print(f"::notice::{org}: {len(repos)} repositories to scan")
    if len(repos) > MATRIX_LIMIT:
        print(f"::warning::{org} has {len(repos)} repos (>{MATRIX_LIMIT}); scanning all anyway")

    failures = 0
    for repo in repos:
        name, branch = repo["name"], repo["default_branch"]
        try:
            token = scoped_upload_token(integration, inst)
            repo_gh = Github(auth=Auth.Token(token))
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp) / name
                sarif = scan_repo(org, name, branch, token, workdir)
                if sarif:
                    upload_sarif(repo_gh, org, name, branch, sarif, workdir)
                else:
                    print(f"::warning::{org}/{name}: no SARIF produced")
        except Exception as exc:  # keep scanning the rest of the fleet
            print(f"::error::{org}/{name}: {exc}")
            failures += 1
    return failures


def main() -> int:
    app_id = int(os.environ["GITHUB_APP_ID"])
    pem = load_private_key()

    single = os.getenv("SCAN_ORG") or (sys.argv[1] if len(sys.argv) > 1 else "")
    orgs = [single.strip()] if single.strip() else configured_orgs()
    if not orgs:
        print("::error::No organizations configured", file=sys.stderr)
        return 1

    integration = build_integration(pem, app_id)
    installations = installations_by_org(integration)

    failures = sum(scan_org(integration, installations, org) for org in orgs)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
