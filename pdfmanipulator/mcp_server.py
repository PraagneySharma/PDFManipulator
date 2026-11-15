"""Optional, narrowly scoped local stdio MCP server.

Requires official MCP SDK v2: pip install 'mcp>=2,<3'
Only handles files relative to an explicit authorized root. No shell, code, or
network tools. Never exposes an unauthenticated HTTP endpoint.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from .engine import WorkflowError, compile_workflow, execute_workflow
from .recipes import PRESETS

def make_server(root: Path):
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise WorkflowError("Install the optional MCP SDK: pip install 'mcp>=2,<3'.") from exc

    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise WorkflowError("Authorized root must be an existing directory.")
    server = MCPServer("PDFManipulator")

    def paths(inputs: dict[str, str]) -> dict[str, Path]:
        if len(inputs) > 30:
            raise WorkflowError("At most 30 input files.")
        result: dict[str, Path] = {}
        for alias, value in inputs.items():
            if not isinstance(alias, str) or not alias.startswith("input") or not alias[5:].isdigit():
                raise WorkflowError("Input aliases must be input1, input2, etc.")
            if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
                raise WorkflowError("Paths must be relative to the authorized root without '..'.")
            file = (root / value).resolve()
            if not file.is_relative_to(root):
                raise WorkflowError("Input is outside authorized root.")
            result[alias] = file
        return result

    @server.tool()
    def list_pdf_presets() -> dict:
        """List deterministic PDF operations and preset recipes."""
        return {name: item["steps"] for name, item in PRESETS.items()}

    @server.tool()
    def preview_pdf_workflow(steps: list[dict], inputs: dict[str, str]) -> dict:
        """Validate and preview a PDF workflow without saving or changing files."""
        comp = compile_workflow(steps, paths(inputs), allowed_root=root)
        return {"documents": [{"pages": len(d.pages),
                               "sources": sorted(set(p.source for p in d.pages))}
                              for d in comp.documents], "warnings": comp.warnings}

    @server.tool()
    def execute_pdf_workflow(steps: list[dict], inputs: dict[str, str],
                             output_subdir: str, filename_pattern: str = "{source}_{index:02d}") -> dict:
        """Write PDFs after validation. Existing outputs are never overwritten.

        Calls to this tool should require user confirmation in the MCP client.
        """
        if not isinstance(output_subdir, str) or Path(output_subdir).is_absolute() or ".." in Path(output_subdir).parts:
            raise WorkflowError("Output folder must be relative to authorized root.")
        folder = (root / output_subdir).resolve()
        if not folder.is_relative_to(root) or not folder.is_dir():
            raise WorkflowError("Output folder must exist inside authorized root.")
        comp = compile_workflow(steps, paths(inputs), allowed_root=root)
        written = execute_workflow(comp, folder, pattern=filename_pattern, allowed_root=root)
        return {"created": [str(path.relative_to(root)) for path in written]}

    return server

def main():
    parser = argparse.ArgumentParser(description="Local MCP tools for an authorized PDF folder.")
    parser.add_argument("--root", required=True, type=Path, help="ONLY accessible folder")
    args = parser.parse_args()
    make_server(args.root).run(transport="stdio")

if __name__ == "__main__":
    main()
