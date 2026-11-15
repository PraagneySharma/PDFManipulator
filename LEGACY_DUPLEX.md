# Legacy duplex scanning utility

This is the original standalone duplex-scanning interface, preserved for compatibility.
The primary application is now **PDFManipulator**; see [README.md](README.md).

## Original AutomaticDuplexScanning tool

A Windows desktop app that combines two single-sided scanned PDFs into a correctly ordered duplex PDF. Everything is processed locally on your computer. PDFsam is not required.

## How to use

1. Scan all **fronts** into a single PDF, in increasing order: **1, 3, 5, 7, ...**. Save as fronts.pdf.
2. Flip the entire stack over and scan the **backs** into one PDF, in descending order: **..., 10, 8, 6, 4, 2**. Save as backs.pdf. Do not manually reorder sheets.
3. Double-click **Start AutomaticDuplexScanning.bat**. The first launch creates a private Python environment and downloads the free pypdf library (internet needed once).
4. Use **Browse...** to select the fronts and backs PDFs.
5. Choose your output PDF name (by default Duplex_Merged.pdf in the same folder as the fronts).
6. Click **Merge and Save PDF**.

### Even total: ten pages

| Input | Scan order |
| --- | --- |
| fronts.pdf | 1, 3, 5, 7, 9 |
| backs.pdf | 10, 8, 6, 4, 2 |
| final PDF | **1, 2, 3, 4, 5, 6, 7, 8, 9, 10** |

### Odd total: nine pages

| Input | Scan order |
| --- | --- |
| fronts.pdf | 1, 3, 5, 7, 9 |
| backs.pdf | 8, 6, 4, 2 |
| final PDF | **1, 2, 3, 4, 5, 6, 7, 8, 9** |

The app accepts equal numbers of fronts and backs (even total) or exactly one extra front (odd total). A one-page document needs only a fronts PDF. Incorrect counts are rejected.

**Important for odd-page originals:** When you flip the whole stack over, the back of the final front page may be blank. If your scanner includes this blank page in the backs PDF, it is usually the **first scanned back**. Check **Skip first back scan if it is blank** to discard it. If your scanner automatically removes blank pages, leave this option off.

**Important:** It trusts the order in which your scanner saved the pages. It does not recognize printed page numbers or detect incorrectly ordered image pages. Review the final file before sharing.

## Optional scanner settings

- **Backs scanned in reverse order:** **On by default**, because you flip the entire stack and the backs arrive as ..., 6, 4, 2. Uncheck only if your scanner instead saves backs as 2, 4, 6, ...
- **Skip first back scan if it is blank:** Select for odd-page originals when the scanner retains the blank back of the last sheet. Never select if the first scan contains real content.
- **Rotate every back page 180°:** Enable if the back pages appear upside down.

For your normal workflow, keep the reverse-order checkbox enabled. Rotation and blank-page skipping are off until needed.

## Command-line use (optional)

Run this in PowerShell from the project folder, after installing requirements:

    .\.venv\Scripts\python.exe app.py --fronts "fronts.pdf" --backs "backs.pdf" --output "combined.pdf"

You can omit --backs for a one-page document. Descending backs are the default. Optional flags: --backs-ascending, --skip-first-back, and --rotate-backs (the older --reverse-backs flag is still accepted).

## Tests

    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

Requirements: Windows 10/11, Python 3 with Tkinter, and the automatically installed pypdf package. Internet is not required after first-time setup.
