"""Built-in presets and user recipe persistence (no document contents stored)."""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
from copy import deepcopy

from .engine import WorkflowError, validate_steps

PRESETS: dict[str, dict] = {
    "Duplex Scan Merger": {"steps": [{"op": "duplex", "fronts": "input1", "backs": "input2", "reverse_backs": True, "rotate_backs": False}], "description": "Interleave a front scan with the reversed back scan."},
    "Split Every N Pages": {"steps": [{"op": "load", "source": "input1"}, {"op": "split_every", "n": 3}], "description": "Produce one file per 3 pages (editable)."},
    "Custom Page Splitter": {"steps": [{"op": "load", "source": "input1"}, {"op": "split_ranges", "ranges": ["1-5"], "include_remaining": True}], "description": "Split into custom page ranges."},
    "PDF Merger": {"steps": [{"op": "merge", "sources": ["input1", "input2"]}], "description": "Combine multiple PDFs in the chosen order."},
    "Extract Selected Pages": {"steps": [{"op": "load", "source": "input1"}, {"op": "extract", "pages": "1"}], "description": "Pull selected pages into a new document."},
    "Reverse Page Order": {"steps": [{"op": "load", "source": "input1"}, {"op": "reverse"}], "description": "Reverse an entire PDF."},
    "Rotate Scanned Pages": {"steps": [{"op": "load", "source": "input1"}, {"op": "rotate", "pages": "even", "degrees": 180}], "description": "Rotate every even-numbered page."},
    "Remove Blank Pages": {"steps": [{"op": "load", "source": "input1"}, {"op": "remove_blanks", "threshold": 0.003}], "description": "Conservatively detect and remove blank scans."},
    "Batch PDF Organizer": {"steps": [{"op": "load_each", "sources": ["input1", "input2"]}], "description": "Process multiple PDFs independently, then name their outputs."},
}

def store_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    current = base / "PDFManipulator" / "recipes.json"
    legacy = base / "PDFWorkflowStudio" / "recipes.json"
    if not current.exists() and legacy.is_file():
        try:
            current.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, current)
        except OSError as exc:
            raise WorkflowError("Could not migrate existing saved workflows.") from exc
    return current

def validate_recipe(data: object) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise WorkflowError("Recipe must contain a name and steps.")
    name = data["name"].strip()
    if not name or len(name) > 90:
        raise WorkflowError("Recipe name must be between 1 and 90 characters.")
    steps = validate_steps(data.get("steps"))
    pattern = data.get("pattern", "{source}_{index:02d}")
    if not isinstance(pattern, str) or len(pattern) > 150:
        raise WorkflowError("Invalid output filename pattern.")
    return {"name": name, "steps": steps, "pattern": pattern}

def read_recipes(path: Path | None = None) -> dict[str, dict]:
    location = path or store_path()
    if not location.is_file():
        return {}
    try:
        data = json.loads(location.read_text(encoding="utf-8"))
        if not isinstance(data, list) or len(data) > 1000:
            raise ValueError("Expected a list of recipes")
        validated = [validate_recipe(item) for item in data]
        return {item["name"]: item for item in validated}
    except (OSError, ValueError, TypeError) as exc:
        raise WorkflowError(f"Saved recipes cannot be read: {exc}") from exc

def save_recipes(recipes: dict[str, dict], path: Path | None = None) -> None:
    location = path or store_path()
    location.parent.mkdir(parents=True, exist_ok=True)
    clean = [validate_recipe(recipe) for recipe in recipes.values()]
    if len(clean) > 1000:
        raise WorkflowError("Too many saved recipes.")
    temporary = location.with_name(location.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(clean, stream, indent=2)
        os.replace(temporary, location)
    finally:
        temporary.unlink(missing_ok=True)

def export_recipe(recipe: dict, path: Path) -> None:
    clean = validate_recipe(recipe)
    with path.open("x", encoding="utf-8") as out:
        json.dump(clean, out, indent=2)

def import_recipe(path: Path) -> dict:
    if path.stat().st_size > 200_000:
        raise WorkflowError("Recipe file is too large.")
    try:
        return validate_recipe(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError, TypeError) as exc:
        raise WorkflowError(f"Invalid recipe file: {exc}") from exc

def preset(name: str) -> dict:
    if name not in PRESETS:
        raise WorkflowError(f"Unknown preset: {name}")
    return {"name": name, "steps": deepcopy(PRESETS[name]["steps"]), "pattern": "{source}_{index:02d}"}
