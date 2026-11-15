"""Local, offline tool to interleave separately scanned front and back pages."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pypdf import PdfReader, PdfWriter


class DuplexError(ValueError):
    """A validation or processing error suitable for display to the user."""


def read_pdf(path: str | Path, description: str) -> PdfReader:
    pdf_path = Path(path).expanduser()
    if not pdf_path.is_file():
        raise DuplexError(f"{description} PDF does not exist:\n{pdf_path}")

    try:
        reader = PdfReader(str(pdf_path), strict=False)
        if reader.is_encrypted:
            if not reader.decrypt(""):
                raise DuplexError(
                    f"The {description.lower()} PDF is password-protected. "
                    "Please unlock it before merging."
                )
        return reader
    except DuplexError:
        raise
    except Exception as exc:
        raise DuplexError(f"Could not open {description.lower()} PDF:\n{exc}") from exc


def page_counts(fronts: str | Path, backs: str | Path | None = None) -> tuple[int, int]:
    """Read counts and validate: F=B for even totals, F=B+1 for odd totals."""
    front_reader = read_pdf(fronts, "Fronts")
    front_count = len(front_reader.pages)
    if backs:
        back_reader = read_pdf(backs, "Backs")
        back_count = len(back_reader.pages)
    else:
        back_count = 0

    if front_count < 1:
        raise DuplexError("The fronts PDF contains no pages.")
    if back_count not in (front_count, front_count - 1):
        raise DuplexError(
            f"Page counts do not match: {front_count} fronts and {back_count} backs.\n\n"
            "For an even document, both PDFs must have the same number of pages. "
            "For an odd document, fronts must have exactly one extra page. "
            "Check for missing, extra, or blank scans."
        )
    return front_count, back_count


def merge_duplex(
    fronts: str | Path,
    backs: str | Path | None,
    output: str | Path,
    *,
    reverse_backs: bool = True,
    rotate_backs: bool = False,
    skip_first_back: bool = False,
) -> int:
    """Create 1,2,3,4,... from fronts 1,3,5,... and descending backs 10,8,...,2.

    For odd-length stacks, skip_first_back drops the first scanned back if it
    is the blank backside of the last front sheet (with blank-page removal off).
    The two original scans are never modified. Output is written atomically.
    Returns the total merged page count.
    """
    front_path = Path(fronts).expanduser().resolve()
    back_path = Path(backs).expanduser().resolve() if backs else None
    output_path = Path(output).expanduser().resolve()

    if back_path == front_path:
        raise DuplexError("Choose two different files for fronts and backs.")
    if output_path in (front_path, back_path):
        raise DuplexError("Choose a different output filename so originals are not overwritten.")
    if not output_path.parent.is_dir():
        raise DuplexError(f"The output folder does not exist:\n{output_path.parent}")

    # Validate before writing anything.
    front_count, scanned_back_count = page_counts(front_path, back_path)
    front_reader = read_pdf(front_path, "Fronts")
    back_reader = read_pdf(back_path, "Backs") if back_path else None

    if skip_first_back and scanned_back_count != front_count:
        raise DuplexError(
            "To skip the first (blank) back scan, the two PDFs must have "
            "the same page count. Otherwise leave this option unchecked."
        )
    back_count = scanned_back_count - (1 if skip_first_back else 0)

    writer = PdfWriter()
    for i in range(front_count):
        writer.add_page(front_reader.pages[i])
        if i < back_count and back_reader is not None:
            back_index = ((scanned_back_count - 1 - i) if reverse_backs
                          else (i + (1 if skip_first_back else 0)))
            added_page = writer.add_page(back_reader.pages[back_index])
            if rotate_backs:
                added_page.rotate(180)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".pdf", prefix=".duplex_", dir=output_path.parent, delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer.write(temporary_file)
        os.replace(temporary_path, output_path)
    except Exception as exc:
        raise DuplexError(f"Could not save the merged PDF:\n{exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return front_count + back_count


class DuplexApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Automatic Duplex Scanning")
        root.geometry("730x560")
        root.minsize(650, 530)

        self.fronts = tk.StringVar()
        self.backs = tk.StringVar()
        self.output = tk.StringVar()
        self.reverse_backs = tk.BooleanVar(value=True)
        self.rotate_backs = tk.BooleanVar(value=False)
        self.skip_first_back = tk.BooleanVar(value=False)
        self.summary = tk.StringVar(value="Select your fronts PDF to begin.")
        self.front_count_label = tk.StringVar(value="Not selected")
        self.back_count_label = tk.StringVar(value="Not selected")

        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=6)
        style.configure("Merge.TButton", font=("Segoe UI", 11, "bold"), padding=10)

        outer = ttk.Frame(root, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Automatic Duplex Scanning", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Combine two single-sided scans into one correctly ordered PDF. Everything stays on your PC.",
            style="Sub.TLabel",
            wraplength=660,
        ).pack(anchor="w", pady=(4, 19))

        self.add_file_row(
            outer, "1   FRONTS  (pages 1, 3, 5, 7, ...)",
            self.fronts, self.front_count_label, self.browse_fronts
        )
        self.add_file_row(
            outer, "2   BACKS  (pages ..., 8, 6, 4, 2)",
            self.backs, self.back_count_label, self.browse_backs
        )
        self.add_file_row(
            outer, "3   SAVE MERGED PDF AS", self.output, None, self.browse_output
        )

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=(13, 8))
        ttk.Checkbutton(
            options,
            text="Backs scanned in reverse order (default when flipping the stack)",
            variable=self.reverse_backs,
        ).pack(anchor="w")
        ttk.Checkbutton(
            options,
            text="Skip first back scan if it is blank (odd-page original)",
            variable=self.skip_first_back,
        ).pack(anchor="w", pady=(3, 0))
        ttk.Checkbutton(
            options,
            text="Rotate every back page 180°",
            variable=self.rotate_backs,
        ).pack(anchor="w", pady=(3, 0))

        ttk.Separator(outer).pack(fill="x", pady=(14, 12))
        ttk.Label(outer, textvariable=self.summary, style="Status.TLabel", wraplength=650).pack(
            anchor="w", pady=(0, 14)
        )
        ttk.Button(
            outer, text="Merge and Save PDF", style="Merge.TButton", command=self.merge
        ).pack(anchor="w")

        for variable in (self.fronts, self.backs, self.skip_first_back):
            variable.trace_add("write", self.update_summary)

    def add_file_row(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        count_var: tk.StringVar | None,
        handler: object,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 12))
        heading = ttk.Frame(row)
        heading.pack(fill="x", pady=(0, 4))
        ttk.Label(heading, text=label, font=("Segoe UI", 9, "bold")).pack(side="left")
        if count_var is not None:
            ttk.Label(heading, textvariable=count_var).pack(side="right")
        content = ttk.Frame(row)
        content.pack(fill="x")
        ttk.Entry(content, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(content, text="Browse...", command=handler).pack(side="left", padx=(8, 0))

    @staticmethod
    def pick_pdf() -> str:
        return filedialog.askopenfilename(
            title="Select scanned PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )

    def browse_fronts(self) -> None:
        picked = self.pick_pdf()
        if picked:
            self.fronts.set(picked)
            if not self.output.get().strip():
                self.output.set(str(Path(picked).parent / "Duplex_Merged.pdf"))

    def browse_backs(self) -> None:
        picked = self.pick_pdf()
        if picked:
            self.backs.set(picked)

    def browse_output(self) -> None:
        picked = filedialog.asksaveasfilename(
            title="Save merged PDF",
            defaultextension=".pdf",
            initialfile=Path(self.output.get()).name if self.output.get() else "Duplex_Merged.pdf",
            filetypes=[("PDF files", "*.pdf")],
        )
        if picked:
            self.output.set(picked)

    def update_summary(self, *_args: object) -> None:
        front_path = self.fronts.get().strip()
        back_path = self.backs.get().strip()
        for path, label in (
            (front_path, self.front_count_label),
            (back_path, self.back_count_label),
        ):
            if not path:
                label.set("Not selected")
            else:
                try:
                    label.set(f"{len(read_pdf(path, 'Selected').pages)} pages")
                except Exception:
                    label.set("Could not read")
        if not front_path:
            self.summary.set("Select your fronts PDF to begin.")
            return
        if not back_path:
            try:
                if len(read_pdf(front_path, "Fronts").pages) == 1:
                    self.summary.set("Ready: one front page. No backs PDF needed.")
                else:
                    self.summary.set("Select your backs PDF next.")
            except DuplexError as exc:
                self.summary.set(str(exc).split("\n")[0])
            return
        try:
            front_count, scanned_backs = page_counts(front_path, back_path)
            if self.skip_first_back.get() and scanned_backs != front_count:
                raise DuplexError("Only skip the first back when both scans have equal page counts.")
            real_backs = scanned_backs - (1 if self.skip_first_back.get() else 0)
            self.summary.set(
                f"Ready: {front_count} fronts + {real_backs} backs = "
                f"{front_count + real_backs} pages in final PDF."
            )
        except DuplexError as exc:
            self.summary.set(str(exc).split("\n")[0])

    def merge(self) -> None:
        if not self.fronts.get().strip() or not self.output.get().strip():
            messagebox.showerror("Missing files", "Choose a fronts PDF and an output filename.")
            return
        output_path = Path(self.output.get().strip())
        if output_path.is_file() and not messagebox.askyesno(
            "Replace existing PDF",
            f"This PDF already exists:\n\n{output_path}\n\nReplace it with the merged PDF?",
        ):
            return
        try:
            pages = merge_duplex(
                self.fronts.get().strip(),
                self.backs.get().strip() or None,
                self.output.get().strip(),
                reverse_backs=self.reverse_backs.get(),
                rotate_backs=self.rotate_backs.get(),
                skip_first_back=self.skip_first_back.get(),
            )
        except DuplexError as exc:
            messagebox.showerror("Cannot merge", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Unexpected error", f"Merge failed:\n{exc}")
            return
        self.summary.set(f"Done: saved {pages} pages to {Path(self.output.get()).name}.")
        messagebox.showinfo(
            "PDF saved",
            f"Successfully created a {pages}-page PDF:\n\n{self.output.get()}",
        )


def main() -> None:
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(
            description="Merge fronts (1,3,5,...) with backs (2,4,6,...) into one PDF."
        )
        parser.add_argument("--fronts", required=True, help="Fronts PDF, increasing order")
        parser.add_argument("--backs", help="Backs PDF, increasing order")
        parser.add_argument("--output", required=True, help="Output PDF path")
        order = parser.add_mutually_exclusive_group()
        order.add_argument("--backs-ascending", action="store_true", help="Backs scanned 2,4,6,... instead of the default reverse order")
        order.add_argument("--reverse-backs", action="store_true", help="Legacy flag; reverse order is now the default")
        parser.add_argument("--rotate-backs", action="store_true")
        parser.add_argument("--skip-first-back", action="store_true", help="Ignore first scanned back if it is blank")
        args = parser.parse_args()
        try:
            count = merge_duplex(
                args.fronts,
                args.backs,
                args.output,
                reverse_backs=not args.backs_ascending,
                rotate_backs=args.rotate_backs,
                skip_first_back=args.skip_first_back,
            )
            print(f"Saved {count} pages to {args.output}")
        except DuplexError as exc:
            parser.exit(1, f"Error: {exc}\n")
    else:
        root = tk.Tk()
        DuplexApp(root)
        root.mainloop()


if __name__ == "__main__":
    main()
