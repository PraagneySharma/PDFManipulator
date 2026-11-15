"""Deterministic, validated, local PDF workflow compiler and executor.

Plans contain JSON-serializable operations, never executable code. Page references
are compiled without changing source files; only the final output step writes PDFs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable
import os
import re
import shutil
import string
import tempfile
import threading

from pypdf import PdfReader, PdfWriter


class WorkflowError(ValueError):
    """Expected user-facing PDF or workflow validation error."""


@dataclass(frozen=True)
class PageRef:
    source: str
    index: int  # zero-based page in the source PDF
    rotation: int = 0


@dataclass
class Document:
    pages: list[PageRef]
    source_name: str = "document"


@dataclass
class Compilation:
    documents: list[Document]
    sources: dict[str, Path]
    steps: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return sum(len(doc.pages) for doc in self.documents)


_ALLOWED: dict[str, set[str]] = {
    "load": {"source"},
    "load_each": {"sources"},
    "merge": {"sources"},
    "duplex": {"fronts", "backs", "reverse_backs", "rotate_backs", "skip_first_back"},
    "interleave": {"sources", "reverse_second"},
    "split_every": {"n"},
    "split_ranges": {"ranges", "include_remaining"},
    "extract": {"pages", "document"},
    "delete": {"pages", "document"},
    "reorder": {"order", "document"},
    "reverse": {"document"},
    "rotate": {"pages", "degrees", "document"},
    "duplicate": {"pages", "times", "document"},
    "remove_blanks": {"threshold", "document"},
}
MAX_STEPS = 80
MAX_PAGES = 25000
MAX_DOCUMENTS = 2000
MAX_SOURCE_BYTES = 1024 * 1024 * 1024  # reject unexpectedly enormous files
MAX_OUTPUT_PAGES = 100000


def _positive_int(value: Any, field_name: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise WorkflowError(f"{field_name} must be an integer of at least {minimum}.")
    return value


def parse_pages(spec: Any, length: int, *, unique: bool = True) -> list[int]:
    """Convert human 1-based page specifications into zero-based indices.

    Supports '1,3,5-7', 'all', 'odd', 'even', or a list of page numbers.
    """
    if length < 0:
        raise WorkflowError("Invalid document length.")
    if isinstance(spec, list):
        raw = [_positive_int(v, "Page number") for v in spec]
    elif isinstance(spec, str):
        value = spec.strip().lower()
        if value in ("all", "*"):
            raw = list(range(1, length + 1))
        elif value == "odd":
            raw = list(range(1, length + 1, 2))
        elif value == "even":
            raw = list(range(2, length + 1, 2))
        else:
            raw = []
            if not value:
                raise WorkflowError("Enter page numbers such as 1,3,5-7.")
            for part in value.split(","):
                part = part.strip()
                m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
                if m:
                    a, b = int(m[1]), int(m[2])
                    if a > b:
                        raise WorkflowError(f"Range {part} goes backwards.")
                    if b - a > MAX_OUTPUT_PAGES:
                        raise WorkflowError("Page range is too large.")
                    raw.extend(range(a, b + 1))
                elif re.fullmatch(r"\d+", part):
                    raw.append(int(part))
                else:
                    raise WorkflowError(f"Invalid page selection: {part!r}. Use 1,3,5-7.")
    else:
        raise WorkflowError("Page selection must be a string or list of page numbers.")
    if not raw and length:
        raise WorkflowError("Page selection is empty.")
    for number in raw:
        if number < 1 or number > length:
            raise WorkflowError(f"Page {number} is outside this {length}-page document.")
    if unique and len(set(raw)) != len(raw):
        raise WorkflowError("Page selection contains duplicates.")
    return [v - 1 for v in raw]


def validate_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        raise WorkflowError(f"A workflow needs 1–{MAX_STEPS} steps.")
    validated = []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not isinstance(step.get("op"), str):
            raise WorkflowError(f"Step {i} must be an operation object.")
        op = step["op"]
        if op not in _ALLOWED:
            raise WorkflowError(f"Step {i}: unsupported operation {op!r}.")
        extra = set(step) - {"op"} - _ALLOWED[op]
        if extra:
            raise WorkflowError(f"Step {i}: unexpected parameters {', '.join(sorted(extra))}.")
        if op in ("load", "duplex") and not isinstance(step.get("source", step.get("fronts")), str):
            raise WorkflowError(f"Step {i} needs a source alias.")
        if op in ("load_each", "merge", "interleave"):
            names = step.get("sources")
            if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
                raise WorkflowError(f"Step {i}: sources must list input aliases.")
            if op == "interleave" and len(names) != 2:
                raise WorkflowError("Interleave requires exactly two sources.")
        if op == "split_every":
            _positive_int(step.get("n"), "Split size")
        if op == "rotate":
            if step.get("degrees") not in (90, 180, 270, -90, -180, -270):
                raise WorkflowError("Rotation must be ±90, ±180, or ±270 degrees.")
        if op == "duplicate":
            times = _positive_int(step.get("times", 1), "Duplicate times")
            if times > 20:
                raise WorkflowError("Duplicate times must not exceed 20.")
        if "document" in step:
            _positive_int(step["document"], "Document index", 0)
        if op == "split_ranges":
            ranges = step.get("ranges")
            if not isinstance(ranges, list) or not ranges or len(ranges) > MAX_DOCUMENTS:
                raise WorkflowError("Split ranges must be a nonempty list of selections.")
            if not all(isinstance(r, (str, list)) for r in ranges):
                raise WorkflowError("Split ranges must contain page selections.")
        if op == "reorder" and not isinstance(step.get("order"), list):
            raise WorkflowError("Reorder requires an 'order' array of 1-based page indices.")
        if op in ("extract", "delete", "rotate", "duplicate") and "pages" not in step:
            raise WorkflowError(f"Step {i}: select pages.")
        if op == "remove_blanks":
            threshold = step.get("threshold", 0.003)
            if type(threshold) not in (float, int) or not 0 <= threshold <= 0.05:
                raise WorkflowError("Blank detection threshold must be between 0 and 0.05.")
        for flag in ("reverse_backs", "rotate_backs", "skip_first_back", "reverse_second", "include_remaining"):
            if flag in step and type(step[flag]) is not bool:
                raise WorkflowError(f"{flag} must be true or false.")
        validated.append(dict(step))
    if validated[0]["op"] not in ("load", "load_each", "merge", "duplex", "interleave"):
        raise WorkflowError("First step must load, merge, duplex, or interleave input files.")
    for step in validated[1:]:
        if step["op"] in ("load", "load_each", "merge", "duplex", "interleave"):
            raise WorkflowError("Source-loading operations must be the first step.")
    return validated


def _safe_path(path: str | Path, allowed_root: Path | None = None) -> Path:
    result = Path(path).expanduser().resolve()
    if allowed_root is not None and not result.is_relative_to(allowed_root.resolve()):
        raise WorkflowError("File is outside the explicitly authorized workspace.")
    return result


def _reader(path: Path) -> PdfReader:
    if not path.is_file():
        raise WorkflowError(f"Input PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise WorkflowError(f"Not a .pdf file: {path.name}")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise WorkflowError(f"Input exceeds the 1 GiB safety limit: {path.name}")
    try:
        with path.open("rb") as src:
            if not src.read(1024).lstrip().startswith(b"%PDF-"):
                raise WorkflowError(f"{path.name} does not have a valid PDF header.")
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise WorkflowError(f"{path.name} is password-protected. Unlock it first.")
        if len(reader.pages) > MAX_PAGES:
            raise WorkflowError(f"{path.name} exceeds the {MAX_PAGES:,}-page limit.")
        return reader
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError(f"Cannot read {path.name}: {exc}") from exc


def _is_blank(path: Path, index: int, threshold: float) -> bool:
    """Conservative pixel-based heuristic; never edits source."""
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise WorkflowError("Blank detection requires PyMuPDF (install optional preview dependencies).") from exc
    try:
        with fitz.open(str(path)) as pdf:
            page = pdf.load_page(index)
            if page.get_text("text").strip():
                return False
            pix = page.get_pixmap(matrix=fitz.Matrix(0.35, 0.35), colorspace=fitz.csGRAY, alpha=False)
            samples = pix.samples
            if not samples:
                return True
            # Dark-pixel ratio. A sparse signature or very faint logo can be mistaken for blank.
            nonwhite = sum(p < 245 for p in samples)
            return nonwhite / len(samples) <= threshold
    except Exception as exc:
        raise WorkflowError(f"Could not inspect blank page {index + 1} of {path.name}: {exc}") from exc


def compile_workflow(
    steps: Any,
    sources: dict[str, str | Path],
    *,
    allowed_root: Path | None = None,
    cancel: threading.Event | None = None,
) -> Compilation:
    validated = validate_steps(steps)
    if not isinstance(sources, dict) or not sources:
        raise WorkflowError("Add at least one PDF.")
    source_paths = {key: _safe_path(value, allowed_root) for key, value in sources.items()
                    if isinstance(key, str) and isinstance(value, (str, Path))}
    if len(source_paths) != len(sources):
        raise WorkflowError("Invalid input alias or file path.")
    # pypdf page objects stay in process memory; references stay lightweight until saving.
    readers: dict[str, PdfReader] = {}
    def get_pages(alias: str) -> list[PageRef]:
        if alias not in source_paths:
            raise WorkflowError(f"Missing input '{alias}'. Add the required PDF.")
        if alias not in readers:
            readers[alias] = _reader(source_paths[alias])
        return [PageRef(alias, i) for i in range(len(readers[alias].pages))]

    documents: list[Document] = []
    warnings: list[str] = []
    blank_cache: dict[tuple[str, int, float], bool] = {}
    for position, step in enumerate(validated):
        if cancel is not None and cancel.is_set():
            raise WorkflowError("Canceled.")
        op = step["op"]
        if op == "load":
            alias = step["source"]
            documents = [Document(get_pages(alias), Path(source_paths[alias]).stem)]
        elif op == "load_each":
            documents = [Document(get_pages(a), Path(source_paths[a]).stem) for a in step["sources"]]
        elif op == "merge":
            documents = [Document([p for a in step["sources"] for p in get_pages(a)], "merged")]
        elif op == "interleave":
            a, b = step["sources"]
            front, back = get_pages(a), get_pages(b)
            if step.get("reverse_second", False):
                back.reverse()
            if abs(len(front) - len(back)) > 1:
                raise WorkflowError("Interleave requires inputs differing by at most one page.")
            combined: list[PageRef] = []
            for i in range(max(len(front), len(back))):
                if i < len(front):
                    combined.append(front[i])
                if i < len(back):
                    combined.append(back[i])
            documents = [Document(combined, "interleaved")]
        elif op == "duplex":
            front = get_pages(step["fronts"])
            back = get_pages(step["backs"]) if step.get("backs") else []
            skip_first = step.get("skip_first_back", False)
            if skip_first and len(front) != len(back):
                raise WorkflowError("Skipping the first blank back requires equal input page counts.")
            if len(back) not in (len(front), len(front) - 1):
                raise WorkflowError(f"Duplex count mismatch: {len(front)} fronts and {len(back)} backs.")
            if not front:
                raise WorkflowError("Front pages are empty.")
            if skip_first:
                back = back[1:]
            if step.get("reverse_backs", True):
                back.reverse()
            if step.get("rotate_backs", False):
                back = [replace(p, rotation=180) for p in back]
            combined = []
            for i, page in enumerate(front):
                combined.append(page)
                if i < len(back):
                    combined.append(back[i])
            documents = [Document(combined, "duplex")]
        else:
            next_documents: list[Document] = []
            for index, doc in enumerate(documents):
                if cancel is not None and cancel.is_set():
                    raise WorkflowError("Canceled.")
                if "document" in step and step["document"] != index:
                    next_documents.append(doc)
                    continue
                pages = list(doc.pages)
                if op == "split_every":
                    n = step["n"]
                    for offset in range(0, len(pages), n):
                        next_documents.append(Document(pages[offset:offset + n], doc.source_name))
                elif op == "split_ranges":
                    used: set[int] = set()
                    for spec in step["ranges"]:
                        indices = parse_pages(spec, len(pages))
                        if set(indices) & used:
                            raise WorkflowError("Split ranges overlap; a page would be included twice.")
                        used.update(indices)
                        next_documents.append(Document([pages[i] for i in indices], doc.source_name))
                    if step.get("include_remaining", False):
                        rest = [page for i, page in enumerate(pages) if i not in used]
                        if rest:
                            next_documents.append(Document(rest, doc.source_name))
                elif op == "extract":
                    indices = parse_pages(step["pages"], len(pages))
                    next_documents.append(Document([pages[i] for i in indices], doc.source_name))
                elif op == "delete":
                    indices = set(parse_pages(step["pages"], len(pages)))
                    next_documents.append(Document([p for i, p in enumerate(pages) if i not in indices], doc.source_name))
                elif op == "reorder":
                    order = parse_pages(step["order"], len(pages))
                    if len(order) != len(pages):
                        raise WorkflowError("Reorder must contain each page exactly once.")
                    next_documents.append(Document([pages[i] for i in order], doc.source_name))
                elif op == "reverse":
                    next_documents.append(Document(pages[::-1], doc.source_name))
                elif op == "rotate":
                    selected = set(parse_pages(step["pages"], len(pages)))
                    deg = step["degrees"]
                    next_documents.append(Document(
                        [replace(page, rotation=(page.rotation + deg) % 360) if i in selected else page
                         for i, page in enumerate(pages)], doc.source_name))
                elif op == "duplicate":
                    indices = set(parse_pages(step["pages"], len(pages)))
                    times = step.get("times", 1)
                    updated = []
                    for i, page in enumerate(pages):
                        updated.append(page)
                        if i in indices:
                            updated.extend([page] * times)
                    next_documents.append(Document(updated, doc.source_name))
                elif op == "remove_blanks":
                    threshold = float(step.get("threshold", 0.003))
                    updated = []
                    removed = 0
                    for page in pages:
                        k = (page.source, page.index, threshold)
                        if k not in blank_cache:
                            blank_cache[k] = _is_blank(source_paths[page.source], page.index, threshold)
                        if blank_cache[k]:
                            removed += 1
                        else:
                            updated.append(page)
                    next_documents.append(Document(updated, doc.source_name))
                    warnings.append(f"Blank detection removed {removed} page(s) from {doc.source_name}. Review before saving.")
                else:
                    raise WorkflowError(f"Unimplemented operation {op}")
            documents = next_documents
        if len(documents) > MAX_DOCUMENTS:
            raise WorkflowError(f"Workflow produces more than {MAX_DOCUMENTS:,} files.")
        if sum(len(d.pages) for d in documents) > MAX_OUTPUT_PAGES:
            raise WorkflowError(f"Workflow produces more than {MAX_OUTPUT_PAGES:,} pages.")
    if not documents or any(not doc.pages for doc in documents):
        raise WorkflowError("Workflow produces an empty PDF. Adjust your page selection.")
    return Compilation(documents, source_paths, validated, warnings)


def output_names(compilation: Compilation, pattern: str = "{name}_{index:02d}") -> list[str]:
    if not pattern or len(pattern) > 150:
        raise WorkflowError("Output filename pattern must be 1–150 characters.")
    allowed_fields = {"name", "index", "source"}
    try:
        for _, fieldname, spec, conversion in string.Formatter().parse(pattern):
            if fieldname is not None:
                if fieldname not in allowed_fields or conversion is not None or not re.fullmatch(r"0?[1-4]?d?", spec):
                    raise WorkflowError("Filename patterns allow {name}, {source}, {index}, {index:02d}.")
        names = []
        for i, doc in enumerate(compilation.documents, 1):
            raw = pattern.format(name="output", source=doc.source_name, index=i)
            if "/" in raw or "\\" in raw or raw in (".", ".."):
                raise WorkflowError("Filenames cannot include folder separators.")
            safe = re.sub(r'[<>:"|?*\x00-\x1f]', "_", raw).strip(" .")
            if not safe or safe.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *{f"COM{k}" for k in range(1, 10)}, *{f"LPT{k}" for k in range(1, 10)}}:
                raise WorkflowError("Filename pattern creates an invalid Windows filename.")
            if len(safe) > 180:
                raise WorkflowError("Generated filename exceeds 180 characters.")
            names.append(safe + ("" if safe.lower().endswith(".pdf") else ".pdf"))
        if len(set(x.lower() for x in names)) != len(names):
            raise WorkflowError("Filename pattern produces duplicate names. Include {index}.")
        return names
    except (KeyError, IndexError, ValueError) as exc:
        if isinstance(exc, WorkflowError):
            raise
        raise WorkflowError(f"Invalid output filename pattern: {exc}") from exc


def execute_workflow(
    compilation: Compilation,
    output_dir: str | Path,
    *,
    pattern: str = "{source}_{index:02d}",
    allowed_root: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
) -> list[Path]:
    folder = _safe_path(output_dir, allowed_root)
    if not folder.is_dir():
        raise WorkflowError(f"Output folder does not exist: {folder}")
    names = output_names(compilation, pattern)
    destinations = [folder / name for name in names]
    if any(dest.resolve() in compilation.sources.values() for dest in destinations):
        raise WorkflowError("Output filenames would overwrite an input PDF.")
    existing = [dest.name for dest in destinations if dest.exists()]
    if existing:
        raise WorkflowError(f"Output already exists: {', '.join(existing[:3])}. Choose a different pattern or folder.")
    total = compilation.page_count
    completed = 0
    readers = {alias: _reader(path) for alias, path in compilation.sources.items()}
    written: list[Path] = []
    try:
        for doc, dest in zip(compilation.documents, destinations):
            if cancel is not None and cancel.is_set():
                raise WorkflowError("Canceled; no source files were changed.")
            writer = PdfWriter()
            for page in doc.pages:
                if cancel is not None and cancel.is_set():
                    raise WorkflowError("Canceled; no source files were changed.")
                new_page = writer.add_page(readers[page.source].pages[page.index])
                if page.rotation:
                    new_page.rotate(page.rotation)
                completed += 1
                if progress and (completed % 10 == 0 or completed == total):
                    progress(completed, total)
            # Write fully to a same-volume temporary file first. An NTFS hard-link
            # commits it atomically without overwriting anything that appeared since
            # preflight. On filesystems without hard links, copy exclusively instead.
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode="wb", prefix=".pdfstudio_", suffix=".pdf",
                                                 dir=folder, delete=False) as temporary:
                    temp_path = Path(temporary.name)
                    writer.write(temporary)
                try:
                    os.link(temp_path, dest)
                    written.append(dest)
                except FileExistsError as exc:
                    raise WorkflowError(f"{dest.name} was created by another process. Nothing was overwritten.") from exc
                except OSError:
                    # Fallback for restricted / remote filesystems; still no overwrites.
                    try:
                        with dest.open("xb") as out, temp_path.open("rb") as incoming:
                            written.append(dest)
                            shutil.copyfileobj(incoming, out, length=1024 * 1024)
                    except FileExistsError as exc:
                        raise WorkflowError(f"{dest.name} already exists. Nothing was overwritten.") from exc
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
    except Exception as exc:
        # All-or-nothing for outputs created by this call; leave preexisting files alone.
        for path in written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(exc, WorkflowError):
            raise
        raise WorkflowError(f"Could not save PDFs: {exc}") from exc
    return written
