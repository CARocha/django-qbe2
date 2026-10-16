import hashlib
import tempfile
import tomllib
from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from scripts.release_checks import check_index_files, check_source_run, check_tag

VERSION = "0.1.0a1"
SHA = "a" * 40


class ReleaseChecksTests(TestCase):
    def test_repository_metadata_targets_the_first_stable_release(self):
        root = Path(__file__).resolve().parent.parent
        metadata = tomllib.loads((root / "pyproject.toml").read_text())
        self.assertEqual(metadata["project"]["version"], "1.0.0")
        self.assertIn("1.0.0", (root / "CHANGELOG.md").read_text())

    def test_tag_must_identify_the_exact_metadata_version(self):
        check_tag("tag", f"v{VERSION}", VERSION)
        for kind, name in (
            ("branch", "main"),
            ("branch", f"v{VERSION}"),
            ("tag", "v0.1.0"),
            ("tag", VERSION),
        ):
            with self.subTest(kind=kind, name=name), self.assertRaises(ValueError):
                check_tag(kind, name, VERSION)

    def source_run(self):
        return {
            "status": "completed",
            "conclusion": "success",
            "head_sha": SHA,
            "path": ".github/workflows/release.yml",
            "event": "workflow_dispatch",
        }

    def test_promotion_requires_a_successful_smoke_run_from_the_same_commit(self):
        jobs = [{"name": "Verify TestPyPI installation", "conclusion": "success"}]
        check_source_run(self.source_run(), jobs, SHA)
        for key, value in (
            ("status", "in_progress"),
            ("conclusion", "failure"),
            ("head_sha", "b" * 40),
            ("path", ".github/workflows/ci.yml"),
            ("event", "push"),
        ):
            run = self.source_run()
            run[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_source_run(run, jobs, SHA)
        for invalid_jobs in ([], [{"name": jobs[0]["name"], "conclusion": "failure"}]):
            with self.subTest(jobs=invalid_jobs), self.assertRaises(ValueError):
                check_source_run(self.source_run(), invalid_jobs, SHA)

    def test_both_artifacts_must_match_the_published_project_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory)
            names = (
                f"django_qbe2-{VERSION}-py3-none-any.whl",
                f"django_qbe2-{VERSION}.tar.gz",
            )
            for name in names:
                (dist / name).write_bytes(name.encode())
            payload = {
                "info": {"name": "django-qbe2", "version": VERSION},
                "urls": [
                    {
                        "filename": name,
                        "digests": {
                            "sha256": hashlib.sha256(name.encode()).hexdigest()
                        },
                    }
                    for name in names
                ],
            }
            check_index_files(dist, VERSION, payload)
            for change in ("hash", "missing", "duplicate", "project", "version"):
                bad = deepcopy(payload)
                if change == "hash":
                    bad["urls"][0]["digests"]["sha256"] = "0" * 64
                elif change == "missing":
                    bad["urls"].pop()
                elif change == "duplicate":
                    bad["urls"].append(bad["urls"][0])
                else:
                    bad["info"]["name" if change == "project" else "version"] = "other"
                with self.subTest(change=change), self.assertRaises(ValueError):
                    check_index_files(dist, VERSION, bad)
            (dist / names[0]).write_bytes(b"different bytes")
            with self.assertRaises(ValueError):
                check_index_files(dist, VERSION, payload)
