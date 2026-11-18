# PDFManipulator — user guide

[Back to quick start](../README.md) · [Developer guide](DEVELOPER_GUIDE.md)

## 1. Open the application

**From this repository:** Download and extract the GitHub ZIP, install Python 3.11+ if needed, and double-click `Start PDFManipulator.bat`. The first run creates a private `.venv` folder and installs dependencies. Subsequent launches are local.

**From a built application:** Double-click `PDFManipulator.exe`. Python is already bundled.

The batch launcher automatically opens `dist\PDFManipulator.exe` when that file is present; otherwise it runs the Python source.

## 2. Import the PDFs

Use **+ Add PDFs** in the header or in the middle workflow builder. Imported files are shown as **PDF 1**, **PDF 2**, etc., with their filenames and import order. Originals are never changed by the preview.

Choose a **Start with** mode:

- **Edit PDFs separately** — the default for two or more PDFs added to a new workflow. Each imported document stays independent while you edit its pages
- **PDF 1 only** — use only the first PDF, then optionally insert another source later
- **Merge original PDFs now** — combine the untouched files *before* the following steps
- **Duplex scan pair** — interleave front/back scans using the duplex workflow

For a deletion *from the second PDF*, keep **Edit PDFs separately**. Choosing **Merge original PDFs now** first changes what page 1 means.

## 3. Build your workflow manually

The **Build your workflow** editor is visible automatically in the middle column. There is no separate editing drawer to open.

1. Import the PDF files and choose **Start with**.
2. In **Workflow steps**, choose **Delete pages**, **Rotate pages**, **Extract pages**, **Split every N pages**, or another operation from the dropdown.
3. Click **+ Step**. The **Configure workflow step** dialog opens.
4. Under **Apply changes to**, choose **PDF 1**, **PDF 2**, or **All current PDFs**, as appropriate.
5. Set the page selection (e.g., `1`, `2-5`, `even` or `all`) and click **Apply step**.
6. Add more steps as needed; use the ↑/↓ arrows to reorder them.
7. **When you are done editing the separate PDFs**, click **+ Merge edited PDFs**. This creates one output, with PDF 1 first by default.
8. Check the live preview on the right, then click **Save as PDF**.

You can select **Save reusable workflow** to store a recipe or **+ New workflow** to start from a clean workspace. Presets on the left are templates that replace the current steps after confirmation.

### Example: delete page 1 from PDF 2, then merge with PDF 1 first

Suppose PDF 1 contains A1, A2 and A3, while PDF 2 contains B1, B2 and B3. You want the final order to be **A1, A2, A3, B2, B3**.

1. Add PDF 1 and PDF 2 in that order.
2. Keep **Start with → Edit PDFs separately**.
3. Choose **Delete pages** from the operation dropdown and click **+ Step**.
4. Choose **Apply changes to → PDF 2**; enter **1** as the page number; click **Apply step**.
5. Click **+ Merge edited PDFs**. The default merge order is PDF 1, then the modified PDF 2.
6. Verify the preview. Click **Save as PDF** to choose the new filename.

This creates the following ordered steps:

~~~json
[
  {"op": "load_each", "sources": ["input1", "input2"]},
  {"op": "delete", "pages": "1", "document": 1},
  {"op": "merge_documents", "order": [1, 2]}
]
~~~

The numeric `document` field is **zero-based internally**. The graphical editor instead displays human labels such as **PDF 2**, so you don't need to work with JSON.

### Insert an entire PDF at a position

If you want to place the original PDF 2 within PDF 1 without separately editing PDF 2, use **PDF 1 only → + Insert PDF at position 1**. In the editor, select which imported PDF to insert and specify the position: `1` for the beginning, a larger page number for the middle, or `end` to append it.

### Duplex scanning

Import front and back scans, then choose **Start with → Duplex scan pair**. Inspect the sequence in the preview; adjust reversal and rotation in the advanced editor if needed.

## 4. Review the output

The preview on the right shows the current PDF pages. At 100% zoom, six thumbnail columns fit across the available area; zooming in enlarges pages and reduces columns.

Click a thumbnail to delete or rotate that page. For other edits, use the **Workflow steps** list. Some changes, such as removing blank pages, should always be reviewed carefully.

If your workflow creates multiple output PDFs, switch between their tabs in the preview. After **Merge edited PDFs**, the preview shows one combined output instead.

## 5. Save the result

Click **Save as PDF**. For one output, choose its filename and folder using the Save As dialog. For multiple outputs, choose a folder; the app proposes unused filenames when names would otherwise collide. Existing outputs and imported sources are never overwritten.

## Optional AI helper

Manual mode is the default. To see the instruction composer and AI providers, click **AI helper (optional)** in the top bar. Once an AI produces steps, you can review and edit them in the same manual builder. The AI panel can be hidden again at any time.

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
