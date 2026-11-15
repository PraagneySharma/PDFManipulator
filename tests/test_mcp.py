"""Optional MCP server tool integration tests with a restricted local directory."""
import asyncio
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfWriter, PdfReader
from pdfmanipulator.engine import WorkflowError

try:
    from pdfmanipulator.mcp_server import make_server
    import mcp
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "Optional MCP SDK is not installed")
class MCPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        writer = PdfWriter()
        writer.add_blank_page(width=610, height=800)
        writer.add_blank_page(width=620, height=800)
        with (self.root / "input.pdf").open("wb") as file:
            writer.write(file)
        (self.root / "output").mkdir()

    def test_server_tools_available(self):
        tools = asyncio.run(make_server(self.root).list_tools())
        self.assertEqual({t.name for t in tools},
                         {"list_pdf_presets","preview_pdf_workflow","execute_pdf_workflow"})

    def test_preview_and_guarded_execution(self):
        server = make_server(self.root)
        steps = [{"op":"load","source":"input1"},{"op":"reverse"}]
        async def run():
            first = await server.call_tool("preview_pdf_workflow",
                {"steps":steps,"inputs":{"input1":"input.pdf"}})
            second = await server.call_tool("execute_pdf_workflow",
                {"steps":steps,"inputs":{"input1":"input.pdf"},
                 "output_subdir":"output", "filename_pattern":"sorted_{index:02d}"})
            return first,second
        result = asyncio.run(run())
        self.assertFalse(result[0].is_error)
        self.assertFalse(result[1].is_error)
        path = self.root/"output"/"sorted_01.pdf"
        self.assertTrue(path.is_file())
        self.assertEqual([int(p.mediabox.width) for p in PdfReader(path).pages],[620,610])
        self.assertEqual([int(p.mediabox.width) for p in PdfReader(self.root/"input.pdf").pages],
                         [610,620])


if __name__ == "__main__":
    unittest.main()
