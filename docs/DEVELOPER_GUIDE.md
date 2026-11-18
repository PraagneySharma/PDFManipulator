# PDFManipulator — developer guide

[Back to README](../README.md) · [User guide](USER_GUIDE.md) · [Security policy](../SECURITY.md)

This repository contains a Windows desktop app, a reusable PDF processing engine, a CLI, and an optional local MCP server. **It does not deploy a web application.**

## Development setup (Windows)

Requirements: Windows 10/11, Python **3.11+** with Tkinter and PowerShell. Run these commands from the repository root:

~~~powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launch.py
~~~

Or double-click `Start PDFManipulator.bat` to automate the first two commands. The launcher prefers the compiled EXE if present.

## Test the application

~~~powershell
.\.venv\Scripts\python.exe -m compileall -q pdfmanipulator launch.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tests.smoke_ui
~~~

The GUI smoke test exercises a two-column manual-first layout, filename-based source selection, full-page previews at Windows 200% DPI, PDF-specific deletion, post-edit merging, responsive zoom, Save As, and the optional AI panel. The last test needs a graphical Windows desktop. PDF test documents are generated during tests and never committed. The ChatGPT auth and inference tests simulate authorization; live account sign-in requires a human to approve the browser flow.

## Build a portable Windows EXE

~~~powershell
.\.venv\Scripts\python.exe -m pip install "pyinstaller>=6.16,<7"
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
~~~

Output: `dist\PDFManipulator.exe`. The build script generates the icon itself. The executable and the generated icon are ignored by Git, so the repository only tracks reproducible source and build tooling.

To run a built-EXE PDF smoke test:

~~~powershell
& ".\dist\PDFManipulator.exe" --smoke-test
~~~

This should launch, load synthetic PDFs, render thumbnails, export a verified PDF, and exit.

## Architecture

| Location | Responsibility |
| --- | --- |
| `launch.py` | Main GUI entry point and packaged smoke test |
| `pdfmanipulator/ui.py` | Windows interface, drag/drop, controls, previews and workflow editing |
| `pdfmanipulator/engine.py` | Compile, validate and execute PDF transformations |
| `pdfmanipulator/parser.py` | Conservative offline instruction parser |
| `pdfmanipulator/ai.py` | Optional Ollama and separately billed API providers |
| `pdfmanipulator/chatgpt.py` | ChatGPT-plan OAuth connection, protected local sessions, model discovery and AI inference |
| `pdfmanipulator/recipes.py` | Presets and saved workflow JSON |
| `pdfmanipulator/layout.py` | Readable thumbnail columns, full-image aspect-ratio fitting, and filename-based preview tabs |
| `pdfmanipulator/exports.py` | Safe, collision-free batch export naming |
| `pdfmanipulator/previews.py` | Local thumbnail generation |
| `pdfmanipulator/cli.py` | Command-line workflows |
| `pdfmanipulator/mcp_server.py` | Optional, folder-restricted stdio MCP integration |
| `packaging/` | Windows build script and generated-icon source |
| `legacy/` | Previous duplex utility, kept separate from the main application |
| `tools/` | Staged Git content / privacy audit |
| `tests/` | Unit tests, integrations, and desktop smoke test |

## Recipe examples

A recipe is validated JSON with `name`, `pattern`, and `steps`. The first step must load at least one input. Inputs are referred to by logical aliases rather than arbitrary filesystem paths.

~~~json
{
  "name": "Combine and split",
  "pattern": "result_{index:02d}",
  "steps": [
    {"op": "merge", "sources": ["input1", "input2"]},
    {"op": "split_every", "n": 5}
  ]
}
~~~

Other supported operations include `load`, `load_each`, `duplex`, `interleave`, `merge_documents`, `insert_pdf`, `split_ranges`, `extract`, `delete`, `reorder`, `reverse`, `rotate`, `duplicate` and `remove_blanks`. Manual workflows should use **`load_each`** to keep imported PDFs separate, apply edits with a **zero-based** `document` selector (so `document: 1` targets PDF 2), then use **`merge_documents`** to combine the edited output documents. Merge order is **one-based** and includes each current document exactly once. For example:

~~~json
[
  {"op": "load_each", "sources": ["input1", "input2"]},
  {"op": "delete", "pages": "1", "document": 1},
  {"op": "merge_documents", "order": [1, 2]}
]
~~~

`insert_pdf` is still supported as a post-load operation for inserting an untouched source PDF at a 1-based page position or `end`. The UI opens with the manual workflow builder visible and hides the optional AI composer until requested.

See `pdfmanipulator/engine.py` for exact validation rules.

## CLI

Use `--help` for the authoritative argument list:

~~~powershell
.\.venv\Scripts\python.exe -m pdfmanipulator.cli --help
~~~

Example, after creating a JSON recipe file such as the one above:

~~~powershell
.\.venv\Scripts\python.exe -m pdfmanipulator.cli --recipe "plan.json" --input "input1=C:\scans\a.pdf" --input "input2=C:\scans\b.pdf" --output-dir "C:\scans\finished" --preview
~~~

Remove `--preview` when ready to write output. The engine never intentionally overwrites existing target files.

## Optional local MCP server

This is **separate** from signing into ChatGPT inside the desktop app:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
.\.venv\Scripts\python.exe -m pdfmanipulator.mcp_server --root "C:\scans\approved"
~~~

The MCP server uses stdio, not a public HTTP listener. The client must explicitly start it and supply an authorized root folder. Available tools are `list_pdf_presets`, `preview_pdf_workflow`, and `execute_pdf_workflow`. Input files and output folders must remain under the authorized root. Never expose the server to unauthenticated public requests.

## ChatGPT and privacy notes

The desktop OAuth flow requires the user's browser consent, validates provider identity signatures and token claims, and encrypts saved sessions using Windows DPAPI. A user must select an available model and approve sharing *instruction text* before a cloud interpretation request. PDF bytes do not leave the local computer through this feature.

The project does not automatically inherit a ChatGPT conversation, Glossa, or other connected applications. Responses are treated as untrusted workflow plans and validated before saving.

## Before publishing code

1. Make sure the Git status is clean or intentionally staged, and check `git diff --cached`.
2. Run the complete test suite and the GUI smoke test.
3. Run the tracked-file audit **after** `git add`:

   ~~~powershell
   .\.venv\Scripts\python.exe tools\audit_public_release.py
   ~~~

4. Run an independent scanner such as Gitleaks against Git history.
5. Confirm that no PDFs, credentials, local settings, compiled EXEs, virtual environments, or unintended personal paths are tracked. Credential revocation is required if secrets have ever entered Git history.

There is no committed GitHub Actions workflow because the initial GitHub authorization lacked the `workflow` permission. Tests run locally; a CI workflow can be added when permissions allow.
