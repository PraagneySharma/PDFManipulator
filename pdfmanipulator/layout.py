"""Responsive PDF preview helpers: readable pages, full-page aspect ratios."""
from __future__ import annotations

from math import floor


def thumbnail_layout(available_width: int, zoom: float) -> tuple[int, int, int]:
    """Return (columns, max_page_width, reference_page_height).

    Prioritize legibility over squeezing six miniature pages onto a row.
    All pages remain entirely visible; at higher zoom fewer fit per row.
    The height is a reference only: individual pages use their own aspect ratio.
    """
    if available_width < 1 or zoom <= 0:
        raise ValueError("Width and zoom must be positive.")
    inner_width = max(1, available_width - 24)
    # About 2 columns on a 600px preview; 3 on a 900px preview.
    preferred_width = max(184.0, min(270.0, available_width * 0.42)) * zoom
    gap = 18
    columns = max(1, min(6, floor((inner_width + gap) / (preferred_width + gap))))
    # At large zoom show one wide page rather than letting its right edge
    # extend beyond the preview viewport.
    cell_width = (inner_width - (columns - 1) * gap) / columns
    page_width = max(1, int(cell_width - 16))
    return columns, page_width, int(round(page_width * 1.414))


def fit_image_size(width: int, height: int, max_width: int,
                   max_height: int | None = None) -> tuple[int, int]:
    """Size the ENTIRE image into a rectangle without cropping or distortion."""
    if min(width, height, max_width) <= 0 or (max_height is not None and max_height <= 0):
        raise ValueError("Page and display dimensions must be positive.")
    ratio = max_width / width
    if max_height is not None:
        ratio = min(ratio, max_height / height)
    return max(1, round(width * ratio)), max(1, round(height * ratio))


def output_tab_title(index: int, document, sources: dict,
                     total_outputs: int) -> str:
    """Give preview tabs recognizable file names, never 'Output 2'."""
    aliases = {page.source for page in document.pages}
    if len(aliases) > 1:
        return f"Combined PDF ({len(document.pages)} pages)"
    if len(aliases) == 1:
        alias = next(iter(aliases))
        path = sources.get(alias)
        if path is not None:
            source_number = list(sources).index(alias) + 1
            prefix = (f"Part {index + 1} · " if total_outputs > len(sources) else "")
            filename = path.name
            if len(filename) > 36:
                filename = filename[:33] + "…"
            return f"{prefix}PDF {source_number} · {filename} ({len(document.pages)} pages)"
    return f"Edited PDF {index + 1} ({len(document.pages)} pages)"
