"""Launch the local PDFManipulator window.

PyInstaller bundles this entry point as a standalone Windows desktop
application. No web server, online account, or Python installation required.
"""
from __future__ import annotations

import sys


def _smoke_test() -> None:
    """Check bundled UI, thumbnails, PDF transforms and non-overwriting output."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from pypdf import PdfReader, PdfWriter
    from studio.recipes import preset
    from studio.ui import StudioApp
    from studio.engine import execute_workflow

    with TemporaryDirectory() as dirname:
        folder = Path(dirname)
        fronts, backs = folder / "fronts.pdf", folder / "backs.pdf"
        for path, widths in ((fronts, [601, 603]), (backs, [604, 602])):
            writer = PdfWriter()
            for width in widths:
                writer.add_blank_page(width=width, height=800)
            with path.open("wb") as dest:
                writer.write(dest)

        root = StudioApp()
        try:
            root.add_files([fronts, backs])
            root.load_recipe(preset("Duplex Scan Merger"))
            root.update()
            if root.compiled is None or root.compiled.page_count != 4:
                raise RuntimeError("PDF compilation failed")
            if len(root.image_refs) < 4:
                raise RuntimeError("Bundled PDF thumbnail rendering failed")
            result = execute_workflow(
                root.compiled, folder, pattern="smoke_{index:02d}"
            )
            if len(result) != 1 or len(PdfReader(result[0]).pages) != 4:
                raise RuntimeError("PDF export verification failed")
            root.after(150, root.destroy)
            root.mainloop()
        finally:
            try:
                root.destroy()
            except Exception:
                pass  # Tk may already be fully destroyed by the smoke-test timer.


def run() -> None:
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--smoke-test":
            _smoke_test()
        else:
            from studio.ui import main
            main()
    except Exception as exc:
        if len(sys.argv) > 1 and sys.argv[1] == "--smoke-test":
            import traceback
            traceback.print_exc()
            raise SystemExit(1) from exc
        # A --windowed executable has no console for Python tracebacks.
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "PDFManipulator",
                f"The application couldn't start:\n\n{exc}\n\n"
                "Try the original batch launcher if this issue persists.",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
        raise SystemExit(1) from exc


if __name__ == "__main__":
    run()
