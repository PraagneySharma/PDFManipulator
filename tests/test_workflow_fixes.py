"""Regressions for PDF insertion, page editing, zoom and export."""
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from pdfmanipulator.ai import parse_model_steps, translate
from pdfmanipulator.engine import WorkflowError, compile_workflow, execute_workflow
from pdfmanipulator.exports import next_available_pattern
from pdfmanipulator.layout import thumbnail_layout, fit_image_size, output_tab_title
from pdfmanipulator.parser import interpret


REQUEST = ("Delete the first Page of the first PDF. "
           "Add the second PDF to the first PDF and make sure the second PDF is page 1")


class PDFEditingRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.first = self.root / "first.pdf"
        self.second = self.root / "second.pdf"
        self.mk(self.first, [1, 2, 3, 4])
        self.mk(self.second, [8, 9])
        self.sources = {"input1": self.first, "input2": self.second}
        self.out = self.root / "out"
        self.out.mkdir()

    @staticmethod
    def mk(path, numbers):
        writer = PdfWriter()
        for number in numbers:
            writer.add_blank_page(width=600 + number, height=800)
        with path.open("wb") as f:
            writer.write(f)

    @staticmethod
    def ids(path):
        return [int(p.mediabox.width) - 600 for p in PdfReader(str(path)).pages]

    def test_users_exact_instruction_preserves_both_operations(self):
        original_first = self.first.read_bytes()
        original_second = self.second.read_bytes()
        steps = interpret(REQUEST, list(self.sources))
        self.assertEqual(steps, [
            {"op": "load", "source": "input1"},
            {"op": "delete", "pages": "1"},
            {"op": "insert_pdf", "source": "input2", "position": 1}])
        compilation = compile_workflow(steps, self.sources)
        self.assertEqual(
            [(page.source, page.index) for page in compilation.documents[0].pages],
            [("input2", 0), ("input2", 1), ("input1", 1),
             ("input1", 2), ("input1", 3)])
        result = execute_workflow(compilation, self.out, pattern="requested")
        self.assertEqual(len(result), 1)
        self.assertEqual(self.ids(result[0]), [8, 9, 2, 3, 4])
        self.assertEqual(self.first.read_bytes(), original_first)
        self.assertEqual(self.second.read_bytes(), original_second)

    def test_cloud_provider_does_not_drop_multifile_steps(self):
        # Recognized instructions are processed locally, without any API call.
        steps = translate(REQUEST, list(self.sources), provider="openai", consent=False)
        self.assertEqual(steps[-1], {"op": "insert_pdf", "source": "input2", "position": 1})

    def test_ai_json_accepts_insert_pdf(self):
        import json
        content = json.dumps({"steps": [
            {"op": "load", "source": "input1"},
            {"op": "delete", "pages": "1"},
            {"op": "insert_pdf", "source": "input2", "position": 1}]})
        self.assertEqual(len(parse_model_steps(content, list(self.sources))), 3)

    def test_insert_middle_and_append(self):
        middle = [{"op": "load", "source": "input1"},
                  {"op": "insert_pdf", "source": "input2", "position": 3}]
        compilation = compile_workflow(middle, self.sources)
        self.assertEqual([p.source for p in compilation.documents[0].pages],
                         ["input1", "input1", "input2", "input2", "input1", "input1"])
        end = [{"op": "load", "source": "input1"},
               {"op": "insert_pdf", "source": "input2", "position": "end"}]
        compilation = compile_workflow(end, self.sources)
        self.assertEqual([p.source for p in compilation.documents[0].pages],
                         ["input1"] * 4 + ["input2"] * 2)

    def test_insert_rejects_missing_source_or_invalid_position(self):
        for position in (0, -1, 2.5, "start", True):
            with self.subTest(position=position), self.assertRaises(WorkflowError):
                compile_workflow([
                    {"op": "load", "source": "input1"},
                    {"op": "insert_pdf", "source": "input2", "position": position}],
                    self.sources)
        for source, position in (("input3", 1), ("input2", 7)):
            with self.subTest(source=source, position=position), self.assertRaises(WorkflowError):
                compile_workflow([
                    {"op": "load", "source": "input1"},
                    {"op": "insert_pdf", "source": source, "position": position}],
                    self.sources)

    def test_multipdf_delete_different_page_does_not_infer_page_one(self):
        steps = interpret("Delete page 3 of the first PDF. Add the second PDF "
                          "and make the second PDF page 1", list(self.sources))
        self.assertEqual(steps[1], {"op": "delete", "pages": "3"})

    def test_single_pdf_delete_and_export(self):
        steps = [{"op": "load", "source": "input1"}, {"op": "delete", "pages": "1"}]
        comp = compile_workflow(steps, self.sources)
        saved = execute_workflow(comp, self.out, pattern="edited")
        self.assertEqual(self.ids(saved[0]), [2, 3, 4])

    def test_existing_batch_output_gets_new_safe_name(self):
        comp = compile_workflow([{"op": "load", "source": "input1"},
                                {"op": "split_every", "n": 2}], self.sources)
        (self.out / "result_01.pdf").write_bytes(b"existing untouched")
        pattern, names = next_available_pattern(comp, self.out, "result_{index:02d}")
        self.assertEqual(pattern, "result_{index:02d}_v2")
        self.assertEqual(names, ["result_01_v2.pdf", "result_02_v2.pdf"])
        result = execute_workflow(comp, self.out, pattern=pattern)
        self.assertEqual(len(result), 2)
        self.assertEqual((self.out / "result_01.pdf").read_bytes(), b"existing untouched")

    def test_zoom_increases_both_dimensions_and_reduces_columns(self):
        base = thumbnail_layout(960, 1.0)
        zoomed = thumbnail_layout(960, 1.4)
        self.assertEqual(base[0], 3)  # Readable whole pages, not six tiny slices.
        self.assertLess(zoomed[0], base[0])
        self.assertGreater(zoomed[1], base[1])
        self.assertGreater(zoomed[2], base[2])
        self.assertEqual(thumbnail_layout(480, 1.0)[0], 2)
        self.assertGreaterEqual(thumbnail_layout(960, 0.7)[0], base[0])

    def test_full_page_fit_preserves_tall_portrait_and_landscape_aspect(self):
        for page_width, page_height in ((612, 792), (612, 1008), (1008, 612), (450, 1400)):
            with self.subTest(page=(page_width, page_height)):
                result_width, result_height = fit_image_size(
                    page_width, page_height, max_width=580, max_height=520)
                self.assertLessEqual(result_width, 580)
                self.assertLessEqual(result_height, 520)
                self.assertAlmostEqual(result_width / result_height,
                                       page_width / page_height, delta=0.012)
                self.assertGreater(result_width, 0)
                self.assertGreater(result_height, 0)

    def test_preview_tabs_show_original_names_not_output_numbers(self):
        comp = compile_workflow([
            {"op": "load_each", "sources": ["input1", "input2"]}
        ], self.sources)
        labels = [output_tab_title(i, doc, self.sources, len(comp.documents))
                  for i, doc in enumerate(comp.documents)]
        self.assertIn("PDF 1", labels[0])
        self.assertIn("first.pdf", labels[0])
        self.assertIn("PDF 2", labels[1])
        self.assertIn("second.pdf", labels[1])
        self.assertFalse(any("Output" in label for label in labels))
        merged = compile_workflow([
            {"op": "merge", "sources": ["input1", "input2"]}
        ], self.sources)
        self.assertIn("Combined PDF", output_tab_title(
            0, merged.documents[0], self.sources, 1))


if __name__ == "__main__":
    unittest.main()
