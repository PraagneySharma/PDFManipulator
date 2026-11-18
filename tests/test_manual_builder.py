"""Manual workflow tests: edit input documents separately before combining."""
import tempfile
from pathlib import Path
import unittest

from pypdf import PdfReader, PdfWriter

from pdfmanipulator.engine import (
    WorkflowError, compile_workflow, execute_workflow, validate_steps)
from pdfmanipulator.recipes import validate_recipe


class ManualBuilderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.first = self.base / "first.pdf"
        self.second = self.base / "second.pdf"
        self.third = self.base / "third.pdf"
        for file, values in (
            (self.first, [1, 2, 3]),
            (self.second, [8, 9, 10]),
            (self.third, [20, 21]),
        ):
            writer = PdfWriter()
            for value in values:
                writer.add_blank_page(width=600 + value, height=850)
            with file.open("wb") as handle:
                writer.write(handle)
        self.sources = {
            "input1": self.first,
            "input2": self.second,
            "input3": self.third,
        }
        self.out = self.base / "output"
        self.out.mkdir()

    def ids(self, path):
        return [int(p.mediabox.width) - 600 for p in PdfReader(path).pages]

    def test_delete_first_page_of_second_pdf_then_merge_first_pdf_first(self):
        first_before = self.first.read_bytes()
        second_before = self.second.read_bytes()
        plan = [
            {"op": "load_each", "sources": ["input1", "input2"]},
            {"op": "delete", "pages": "1", "document": 1},
            {"op": "merge_documents", "order": [1, 2]},
        ]
        compiled = compile_workflow(plan, self.sources)
        self.assertEqual(len(compiled.documents), 1)
        path = execute_workflow(compiled, self.out, pattern="manual")[0]
        self.assertEqual(self.ids(path), [1, 2, 3, 9, 10])
        self.assertEqual(self.first.read_bytes(), first_before)
        self.assertEqual(self.second.read_bytes(), second_before)

    def test_reversing_merge_order_preserves_pre_merge_changes(self):
        plan = [
            {"op": "load_each", "sources": ["input1", "input2"]},
            {"op": "rotate", "pages": "2", "degrees": 180, "document": 0},
            {"op": "delete", "pages": "3", "document": 1},
            {"op": "merge_documents", "order": [2, 1]},
        ]
        compiled = compile_workflow(plan, self.sources)
        output = execute_workflow(compiled, self.out, pattern="reverse")[0]
        self.assertEqual(self.ids(output), [8, 9, 1, 2, 3])
        self.assertEqual(PdfReader(output).pages[3].get("/Rotate"), 180)

    def test_three_sources_merge_with_default_order(self):
        plan = [
            {"op": "load_each", "sources": list(self.sources)},
            {"op": "delete", "pages": "1", "document": 1},
            {"op": "merge_documents"},
        ]
        compiled = compile_workflow(plan, self.sources)
        path = execute_workflow(compiled, self.out, pattern="three")[0]
        self.assertEqual(self.ids(path), [1, 2, 3, 9, 10, 20, 21])

    def test_merge_order_validation_and_target_errors(self):
        base = [{"op": "load_each", "sources": ["input1", "input2"]}]
        for order in ([1, 1], [3, 1], [1], [0, 1], [1, "2"], [], "1,2"):
            with self.subTest(order=order), self.assertRaises(WorkflowError):
                compile_workflow(base + [{"op": "merge_documents", "order": order}],
                                 self.sources)
        with self.assertRaisesRegex(WorkflowError, "targets PDF 3"):
            compile_workflow(base + [
                {"op": "delete", "pages": "1", "document": 2}],
                self.sources)
        with self.assertRaisesRegex(WorkflowError, "separate documents"):
            compile_workflow([
                {"op": "merge", "sources": ["input1", "input2"]},
                {"op": "merge_documents"}],
                self.sources)

    def test_targeted_split_then_merge_deterministic(self):
        steps = [
            {"op": "load_each", "sources": ["input1", "input2"]},
            {"op": "split_every", "n": 2, "document": 1},
            {"op": "merge_documents", "order": [1, 2, 3]},
        ]
        compiled = compile_workflow(steps, self.sources)
        output = execute_workflow(compiled, self.out, pattern="split")[0]
        self.assertEqual(self.ids(output), [1, 2, 3, 8, 9, 10])

    def test_manual_plan_can_be_saved_and_reloaded(self):
        plan = [
            {"op": "load_each", "sources": ["input1", "input2"]},
            {"op": "delete", "pages": "1", "document": 1},
            {"op": "merge_documents", "order": [1, 2]},
        ]
        stored = validate_recipe({"name": "Edit PDFs then merge",
                                  "steps": plan, "pattern": "combined"})
        self.assertEqual(stored["steps"], validate_steps(plan))


if __name__ == "__main__":
    unittest.main()
