# PDFManipulator — user guide

[Back to quick start](../README.md) · [Developer guide](DEVELOPER_GUIDE.md)

## 1. Open the application

**From this repository:** Download and extract the GitHub ZIP, install Python 3.11+ if needed, and double-click `Start PDFManipulator.bat`. The first run creates a private `.venv` folder and installs dependencies. Subsequent launches are local.

**From a built application:** Double-click `PDFManipulator.exe`. Python is already bundled.

The batch launcher automatically opens `dist\PDFManipulator.exe` when that file is present; otherwise it runs the Python source.

## 2. Add your PDFs

Select **+ Add PDFs** or drag PDF files into the app. A visible import bar lists the number of PDFs and each input alias (`input1`, `input2`, etc.), so you can confirm both files are present and in the intended order. Use **Clear inputs** to remove them from the current workflow without deleting the files from your computer.

Choose a preset under **Quick actions**, or type a request in **Describe your changes** and select **Build workflow**.

For example:

- “Combine these PDFs into one document”
- “Split this PDF every 3 pages”
- “Rotate even pages 180 degrees”
- “Extract pages 1-5”
- “Remove blank pages”

The offline parser understands a constrained set of instructions. If it cannot interpret a request safely, edit the workflow manually, choose a preset, or enable an optional AI provider.

## 3. Preview and edit

The **Document preview** displays thumbnails of the proposed output. Your requested changes are a *preview* until you save. At 100% zoom, six pages fit in a row. Zooming in increases each page's width and height, so fewer pages fit per row.

- **Edit workflow** opens the side panel to review and modify steps, input files, output names, and undo/redo.
- **Compare originals** shows the input preview.
- Use **+ / −** zoom to inspect pages.
- Click a page thumbnail to select it, then choose **Delete page** or **Rotate** above the preview. Drag thumbnails to reorder.
- Click **+ New workflow** in the top bar to start from a blank workspace without deleting saved workflows.
- You can save reusable workflows and import/export their recipe JSON.

**Do not export until the displayed page order is correct.** The blank-page detector is conservative and can misclassify faint markings.

## 4. Common tasks

### Merge several PDFs

Add the files in the intended order → choose **Merge PDFs** from Quick actions → inspect the preview → **Save as PDF**. This merges all currently imported PDFs in their import order.

### Combine front and back scans (duplex)

1. Scan front sides in ascending page order (1, 3, 5, …).
2. Flip the paper stack and scan the backs (normally in descending order).
3. Add both PDFs, with the front-side file first.
4. Choose **Duplex Scan Merger**, and inspect the interleaved result.
5. If back pages are upside-down or in ascending order, choose **Edit workflow** to change the reverse/rotation settings.
6. Export the result.

### Insert a PDF after other edits

Add both PDFs, then choose **Edit workflow** → **+ Insert PDF at position 1**. The resulting **Insert PDF** step places every page of `input2` at the beginning of the current output. Edit that step's **position** to a different 1-based page number, or type `end` to append the PDF.

For the request *“Delete the first Page of the first PDF. Add the second PDF to the first PDF and make sure the second PDF is page 1”*, enter the instruction and select **Build workflow**. The resulting steps are **Load first PDF → Delete page 1 → Insert second PDF at position 1**. Review all pages before saving.

### Split a document

Add a PDF → choose **Split Every N Pages** → adjust the number under **Edit workflow** → inspect each output → export.

### Extract or delete pages

Click a page thumbnail, then choose **Delete page** in the preview toolbar, or add a **Delete** step through **Edit workflow**. Page selectors are **1-based**, using forms such as `1,3,5-8`, `even`, `odd`, and `all`.

### Remove blank pages

Choose **Remove Blank Pages**, inspect the output, and restore any pages that were incorrectly classified before exporting.

## 5. Save the result

Click **Save as PDF** in the top-right. For a single output, a **Save As** dialog lets you choose both the folder and filename. For multiple outputs, choose the destination folder and review the generated filenames. If batch filenames already exist, the app proposes unused versioned filenames. The app never overwrites existing PDFs.

Source PDF documents are never modified.

## Optional AI instructions

The app has five interpretation modes:

| Mode | Internet | Credentials |
| --- | --- | --- |
| **Offline** | No | None |
| **ChatGPT plan** | Yes | Eligible ChatGPT account and interactive approval; no API key |
| **Ollama (local)** | No cloud API, but requires an installed local model | None |
| **OpenAI API** | Yes | `OPENAI_API_KEY` and separate API billing |
| **Claude API** | Yes | `ANTHROPIC_API_KEY` and separate API billing |

To connect ChatGPT:

1. Click **Continue with ChatGPT**.
2. Complete the sign-in and permission request in your system browser.
3. Return to PDFManipulator. If your account permits plan usage, open **AI settings** to select an offered model.
4. Add PDFs and type a request. Check **Send instruction text to selected AI** before building the workflow.
5. Review the generated workflow and page preview. Use **Save as PDF** to export locally.

**Privacy:** The AI interpreter sends the instruction and generic input labels such as `input1`, not your PDF bytes or actual PDF filenames. Avoid writing confidential information *in the instruction itself*, since that text is sent when you consent. ChatGPT plan usage is subject to eligibility and usage limits. The browser sign-in flow requires live user approval; automated tests use simulated responses rather than real accounts.

For OpenAI or Claude API mode, configure the corresponding environment variable before launching the app. These modes do not use consumer subscription allowances.

For Ollama, install a supported local Ollama server and model; the default endpoint is `http://127.0.0.1:11434`.

## Saved settings

Reusable workflows are stored in your Windows user profile at:

`%APPDATA%\PDFManipulator\recipes.json`

Encrypted ChatGPT session information is stored locally at:

`%LOCALAPPDATA%\PDFManipulator\chatgpt\accounts.dpapi`

Windows DPAPI protects saved session tokens. Existing saved data from the previous PDF Workflow Studio location is copied on first launch when the new location does not already have it.

Never upload these private files to GitHub.

## Troubleshooting

**Double-clicking the batch file closes immediately.** Open Command Prompt in the extracted project folder and run `"Start PDFManipulator.bat"` to read any installation error. Confirm Python 3.11+ is installed and the first run has internet access.

**I don't have `dist\PDFManipulator.exe`.** GitHub source downloads do not include this generated binary. Use the batch launcher or [build it locally](../README.md#build-your-own-windows-exe-optional).

**A prompt isn't understood.** Try one of the examples above or edit a workflow manually. Offline interpretation does not understand every English instruction.

**ChatGPT does not connect.** Check your internet connection, browser authorization, account eligibility, and ChatGPT usage limits. You can always switch back to **Offline**.

**PDF has missing or incorrectly ordered pages.** Inspect the source ordering, duplex reverse/rotation options, and blank-page removal setting.

**Need command-line or MCP integration?** See the [developer guide](DEVELOPER_GUIDE.md).

## Current limitations

PDFManipulator currently does not upload and semantically inspect PDF contents using AI. That means document-question answering, semantic section extraction, and OCR are not included in the ChatGPT instruction interpreter. Page thumbnails and transformations are produced locally. Very large, complex documents may take extra memory and processing time.
