# PDFManipulator

A **Windows desktop app** for merging, splitting, rotating, rearranging, and organizing PDF files. You can use built-in workflows without AI, or optionally connect an eligible ChatGPT account to interpret more complicated instructions.

**Your PDF files stay on your computer.** PDFManipulator is not a website and does not need Vercel or a server.

## Get started (Windows)

**Downloading this GitHub repository? Follow these steps:**

1. Click **Code → Download ZIP** above, then extract the ZIP to a folder.
2. Install **Python 3.11 or later** from [python.org](https://www.python.org/downloads/windows/) if you do not already have it. Enable the Windows Python launcher during installation.
3. Double-click **`Start PDFManipulator.bat`** inside the extracted folder. On the first launch, it installs the required Python packages; internet access is needed for this first-time setup.
4. Once the app opens, click **+ Add PDFs**. Every file appears in **1 YOUR PDF FILES** with its own filename and **View** button; the newest PDF is previewed automatically.
5. The **Build your workflow** panel is already open. Under **Start with**, select **Edit PDFs separately** when you need to change PDF 1 or PDF 2 before combining them.
6. Click **View** beside the PDF you want, then choose an action under **2 EDIT THE PAGES**. Select **Add edit**, review the step, and optionally select **Combine edited PDFs**. The right preview names the document you're viewing (e.g., PDF 2 · filename.pdf).
7. Use **Fit whole page** to view a complete page in the available preview height, or zoom in to see larger pages with fewer thumbnails per row. Click **Save as PDF** to choose the output filename or folder. Original files remain unchanged.

**Already have `PDFManipulator.exe`?** Double-click it instead. The standalone Windows EXE includes Python and does not require installation. The source repository does **not** include the compiled EXE. You can build one using the instructions below; check [GitHub Releases](https://github.com/PraagneySharma/PDFManipulator/releases) for an official download if one is published.

## What can I do?

| Goal | Where to start |
| --- | --- |
| Merge original PDFs immediately | **Start with → Merge original PDFs now** |
| Edit separate PDFs, then combine | **Edit PDFs separately → Add page edits → + Merge edited PDFs** |
| Fix two one-sided scans | Add fronts and backs → **Duplex Scan Merger** |
| Split a PDF into smaller files | **Split Every N Pages** |
| Rotate upside-down pages | **Rotate Scanned Pages** |
| Extract or remove selected pages | Choose **Delete pages** or **Extract pages**, then select the target PDF |
| Insert another PDF at the beginning or middle | Choose **+ Insert PDF at position 1** in the builder; adjust the position or type `end` |
| Start over without losing saved workflows | **+ New workflow** in the top bar |
| Remove blank scans | **Remove Blank Pages** (always review the preview) |
| Process each PDF separately | **Batch PDF Organizer** |

**Example — delete the first page of PDF 2, then merge:** Import PDF 1 and PDF 2. Click **View** on PDF 2. Choose **Delete pages**, select **Add edit**, and enter page **1** for PDF 2. Next choose **Combine edited PDFs**. The result contains all of PDF 1, followed by PDF 2 without its first page. Use **Save as PDF** when the preview is correct.

For more examples, see the [step-by-step user guide](docs/USER_GUIDE.md).

## Do I need ChatGPT or an API key?

**No.** The built-in PDF tools and basic English instruction parser work offline.

For optional instruction-based help, click **AI helper (optional)** in the top bar, then **Continue with ChatGPT**, approve the browser authorization, and select an available model. Eligible accounts can use authorized ChatGPT-plan usage without providing an OpenAI API key. **Limits apply; this is not unlimited API access.** The real-account sign-in flow requires your approval and has not been validated against every ChatGPT account.

Only your **instruction text and generic input labels** are sent to the selected AI; PDF bytes and filenames are **not** sent through the instruction interpreter. You always review the proposed changes before exporting.

Other optional modes include **Ollama (local)**, **OpenAI API**, and **Claude API**. Those cloud API modes require separate keys and billing. Signing in to this app does not automatically connect your other ChatGPT chats or Glossa.

See the [user guide](docs/USER_GUIDE.md#optional-ai-instructions) for details.

## Build your own Windows EXE (optional)

After running the batch launcher once, open PowerShell **in the project folder**:

~~~powershell
.\.venv\Scripts\python.exe -m pip install "pyinstaller>=6.16,<7"
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
~~~

Then open **`dist\PDFManipulator.exe`**. This executable is generated locally and intentionally excluded from Git.

## Project layout

~~~text
PDFManipulator/
├── Start PDFManipulator.bat    # Windows source launcher
├── launch.py                   # Desktop application entry point
├── pdfmanipulator/             # Current app: UI, PDF engine, AI, CLI, MCP
├── packaging/                  # Windows EXE build and icon generator
├── tests/                      # Automated tests and GUI smoke test
├── tools/                      # Public-release security audit
├── docs/                       # User, developer, and legacy instructions
├── legacy/                     # Previous duplex scanner, preserved separately
├── requirements.txt
├── requirements-mcp.txt
└── SECURITY.md
~~~

The folders `.venv/`, `build/`, and `dist/` are generated locally, not committed.

## For developers

- [Developer guide](docs/DEVELOPER_GUIDE.md): setup, tests, CLI, optional MCP, architecture, packaging.
- [Security policy](SECURITY.md): private credential storage and safe disclosure.
- [Previous duplex utility](docs/LEGACY_DUPLEX.md): legacy usage, kept for compatibility.

## License

This repository does not currently include an open-source license. Public visibility does not grant permission to redistribute or modify the code beyond applicable legal exceptions.
