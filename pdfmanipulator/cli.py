"""CLI for automation; run python -m pdfmanipulator.cli --help."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .engine import WorkflowError, compile_workflow, execute_workflow

def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a validated local PDF workflow recipe.")
    parser.add_argument("--recipe", required=True, type=Path, help="Recipe JSON with steps")
    parser.add_argument("--input", action="append", required=True, metavar="ALIAS=PATH",
                        help="Input alias assignment, e.g. input1=C:\\scan.pdf")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--pattern", help="Override recipe filename pattern")
    parser.add_argument("--preview", action="store_true", help="Compile and describe output; write nothing")
    args = parser.parse_args()
    try:
        if args.recipe.stat().st_size > 200_000:
            raise WorkflowError("Recipe is too large.")
        recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
        sources = dict(pair.split("=", 1) for pair in args.input)
        pattern = args.pattern or recipe.get("pattern", "{source}_{index:02d}")
        compilation = compile_workflow(recipe["steps"], sources)
        names = __import__("pdfmanipulator.engine", fromlist=["output_names"]).output_names(compilation, pattern)
        if args.preview:
            for name, doc in zip(names, compilation.documents):
                print(f"{name}: {len(doc.pages)} pages")
        else:
            for path in execute_workflow(compilation, args.output_dir, pattern=pattern):
                print(path)
    except (WorkflowError, KeyError, ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")

if __name__ == "__main__":
    main()
