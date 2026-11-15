"""Lazy, local thumbnail renderer. A PDF is never uploaded to create a preview."""
from __future__ import annotations
from pathlib import Path
from functools import lru_cache

from .engine import PageRef, WorkflowError

@lru_cache(maxsize=160)
def render_png(path: str, page_index: int, rotation: int = 0, width: int = 155) -> bytes:
    try:
        import pymupdf as fitz
        with fitz.open(path) as pdf:
            page = pdf.load_page(page_index)
            factor = min(2.0, width / max(page.rect.width, 1))
            pix = page.get_pixmap(matrix=fitz.Matrix(factor, factor), alpha=False)
            # Rotate preview to match the engine's output metadata.
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            if rotation:
                img = img.rotate(-rotation, expand=True)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()
    except Exception as exc:
        raise WorkflowError(f"Preview unavailable for {Path(path).name} page {page_index + 1}: {exc}") from exc

def image_for(ref: PageRef, sources: dict[str, Path], width: int = 155):
    import io
    from PIL import Image
    return Image.open(io.BytesIO(render_png(str(sources[ref.source]), ref.index, ref.rotation, width))).copy()
