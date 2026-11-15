"""Guard public repository layout and documentation against stale file paths."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTests(unittest.TestCase):
    def test_expected_main_structure(self):
        for name in (
            "README.md",
            "SECURITY.md",
            "Start PDFManipulator.bat",
            "launch.py",
            "pdfmanipulator/__init__.py",
            "pdfmanipulator/ui.py",
            "pdfmanipulator/engine.py",
            "pdfmanipulator/chatgpt.py",
            "packaging/build_windows.ps1",
            "packaging/create_icon.py",
            "docs/USER_GUIDE.md",
            "docs/DEVELOPER_GUIDE.md",
            "docs/LEGACY_DUPLEX.md",
            "legacy/duplex_app.py",
            "legacy/Start Legacy Duplex Scanner.bat",
        ):
            with self.subTest(file=name):
                self.assertTrue((ROOT / name).is_file(), name)

    def test_no_stale_root_launcher_or_unrelated_package(self):
        for name in ("studio", "app.py", "Start PDF Workflow Studio.bat",
                     "Start AutomaticDuplexScanning.bat", "PDFMANIPULATOR_GUIDE.md"):
            with self.subTest(file=name):
                self.assertFalse((ROOT / name).exists(), name)

    def test_readme_covers_first_run_end_to_end(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for essential in (
            "## Get started (Windows)",
            "Code", "Download ZIP",
            "Python 3.11", "Start PDFManipulator.bat",
            "+ Add PDFs", "Build workflow", "Document preview",
            "Export PDF", "## Build your own Windows EXE",
            "No.", "docs/USER_GUIDE.md",
        ):
            with self.subTest(section=essential):
                self.assertIn(essential, readme)
        self.assertNotIn("instru## Tests", readme)

    def test_internal_markdown_links_resolve(self):
        for path in (ROOT / "README.md", ROOT / "SECURITY.md", *(ROOT / "docs").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for dest in re.findall(r"\]\(([^)]+)\)", text):
                dest = dest.split("#", 1)[0]
                if not dest or "://" in dest or dest.startswith("mailto:"):
                    continue
                with self.subTest(file=path.name, link=dest):
                    self.assertTrue((path.parent / dest).resolve().is_file(),
                                    f"Broken link in {path.name}: {dest}")


if __name__ == "__main__":
    unittest.main()
