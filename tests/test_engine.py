"""Integration tests using synthetic PDFs with page IDs encoded in their width."""
import tempfile
from pathlib import Path
import threading
import unittest

from pypdf import PdfWriter, PdfReader
from studio.engine import WorkflowError, compile_workflow, execute_workflow, output_names
from studio.parser import interpret
from studio.recipes import preset, read_recipes, save_recipes


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a, self.b = self.root / "fronts.pdf", self.root / "backs.pdf"
        self.sources = {"input1": self.a, "input2": self.b}
        self.mk(self.a, [1, 3, 5, 7, 9])
        self.mk(self.b, [10, 8, 6, 4, 2])
        (self.root / "out").mkdir()

    def mk(self, path, nums):
        writer = PdfWriter()
        for i in nums:
            writer.add_blank_page(width=600+i, height=800)
        with open(path, "wb") as stream:
            writer.write(stream)

    def ids(self, path):
        return [int(page.mediabox.width)-600 for page in PdfReader(path).pages]

    def runplan(self, steps, pattern="{source}_{index:02d}"):
        compiled = compile_workflow(steps, self.sources)
        paths = execute_workflow(compiled, self.root / "out", pattern=pattern)
        return compiled, paths

    def test_duplex_even(self):
        _, outputs = self.runplan([{"op":"duplex","fronts":"input1","backs":"input2"}])
        self.assertEqual(self.ids(outputs[0]), list(range(1,11)))

    def test_duplex_skip_blank(self):
        self.mk(self.a, [1,3,5])
        self.mk(self.b, [0,4,2])
        _, out = self.runplan([{"op":"duplex","fronts":"input1","backs":"input2","skip_first_back":True}])
        self.assertEqual(self.ids(out[0]), [1,2,3,4,5])

    def test_merge_split_chain(self):
        _, outputs = self.runplan([{"op":"merge","sources":["input1","input2"]},
                                   {"op":"split_every","n":3}])
        self.assertEqual([self.ids(p) for p in outputs], [[1,3,5],[7,9,10],[8,6,4],[2]])

    def test_split_custom_and_remainder(self):
        self.mk(self.a, list(range(1,16)))
        _, outputs = self.runplan([{"op":"load","source":"input1"},
                                   {"op":"split_ranges","ranges":["1-5","6-12"],"include_remaining":True}])
        self.assertEqual([self.ids(p) for p in outputs],
                         [list(range(1,6)),list(range(6,13)),[13,14,15]])

    def test_composite_reorder_rotate_duplicate_delete(self):
        self.mk(self.a, [1,2,3])
        _, out = self.runplan([{"op":"load","source":"input1"},
                               {"op":"reverse"},
                               {"op":"duplicate","pages":"2"},
                               {"op":"delete","pages":"4"},
                               {"op":"rotate","pages":"even","degrees":180},
                               {"op":"reorder","order":[3,1,2]}])
        self.assertEqual(self.ids(out[0]), [2,3,2])
        self.assertEqual([p.rotation for p in PdfReader(out[0]).pages], [0,0,180])

    def test_target_document_only(self):
        self.mk(self.a, [1,2,3,4])
        _, out = self.runplan([{"op":"load","source":"input1"},
                               {"op":"split_every","n":2},
                               {"op":"reverse","document":1}])
        self.assertEqual([self.ids(p) for p in out], [[1,2],[4,3]])

    def test_non_destructive_and_atomic_failure(self):
        steps = [{"op":"load","source":"input1"}]
        _, files = self.runplan(steps)
        content = files[0].read_bytes()
        with self.assertRaisesRegex(WorkflowError,"already exists"):
            self.runplan(steps)
        self.assertEqual(content, files[0].read_bytes())
        comp = compile_workflow(steps,self.sources)
        with self.assertRaisesRegex(WorkflowError,"overwrite an input"):
            execute_workflow(comp,self.root,pattern="fronts")

    def test_filename_security(self):
        comp = compile_workflow([{"op":"load","source":"input1"},{"op":"split_every","n":2}],self.sources)
        for pattern in ["same","../outside","{name.__class__}","{index!r}"]:
            with self.subTest(pattern=pattern),self.assertRaises(WorkflowError):
                output_names(comp,pattern)

    def test_blank_page_cleanup(self):
        self.mk(self.a,[1,2])
        with self.assertRaisesRegex(WorkflowError,"empty PDF"):
            compile_workflow([{"op":"load","source":"input1"},{"op":"remove_blanks"}],self.sources)

    def test_fail_closed(self):
        for steps in [
            [{"op":"load","source":"input1"},{"op":"rotate","pages":"all","degrees":45}],
            [{"op":"load","source":"input1"},{"op":"split_every","n":0}],
            [{"op":"load","source":"input1"},{"op":"script","code":"eval"}],
            [{"op":"load","source":"input1"},{"op":"delete","pages":"100"}],
            [{"op":"load","source":"input1"},{"op":"reorder","order":[1,2]}],
        ]:
            with self.subTest(steps=steps),self.assertRaises(WorkflowError):
                compile_workflow(steps,self.sources)
        with self.assertRaisesRegex(WorkflowError,"outside"):
            compile_workflow([{"op":"load","source":"input1"}],self.sources,
                             allowed_root=self.root / "out")
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(WorkflowError,"Canceled"):
            compile_workflow([{"op":"load","source":"input1"}],self.sources,cancel=cancel)

    def test_offline_parser_and_recipes(self):
        self.assertEqual(interpret("Split every 3 pages",["input1"])[1],
                         {"op":"split_every","n":3})
        self.assertEqual(interpret("Rotate even pages 180 degrees",["input1"])[1]["pages"],"even")
        self.assertEqual(interpret("Merge PDFs",["input1","input2"])[0]["op"],"merge")
        saved = preset("Duplex Scan Merger")
        location = self.root / "recipes.json"
        save_recipes({saved["name"]:saved}, location)
        self.assertEqual(read_recipes(location)[saved["name"]]["steps"],saved["steps"])

    def test_batch_extract(self):
        self.mk(self.a,[1,2,3])
        _, out = self.runplan([{"op":"load_each","sources":["input1","input2"]},
                               {"op":"extract","pages":"1"}])
        self.assertEqual([self.ids(path) for path in out],[[1],[10]])


if __name__ == "__main__":
    unittest.main()
