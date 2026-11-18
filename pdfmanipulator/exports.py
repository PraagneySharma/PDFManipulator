"""Safe, non-overwriting export-name selection for the desktop Save As workflow."""
from __future__ import annotations

from pathlib import Path

from .engine import Compilation, WorkflowError, output_names


def next_available_pattern(compilation: Compilation, directory: str | Path,
                           pattern: str) -> tuple[str, list[str]]:
    """Return unique batch filenames without touching existing PDFs or sources."""
    folder = Path(directory).expanduser().resolve()
    if not folder.is_dir():
        raise WorkflowError("Choose an existing output folder.")
    source_paths = set(compilation.sources.values())
    for version in range(1, 501):
        candidate = pattern if version == 1 else f"{pattern}_v{version}"
        names = output_names(compilation, candidate)
        targets = [folder / name for name in names]
        if all(target.resolve() not in source_paths and not target.exists() for target in targets):
            return candidate, names
    raise WorkflowError("Could not find available filenames. Choose another folder.")
