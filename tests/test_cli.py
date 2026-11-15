"""Public CLI end-to-end regression test with a recipe's filename pattern."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from pypdf import PdfWriter, PdfReader

class CLITests(unittest.TestCase):
    def test_recipe_preview_run_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            scan=root/"scan.pdf"
            out=root/"out"
            out.mkdir()
            writer=PdfWriter()
            for width in (601,602,603,604,605):
                writer.add_blank_page(width=width,height=800)
            with scan.open("wb") as f:
                writer.write(f)
            recipe=root/"plan.json"
            recipe.write_text(json.dumps({
                "name":"every two","pattern":"chunk_{index:02d}",
                "steps":[{"op":"load","source":"input1"},{"op":"split_every","n":2}]}),
                encoding="utf-8")
            cmd=[sys.executable,"-m","studio.cli","--recipe",str(recipe),
                 "--input",f"input1={scan}","--output-dir",str(out)]
            preview=subprocess.run(cmd+["--preview"],capture_output=True,text=True)
            self.assertEqual(preview.returncode,0,preview.stderr)
            self.assertIn("chunk_01.pdf: 2 pages",preview.stdout)
            self.assertFalse(list(out.glob("*.pdf")))
            run=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(len(list(out.glob("*.pdf"))),3)
            self.assertEqual([int(p.mediabox.width) for p in PdfReader(out/"chunk_01.pdf").pages],[601,602])
            duplicate=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(duplicate.returncode,0)
            self.assertIn("already exists",duplicate.stderr)

if __name__=="__main__":
    unittest.main()
