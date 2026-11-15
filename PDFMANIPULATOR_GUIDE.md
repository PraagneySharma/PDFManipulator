# PDFManipulator

A local-first Windows PDF automation studio. Built on AutomaticDuplexScanning;
the original working GUI and duplex CLI remain in app.py and
Start AutomaticDuplexScanning.bat.

Saved workflows and ChatGPT sessions from the previous PDF Workflow Studio
installation are copied into PDFManipulator's user-profile storage on first
launch. These private files are **never** placed in the public repository.

## Standalone Windows application

The portable executable is built at `dist/PDFManipulator.exe`.
Double-click it to open PDFManipulator as a normal local Windows app.
Python, a terminal window, Vercel, and an internet connection are not required
for the standard PDF operations. The executable includes its Python runtime.
The single-file version can be copied to another compatible Windows computer.
On first launch it may take a few seconds to unpack itself.

The `Start PDFManipulator.bat` launcher now automatically uses the
built EXE when available; otherwise it falls back to the source version.

To rebuild the app in the project folder:

    .\.venv\Scripts\python.exe -m pip install "pyinstaller>=6.16,<7"
    powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_windows.ps1

No key is required for offline PDF operations. Eligible Plus/Pro users can
optionally connect their ChatGPT plan using **Continue with ChatGPT**, with
browser consent and model selection. Separate OpenAI/Claude API key modes
are still available, but no API key is needed for the ChatGPT-plan connection.
Local Ollama requires a downloaded local model but no cloud key.

## Quick start

1. Double-click `dist/PDFManipulator.exe` (or the original
   `Start PDFManipulator.bat` launcher). The EXE includes Python;
   no installation, server or terminal is needed. Python 3.11+ is required
   only if running or rebuilding the source version.
2. Add PDFs using the button or drag-and-drop.
3. Optionally click **Continue with ChatGPT**, approve access in your browser,
   and choose an available model. Otherwise keep **Offline** in AI settings.
   Enter an instruction or select a preset.
4. The default workspace puts the output preview front and center. Choose
   **Edit workflow** in the top bar to open the right-side steps, inputs, output
   filenames, and undo/redo tools. Close it again to enlarge the preview.
   **Compare originals** reveals the optional BEFORE preview strip. Click a page
   to select it and rotate/delete, or drag it to reorder. Use zoom +/- to
   inspect pages. **AI settings** is collapsed until needed.
5. Choose **Export PDF** at the top, select a destination, and confirm.
   Existing files and all sources are NEVER overwritten.

The interface uses Windows Segoe UI typography, a compact preset library,
large PDF thumbnails, and light/dark/system themes. Saved workflows are
collapsed under **Saved workflows > Show**. Shortcuts: Ctrl+O (add PDFs),
Ctrl+S (save workflow), Ctrl+Z / Ctrl+Y (undo / redo).

## Offline presets

Duplex Scan Merger, Split Every N Pages, Custom Page Splitter, PDF Merger,
Extract Selected Pages, Reverse Page Order, Rotate Scanned Pages,
Remove Blank Pages, Batch PDF Organizer.

No AI key is needed. Offline natural-language interpretation recognizes common
patterns, such as "Split every three pages", "Rotate even pages 180 degrees",
"Combine these PDFs", "Delete pages 2 and 7", "Extract pages 1-5", or
"Turn the front and back scans into a duplex PDF". Unsupported instructions
are rejected rather than guessed. Use editable presets for more complex plans.

## Workflow format

Recipes have name, pattern, and steps fields. Steps are objects with op and
explicit parameters (they are never Python code). The first step loads one
or more source aliases; later steps transform the compiled page list.

Example Office Duplex Scanner JSON:

    {
      "name": "Office Duplex Scanner",
      "pattern": "office_{index:02d}",
      "steps": [
        {
          "op": "duplex", "fronts": "input1", "backs": "input2",
          "reverse_backs": true, "rotate_backs": true
        }
      ]
    }

Example composable JSON:

    {
      "name": "Stack fix",
      "pattern": "fixed_{index:02d}",
      "steps": [
        {"op":"load","source":"input1"},
        {"op":"reverse"},
        {"op":"rotate","pages":"even","degrees":180},
        {"op":"split_every","n":5}
      ]
    }

Allowed operations: load, load_each, merge, duplex, interleave, split_every,
split_ranges, extract, delete, reorder, reverse, rotate, duplicate,
remove_blanks. Page ranges use human-readable 1-based values such as
"1,3,5-8", "even", "odd", or "all". Split ranges use a list, e.g.
["1-5","6-12"] and optional include_remaining:true.

To edit, duplicate, delete or export a recipe, select it from My Workflows,
then use sidebar controls. To import, select Import recipe JSON. Saved
recipes live in %APPDATA%\PDFManipulator\recipes.json and contain no PDFs.
Filename tokens: {name}, {source}, {index}, {index:02d}. Output collisions
and Windows-invalid paths are rejected.

## Sign in with ChatGPT (no API key)

The Windows app implements the documented direct Sign in with ChatGPT flow
for an open-source/local client. Eligible **ChatGPT Plus or Pro** users can
approve using their ChatGPT plan for AI requests without providing an API key.
Eligibility, model availability and usage limits are determined by OpenAI and
the account/workspace selected during authorization. No ChatGPT account
credentials are included with this application.

1. Open PDFManipulator and click **Continue with ChatGPT**.
2. Your system browser opens OpenAI sign-in. Sign in, select the ChatGPT
   workspace, and explicitly approve the requested ChatGPT-plan permission.
3. Return to the desktop app. Once the connection grants plan use, the app
   lists the models available to this account. The interpreter automatically
   switches to **ChatGPT plan**.
4. Add your PDFs, type a task, and click **Build workflow**. ChatGPT receives
   only the instruction and generic aliases (input1, input2, etc.) and
   returns structured JSON steps. The local engine validates these steps.
5. Review the proposed steps and preview; click **Export PDF** to approve
   writing local output PDFs. No AI result may run arbitrary commands.

Open **AI settings** to choose a model, switch to Offline or another provider,
or uncheck sharing of prompt text. Click **ChatGPT account** to reconnect,
add or switch accounts, sign out, or open **Manage usage** in ChatGPT settings.

**Privacy and authorization:** PDF contents and filenames are NOT uploaded
in this ChatGPT-plan workflow. OpenAI only sees your instruction and generic
input aliases. OpenAI's approval does not grant access to your ChatGPT chats,
memory, connected plugins, or Glossa workspaces. Authentication uses browser
OAuth with state, nonce, PKCE, a temporary loopback callback on 127.0.0.1,
OpenAI ID-token signature validation, issuer/audience checks, and user-granted
scopes. No browser cookie scraping or private ChatGPT endpoint is used.

Windows DPAPI protects refresh/access/identity tokens at rest under
`%LOCALAPPDATA%\PDFManipulator\chatgpt\accounts.dpapi`.
The persistent anonymous host ID is stored alongside them in `host.json`;
credentials are never written to source control, recipe JSON, or logs.
Account sign-out attempts to revoke the renewable session. If the network
prevents confirmed revocation, the local token is still cleared and the app
instructs you to disconnect it in ChatGPT Settings.

The direct Responses API connection always uses `store: false` and
`stream: true` as required by the plan-sharing route. Responses are accepted
only after the completion event and strict local workflow validation. AI
cannot execute the PDF workflow by itself or overwrite original files.
ChatGPT plan usage may be limited by app-specific or plan-wide limits; use
the in-app **Manage usage** link to review these. OpenAI may deny access
depending on account/workspace eligibility or policy.

The sign-in implementation and API streaming are covered by mocked protocol
tests; **live OAuth sign-in requires the actual user to approve the browser
authorization and cannot be completed automatically in development tests**.

Official documentation:
https://developers.openai.com/siwc/token-sharing-open-source
https://developers.openai.com/siwc/token-sharing-open-source/sign-in
https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference

## Other AI choices

The interpreter modes are **ChatGPT plan**, **Offline**, **Ollama (local)**,
**OpenAI API**, and **Claude API**. The separate API-key modes use
`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` from your environment and their own
billing; neither automatically uses a ChatGPT/Claude consumer subscription.
Ollama connects to 127.0.0.1:11434 and defaults to `llama3.2`. Offline uses
constrained English patterns with no network usage.

For cloud providers, the app requires permission to send the instruction.
All model-generated steps are validated and previewed locally before export.
If you need ChatGPT itself to operate PDFManipulator from an existing conversation,
use a **separate** supported Glossa or MCP integration described below;
signing into PDFManipulator does not automatically connect your other apps.

## Optional local MCP server

Install optional SDK from requirements-mcp.txt. Example PowerShell commands:

    .\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
    .\.venv\Scripts\python.exe -m studio.mcp_server --root "C:\Documents\ApprovedPDFs"

MCP tools: list_pdf_presets, preview_pdf_workflow, execute_pdf_workflow.
The service uses stdio only. It requires an explicitly authorized root folder;
inputs and output_subdir are relative to it. Absolute, traversal, or symlink
escapes are disallowed. Output folders must already exist. It exposes no
general filesystem, shell, or Python execution tools.

Claude Code can launch this stdio server as a local MCP tool if configured.
ChatGPT custom MCP access requires supported account permissions and either
a public secured endpoint or an official Secure MCP Tunnel; this project
does not create such a remote endpoint or implement its authentication.
Never expose the local service over a public connection without adding
strong authentication, authorization, and additional security review.

MCP Python SDK: https://py.sdk.modelcontextprotocol.io/

## CLI and tests

    .\.venv\Scripts\python.exe -m studio.cli --recipe office.json --input "input1=C:\scans\fronts.pdf" --input "input2=C:\scans\backs.pdf" --output-dir "C:\scans\finished" --preview
    .\.venv\Scripts\python.exe -m studio.cli --recipe office.json --input "input1=C:\scans\fronts.pdf" --input "input2=C:\scans\backs.pdf" --output-dir "C:\scans\finished"
    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

Original duplex application CLI still works:

    .\.venv\Scripts\python.exe app.py --fronts fronts.pdf --backs backs.pdf --output merged.pdf

## Architecture

- studio/engine.py — deterministic compiler, PDF validation, page transforms,
  conservative blank detection, temporary output and no-overwrite commit.
- studio/ui.py — modern desktop workspace, thumbnail previews, workflow steps.
- studio/parser.py — safe offline prompt parser.
- studio/ai.py — optional key-based cloud/local model translation to JSON.
- studio/chatgpt.py — ChatGPT-plan OAuth, secure Windows sessions, model discovery,
  streamed Responses API instruction generation.
- studio/previews.py — on-demand local thumbnail rendering.
- studio/recipes.py — validated user workflows and built-in presets.
- studio/mcp_server.py — optional scoped stdio MCP tools.
- studio/cli.py — scriptable validated workflow runner.
- app.py — preserved original duplex tool.
- tests/ — original regression tests and synthetic-PDF integration coverage.

## Current limitations

PDF contents are not sent to AI. Semantic page searches or section detection,
OCR, password-unlocking, and visual semantic document analysis are not yet
supported. Blank page detection is pixel-heuristic and can misclassify faint
markings; always inspect the preview.

Previews show 12 output pages at a time. The BEFORE strip shows only the first
few input pages, rather than a pixel-diff comparison. Drag-reorder operates
on the selected output document and adds a validated reorder step. Thumbnail
generation may be slow on very large scanned PDFs. There is a 1 GiB input-size
limit, 25,000 pages per input, and bounded output count, but pypdf can still
consume significant memory on complex PDFs.

Cancel checks run between page operations. A binary PDF writer cannot be
interrupted mid-write. Outputs are prepared in same-folder temporary files,
then created without overwriting preexisting targets. Filesystems without hard
links use an exclusive-create fallback. No document text is logged.

The desktop UI passed a launch smoke test; no multi-monitor or human usability
test has been completed. MCP server initialization is tested but remote
connection to ChatGPT and Claude is not configured.
