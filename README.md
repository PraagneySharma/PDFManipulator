# PDFManipulator

**PDFManipulator** is a local-first Windows desktop application for merging, splitting, arranging, rotating, and processing PDFs. It provides a visual page preview, reusable workflows, an offline instruction parser, and optional **Sign in with ChatGPT** for eligible accounts.

Your PDF documents are processed **on your own computer**. No web server, Vercel deployment, or cloud PDF storage is required.

## Quick start (Windows)

- **Standalone application:** Double-click `dist\PDFManipulator.exe` after building from source or downloading a release artifact.
- **Source launcher:** Double-click **Start PDFManipulator.bat**. If the EXE is present, it opens the app; otherwise it creates a Python environment and installs the listed dependencies.
- Add one or more PDF files, choose a built-in preset or describe a workflow, inspect the preview, then select **Export PDF** to save new files. Original documents are not overwritten.

**Source-only repositories intentionally do not include the ~100 MB compiled EXE or a Python virtual environment.** Download the release build if available, or build it locally as described below.

## Features

| Feature | Details |
| --- | --- |
| PDF operations | Merge, duplex interleave, split, extract, delete, reorder, reverse, rotate, duplicate, remove blanks |
| Preview | Local page thumbnails, zoom, drag-to-reorder, before/after comparison |
| Workflows | Presets, editable steps, filename patterns, JSON import/export, undo/redo |
| Local automation | Offline English instruction parser; no login or network needed |
| ChatGPT plan | Optional browser sign-in and model selection on eligible accounts; no separate API key required for authorized plan usage |
| Other AI | Optional Ollama locally, or separate OpenAI/Claude API keys |
| Interoperability | Local, folder-restricted MCP server and CLI, independently enabled |

## ChatGPT integration

Select **Continue with ChatGPT**, approve the browser authorization, and choose an available model. Only your instruction and generic input labels (`input1`, `input2`, etc.) are sent to the model; **PDF file contents and filenames are not uploaded** by the instruction interpreter. The returned steps are schema-checked locally and must be previewed before saving.

Sign in with ChatGPT uses an eligible account's authorized plan usage, subject to OpenAI's limits and permissions; it does **not** use an API key and does **not** imply unlimited AI calls. Real-account authorization must be approved interactively; automated tests use mocked identity and API responses.

The standalone optional MCP server is a separate integration. Signing into PDFManipulator does not automatically grant it access to other ChatGPT conversations, Glossa, or personal ChatGPT data.

## Build the Windows application

Requirements: Windows 10/11, Python 3.11+ with Tkinter. From the repository root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install "pyinstaller>=6.16,<7"
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

The output is `dist\PDFManipulator.exe`. This packaged EXE contains the Python runtime and runs without a separate Python installation or console. To run from source:

```powershell
.\.venv\Scripts\python.exe launch.py
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tests.smoke_ui
```

The smoke test requires an interactive Windows desktop. Test inputs are generated synthetically. A real ChatGPT OAuth approval is intentionally not automated.

## Privacy and security

- The public repository contains only source, assets, documentation, and synthetic tests. No PDF documents, cloud credentials, local session files, virtual environments, or build outputs belong in Git.
- ChatGPT OAuth sessions are encrypted using Windows DPAPI and saved in your user profile, not the project folder or this repository.
- All PDF processing and saving happens locally. Existing output files are never overwritten.
- AI instructions are validated and cannot execute arbitrary Python code or filesystem commands.
- External providers send only approved instruction text and generic input aliases; they never receive document bytes through the instruction parser.
- Keep your OAuth sessions, API keys, personal documents, and local configuration out of source control. Report vulnerabilities through GitHub's private security reporting feature, not public issues.

For implementation details, API configuration, supported operations, privacy limitations, and MCP setup, see **[PDFMANIPULATOR_GUIDE.md](PDFMANIPULATOR_GUIDE.md)** and [SECURITY.md](SECURITY.md).

## Compatibility

The original automatic duplex scanning utility remains available via `app.py` and **Start AutomaticDuplexScanning.bat**. See [LEGACY_DUPLEX.md](LEGACY_DUPLEX.md) for its original usage instructions. The previous **Start PDF Workflow Studio.bat** is retained as a forwarding launcher for existing shortcuts.

## License

No open-source license has been selected. The repository is public for viewing and collaboration; reuse rights remain reserved unless a license is added.
