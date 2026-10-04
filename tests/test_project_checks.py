#!/usr/bin/env python3
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

CHECK_PROJECT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_project.py"
)
SPEC = importlib.util.spec_from_file_location(
    "project_check_script", CHECK_PROJECT_PATH
)
assert SPEC is not None and SPEC.loader is not None
check_project = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_project)


class ProjectChecksTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_dir = pathlib.Path(tmp.name)

    def write_requirements(self, content: str) -> pathlib.Path:
        path = self.tmp_dir / "requirements.txt"
        path.write_text(content, encoding="utf-8")
        return path

    def test_requirements_audit_accepts_google_genai_without_namespace_package(self):
        path = self.write_requirements(
            "# import google.genai\ngoogle-genai\nrequests\n"
        )
        self.assertEqual(
            check_project.declared_requirement_names(path), ["google-genai", "requests"]
        )

    def test_requirements_audit_rejects_standalone_google(self):
        self.write_requirements("google-genai\ngoogle==3.0.0\n")
        with (
            mock.patch.object(check_project, "ROOT", self.tmp_dir),
            self.assertRaisesRegex(check_project.CheckFailure, "(?i)google"),
        ):
            check_project.check_requirements()


if __name__ == "__main__":
    unittest.main()
