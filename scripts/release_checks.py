"""Fail closed on mismatched tags, promotion runs and published artifact bytes."""

import argparse
import hashlib
import json
import os
import re
import time
import tomllib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROJECT = "django-qbe2"


def check_tag(ref_type: str, ref_name: str, version: str) -> None:
    if ref_type != "tag" or ref_name != f"v{version}":
        raise ValueError("Select the release tag matching pyproject.toml exactly.")


def check_source_run(run: dict, jobs: list[dict], sha: str) -> None:
    expected = {
        "status": "completed",
        "conclusion": "success",
        "head_sha": sha,
        "path": ".github/workflows/release.yml",
        "event": "workflow_dispatch",
    }
    if not isinstance(run, dict) or any(run.get(k) != v for k, v in expected.items()):
        raise ValueError("Promotion requires a successful release run at this commit.")
    smoke = [job for job in jobs if job.get("name") == "Verify TestPyPI installation"]
    if len(smoke) != 1 or smoke[0].get("conclusion") != "success":
        raise ValueError("The source run must have verified the TestPyPI installation.")


def check_index_files(dist: Path, version: str, payload: dict) -> None:
    expected = {
        f"django_qbe2-{version}-py3-none-any.whl",
        f"django_qbe2-{version}.tar.gz",
    }
    if {path.name for path in dist.iterdir()} != expected:
        raise ValueError("The release must contain exactly its wheel and sdist.")
    info = payload.get("info", {})
    name = info.get("name", "")
    if (
        re.sub(r"[-_.]+", "-", name).lower() != PROJECT
        or info.get("version") != version
    ):
        raise ValueError(
            "Published metadata identifies a different project or version."
        )
    files = payload.get("urls", [])
    if len(files) != 2 or {item.get("filename") for item in files} != expected:
        raise ValueError("The index must contain both exact release artifacts once.")
    for item in files:
        path = dist / item["filename"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if item.get("digests", {}).get("sha256") != digest:
            raise ValueError(f"Published bytes differ for {path.name}.")


def read_json(url: str, *, token: str | None = None) -> dict:
    headers = {"User-Agent": "django-qbe2-release", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=10) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tag")
    promotion = commands.add_parser("promotion")
    promotion.add_argument("--run-id", type=int, required=True)
    index = commands.add_parser("index")
    index.add_argument("--dist", type=Path, required=True)
    index.add_argument("--index", choices=("testpypi", "pypi"), required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if args.command == "tag":
        check_tag(
            os.environ.get("GITHUB_REF_TYPE", ""),
            os.environ.get("GITHUB_REF_NAME", ""),
            version,
        )
    elif args.command == "promotion":
        if args.run_id < 1:
            raise ValueError("Provide the successful TestPyPI workflow run ID.")
        repository = os.environ["GITHUB_REPOSITORY"]
        url = f"https://api.github.com/repos/{repository}/actions/runs/{args.run_id}"
        token = os.environ.get("GH_TOKEN")
        run = read_json(url, token=token)
        jobs = read_json(url + "/jobs?per_page=100", token=token)["jobs"]
        check_source_run(run, jobs, os.environ["GITHUB_SHA"])
    else:
        host = "test.pypi.org" if args.index == "testpypi" else "pypi.org"
        url = f"https://{host}/pypi/{PROJECT}/{version}/json"
        for attempt in range(10):
            try:
                payload = read_json(url)
                break
            except HTTPError as error:
                if error.code != 404 or attempt == 9:
                    raise
                time.sleep(3)
        check_index_files(args.dist, version, payload)
    print(f"Release {args.command} checks passed for {version}.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(str(error)) from error
