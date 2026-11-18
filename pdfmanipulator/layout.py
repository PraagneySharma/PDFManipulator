"""Pure thumbnail-grid sizing logic; zoom changes both image dimensions and columns."""
from __future__ import annotations

from math import floor


def thumbnail_layout(available_width: int, zoom: float) -> tuple[int, int, int]:
    """Return (columns, image_width, image_height).

    At 100% zoom, exactly six thumbnails fit the available width. Zooming in
    increases the width and height proportionally and reduces visible columns.
    """
    if available_width < 1 or zoom <= 0:
        raise ValueError("Width and zoom must be positive.")
    # 6 columns at 100% even when the editor drawer is visible.
    baseline = available_width / 6.0
    cols = max(1, min(9, floor(available_width / (baseline * zoom) + 1e-7)))
    slot = baseline * zoom
    thumb_w = max(42, min(640, int(slot - 24)))
    thumb_h = max(58, min(850, int(round(thumb_w * 1.4))))
    return cols, thumb_w, thumb_h
