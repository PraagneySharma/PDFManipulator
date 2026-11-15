# Legacy duplex scanner

[Back to PDFManipulator](../README.md)

The original Automatic Duplex Scanning program is preserved under `legacy/` for compatibility. **For new work, use the main PDFManipulator app** and its **Duplex Scan Merger** preset.

## Run the old interface

From the repository root, double-click:

`legacy\Start Legacy Duplex Scanner.bat`

The launcher uses the repository's local Python environment, creating one and installing the basic PDF dependency if needed.

Alternatively, run from PowerShell:

~~~powershell
.\.venv\Scripts\python.exe legacy\duplex_app.py
~~~

## Prepare the scans

1. Scan all **fronts** into one PDF in increasing order: 1, 3, 5, 7, …
2. Flip the entire stack and scan all **backs** into a second PDF. Normally these are saved in reverse order: …, 8, 6, 4, 2.
3. Select the fronts and backs PDFs in the legacy window.
4. Confirm whether the backs need reversal or 180° rotation.
5. For odd page counts, the first scanned back may be blank. Enable **Skip first back scan** only when appropriate.
6. Choose the output path and select **Merge and Save PDF**. Inspect the result.

For a one-page PDF, only the fronts file is needed.

## Optional command line

~~~powershell
.\.venv\Scripts\python.exe legacy\duplex_app.py --fronts "fronts.pdf" --backs "backs.pdf" --output "combined.pdf"
~~~

By default, the backs are treated as descending order. Other supported flags include `--backs-ascending`, `--skip-first-back`, and `--rotate-backs`.

This legacy utility is **not required** for the main PDFManipulator application, which uses its own newer engine.
