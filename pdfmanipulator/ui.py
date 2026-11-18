"""Modern Windows desktop workspace built with CustomTkinter.

The visual UI never modifies source PDFs. A compiled page plan powers previews
and the guarded executor powers actual output. Optional AI receives prompts only.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
import webbrowser
import threading
from queue import Empty, Queue
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image

from .ai import translate
from .chatgpt import ChatGPTConnection, ChatGPTError, USAGE_URL
from .engine import Compilation, PageRef, WorkflowError, compile_workflow, execute_workflow, output_names, validate_steps
from .exports import next_available_pattern
from .parser import EXAMPLES
from .layout import thumbnail_layout
from .previews import image_for
from .recipes import PRESETS, export_recipe, import_recipe, preset, read_recipes, save_recipes, validate_recipe

ctk.set_default_color_theme("blue")

# Prefer the native Windows UI font over the toolkit Roboto default.
FONT_FAMILY = "Segoe UI"
def F(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
ctk.set_appearance_mode("Dark")
# CTk color tuples follow the active light/dark appearance mode automatically.
BG = ("#f5f7fb", "#0c1018")
SURFACE = ("#ffffff", "#171d29")
CARD = ("#edf2f9", "#1e2635")
BORDER = ("#d7e0ed", "#303a4b")
ACCENT = ("#397de2", "#5497f5")
TEXT = ("#142238", "#eef2fa")
MUTED = ("#536784", "#9aaac0")
BTN = ("#e9edf4", "#252d3b")
HOVER = ("#2966cd", "#3976e0")
CANVAS_BG = ("#f4f6fa", "#111723")

OP_DEFAULTS = {
    "merge": {"sources": ["input1", "input2"]},
    "merge_documents": {},
    "split_every": {"n": 3},
    "split_ranges": {"ranges": ["1"], "include_remaining": True},
    "extract": {"pages": "1"},
    "delete": {"pages": "1"},
    "insert_pdf": {"source": "input2", "position": 1},
    "reverse": {},
    "rotate": {"pages": "even", "degrees": 180},
    "duplicate": {"pages": "1", "times": 1},
    "remove_blanks": {"threshold": 0.003},
    "reorder": {"order": []},
}
START_MODES = {
    "Edit PDFs separately": "load_each",
    "PDF 1 only": "load",
    "Merge original PDFs now": "merge",
    "Duplex scan pair": "duplex",
}

DOCUMENT_ACTIONS = {
    "insert_pdf", "split_every", "split_ranges", "extract", "delete",
    "reorder", "reverse", "rotate", "duplicate", "remove_blanks",
}

STEP_OPTIONS = {
    "Merge edited PDFs": "merge_documents",
    "Insert / append PDF": "insert_pdf",
    "Split every N pages": "split_every",
    "Split into ranges": "split_ranges",
    "Extract pages": "extract",
    "Delete pages": "delete",
    "Reverse page order": "reverse",
    "Rotate pages": "rotate",
    "Duplicate pages": "duplicate",
    "Remove blank pages": "remove_blanks",
    "Reorder pages": "reorder",
}


def describe(step: dict) -> str:
    op = step["op"]
    descriptions = {
        "load": f"Open {step.get('source')}",
        "merge": "Join source PDFs now: " + ", ".join(step.get("sources", [])),
        "merge_documents": "Combine the edited PDF outputs, preserving their current order" +
                           (f" ({step['order']})" if "order" in step else ""),
        "insert_pdf": f"Insert all pages from {step.get('source')} at position {step.get('position')}",
        "load_each": "Open imported PDFs separately (edit each before merging)",
        "duplex": f"Interleave {step.get('fronts')} + {step.get('backs')}" +
                  ("  ·  reverse backs" if step.get("reverse_backs", True) else "") +
                  ("  ·  rotate backs" if step.get("rotate_backs") else ""),
        "interleave": "Alternate pages from two PDFs",
        "split_every": f"Split into files of {step.get('n')} pages",
        "split_ranges": "Split at " + ", ".join(map(str, step.get("ranges", []))) +
                        (" + remaining pages" if step.get("include_remaining") else ""),
        "extract": f"Keep pages {step.get('pages')}",
        "delete": f"Delete pages {step.get('pages')}",
        "reverse": "Reverse page order",
        "rotate": f"Rotate {step.get('pages')} pages by {step.get('degrees')}°",
        "duplicate": f"Duplicate pages {step.get('pages')}",
        "remove_blanks": "Detect and remove blank scans",
        "reorder": "Rearrange pages visually",
    }
    return descriptions.get(op, op.replace("_", " ").title())

class StepDialog(ctk.CTkToplevel):
    """Edit one manual step using PDF names and human page numbers."""

    def __init__(self, parent: "StudioApp", number: int):
        super().__init__(parent)
        self.parent = parent
        self.number = number
        self.step = deepcopy(parent.steps[number])
        self.title("Configure workflow step")
        self.geometry("520x550")
        self.minsize(470, 380)
        self.transient(parent)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        label = self.step["op"].replace("_", " ").title()
        ctk.CTkLabel(self, text=f"Step {number + 1} — {label}",
                     font=F(19, "bold"), text_color=TEXT, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        self.entries: dict[str, ctk.CTkEntry] = {}
        self.source_choices: dict[str, str] = {}
        self.target_choices: dict[str, int | None] = {}
        self.source_var: tk.StringVar | None = None
        self.target_var: tk.StringVar | None = None

        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.grid(row=1, column=0, padx=18, sticky="nsew")

        if self.step["op"] in DOCUMENT_ACTIONS and number > 0:
            try:
                previous = compile_workflow(parent.steps[:number], parent.sources)
                documents = previous.documents
            except WorkflowError:
                documents = []
            if documents:
                self.target_choices = {"All current PDFs": None}
                for index, document in enumerate(documents):
                    name = document.source_name[:34]
                    self.target_choices[f"PDF {index + 1} — {name}"] = index
                ctk.CTkLabel(container, text="Apply changes to", text_color=TEXT,
                             font=F(13, "bold")).pack(anchor="w", pady=(5, 5))
                current_target = self.step.get("document")
                current_label = next((
                    name for name, value in self.target_choices.items()
                    if value == current_target), "All current PDFs")
                self.target_var = tk.StringVar(value=current_label)
                ctk.CTkOptionMenu(
                    container, values=list(self.target_choices),
                    variable=self.target_var, fg_color=BTN, button_color=BORDER,
                    text_color=TEXT, font=F(12), height=37
                ).pack(fill="x", pady=(0, 9))
                ctk.CTkLabel(
                    container,
                    text="Choose PDF 2 to delete pages from the second file "
                         "before merging. Page numbers are relative to the chosen PDF.",
                    text_color=MUTED, font=F(11), wraplength=420,
                    justify="left").pack(anchor="w", pady=(0, 10))

        if self.step["op"] in ("insert_pdf", "merge"):
            sources = ", ".join(
                f"PDF {i + 1}: {path.name}" for i, path in enumerate(parent.sources.values()))
            ctk.CTkLabel(
                container, text="Imported: " + (sources or "Add PDF files first."),
                text_color=MUTED, font=F(11), wraplength=420,
                justify="left").pack(anchor="w", pady=(4, 9))

        for key, value in self.step.items():
            if key in ("op", "document"):
                continue
            heading = {
                "source": "Which PDF to insert?",
                "pages": "Page numbers (1,3,5-7, even, odd, all)",
                "position": "Insert before output page (1 = beginning; end = append)",
                "order": "Merge order (1 = PDF 1, 2 = PDF 2)",
                "degrees": "Rotation (90, 180, 270)",
                "n": "Pages per output PDF",
                "ranges": "Page ranges (JSON list)",
                "threshold": "Blank-page detection sensitivity",
            }.get(key, key.replace("_", " ").capitalize())
            ctk.CTkLabel(container, text=heading, anchor="w",
                         text_color=TEXT, font=F(12)).pack(
                fill="x", pady=(9, 5))
            if key == "source" and self.step["op"] == "insert_pdf" and parent.sources:
                self.source_choices = {
                    f"PDF {i + 1} — {path.name[:32]}": alias
                    for i, (alias, path) in enumerate(parent.sources.items())}
                selected = next(
                    (name for name, alias in self.source_choices.items() if alias == value),
                    next(iter(self.source_choices)))
                self.source_var = tk.StringVar(value=selected)
                ctk.CTkOptionMenu(
                    container, values=list(self.source_choices),
                    variable=self.source_var, fg_color=BTN, button_color=BORDER,
                    text_color=TEXT, font=F(12), height=37
                ).pack(fill="x")
                continue
            hint = json.dumps(value) if isinstance(value, (list, bool, float, int)) else str(value)
            entry = ctk.CTkEntry(container, fg_color=SURFACE, text_color=TEXT,
                                 font=F(13), border_color=BORDER, height=38)
            entry.insert(0, hint)
            entry.pack(fill="x")
            self.entries[key] = entry

        ctk.CTkLabel(
            self, text="Changes update the preview, not the original PDFs.",
            text_color=MUTED, font=F(11)).grid(row=2, column=0, pady=(12, 6))
        ctk.CTkButton(
            self, text="Apply step", command=self.commit,
            font=F(13, "bold"), fg_color=ACCENT, height=41
        ).grid(row=3, column=0, padx=20, pady=(0, 17), sticky="ew")

    def commit(self):
        candidate = dict(self.step)
        try:
            for key, entry in self.entries.items():
                value_text = entry.get().strip()
                old = self.step[key]
                if key == "position":
                    value = "end" if value_text.lower() == "end" else int(value_text)
                elif isinstance(old, bool):
                    if value_text.lower() not in ("true", "false"):
                        raise WorkflowError(f"{key} must be true or false.")
                    value = value_text.lower() == "true"
                elif isinstance(old, int):
                    value = int(value_text)
                elif isinstance(old, float):
                    value = float(value_text)
                elif isinstance(old, list):
                    value = json.loads(value_text)
                else:
                    value = value_text
                candidate[key] = value
            if self.source_var is not None:
                candidate["source"] = self.source_choices[self.source_var.get()]
            if self.target_var is not None:
                selected_target = self.target_choices[self.target_var.get()]
                if selected_target is None:
                    candidate.pop("document", None)
                else:
                    candidate["document"] = selected_target
            proposed = deepcopy(self.parent.steps)
            proposed[self.number] = candidate
            validate_steps(proposed)
            if self.parent.sources:
                compile_workflow(proposed, self.parent.sources)
            self.parent.set_steps(proposed)
            self.destroy()
        except (WorkflowError, ValueError, TypeError, KeyError,
                json.JSONDecodeError) as exc:
            messagebox.showerror("Invalid workflow step", str(exc), parent=self)


class StudioApp(TkinterDnD.DnDWrapper, ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDFManipulator")
        self.geometry("1540x940")
        self.minsize(1240, 720)
        self.configure(fg_color=BG)
        self.sources: dict[str, Path] = {}
        self.steps: list[dict] = [{"op": "load", "source": "input1"}]
        self.workflow_name = "Untitled workflow"
        try:
            self.recipes = read_recipes()
        except WorkflowError:
            self.recipes = {}
        self.selected_recipe_name: str | None = None
        self.before_image_refs: list[ctk.CTkImage] = []
        self.compiled: Compilation | None = None
        self.active_document = 0
        self.page_offset = 0
        self.zoom_scale = 1.0
        self.zoom_var = tk.StringVar(value="100%")
        self.files_summary_var = tk.StringVar(value="No PDFs imported yet")
        self._page_resize_job = None
        self._rendered_area_width = 0
        self.selected_page: int | None = None
        self.drag_page: int | None = None
        self.undo_stack: list[list[dict]] = []
        self.redo_stack: list[list[dict]] = []
        self.busy = False
        self._ui_queue = Queue()
        self.cancel = threading.Event()
        self.image_refs: list[ctk.CTkImage] = []
        self.filename_pattern = tk.StringVar(value="{source}_{index:02d}")
        self.status_var = tk.StringVar(value="Add PDFs or start from a preset. Files stay on this computer.")
        try:
            self.chatgpt = ChatGPTConnection()
            self.chatgpt_init_error = None
        except ChatGPTError as exc:
            self.chatgpt = None
            self.chatgpt_init_error = str(exc)
        logged_in = self.chatgpt.session()["sharing"] if self.chatgpt else False
        self.provider_var = tk.StringVar(value="ChatGPT plan" if logged_in else "Offline")
        self.model_var = tk.StringVar(value="Connect to select a model")
        self.chatgpt_status_var = tk.StringVar(value="ChatGPT not connected")
        self.chatgpt_model_names: dict[str, str] = {}
        self.consent_var = tk.BooleanVar(value=logged_in)
        self._create_layout()
        self._populate_presets()
        self._populate_recipes()
        self._populate_sources()
        self._populate_steps()
        self._update_import_banner()
        self._setup_drop()
        self._bind_shortcuts()
        self.after(40, self._drain_ui_events)
        self._sync_chatgpt_ui()
        if self.chatgpt and self.chatgpt.session()["sharing"]:
            self.after(180, self._load_chatgpt_models)
        self.after(100, self.preview)

    def _dispatch_ui(self, callback):
        """Queue UI callbacks without invoking Tkinter from a worker thread."""
        self._ui_queue.put(callback)

    def _drain_ui_events(self):
        for _ in range(100):
            try:
                callback = self._ui_queue.get_nowait()
            except Empty:
                break
            try:
                callback()
            except Exception as exc:
                self.status_var.set(f"UI operation failed: {str(exc)[:120]}")
        if self.winfo_exists():
            self.after(40, self._drain_ui_events)

    def _create_layout(self):
        """Preview-first desktop layout; advanced controls live in a drawer."""
        self.grid_columnconfigure(0, weight=0, minsize=218)
        self.grid_columnconfigure(1, weight=0, minsize=400)
        self.grid_columnconfigure(2, weight=1, minsize=530)
        self.grid_rowconfigure(1, weight=1)

        # Top application bar — only the actions needed on every screen.
        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0, height=64)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=24, pady=(16, 12))
        header.pack_propagate(False)
        mark = ctk.CTkFrame(header, fg_color=ACCENT, width=38, height=38, corner_radius=11)
        mark.pack(side="left", padx=(0, 12))
        mark.pack_propagate(False)
        ctk.CTkLabel(mark, text="P", font=F(19, "bold"), text_color="#ffffff").pack(expand=True)
        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left")
        ctk.CTkLabel(brand, text="PDFManipulator", font=F(21, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(brand, text="WORKFLOWS / LOCAL", font=F(10, "bold"),
                     text_color=MUTED).pack(anchor="w")
        self.run_button = ctk.CTkButton(header, text="Save as PDF", width=130, height=39,
                                        fg_color=ACCENT, hover_color=HOVER,
                                        font=F(13, "bold"), command=self.run)
        self.run_button.pack(side="right", padx=(10, 0))
        ctk.CTkButton(header, text="+ New workflow", width=136, height=39,
                      fg_color=BTN, text_color=TEXT, hover_color=CARD,
                      font=F(13), command=self.new_workflow).pack(side="right", padx=5)
        self.drawer_button = ctk.CTkButton(header, text="Hide builder", width=133, height=39,
                                           fg_color=BTN, text_color=TEXT,
                                           hover_color=CARD, font=F(13),
                                           command=self.toggle_inspector)
        self.drawer_button.pack(side="right", padx=5)
        ctk.CTkButton(header, text="+ Add PDFs", width=112, height=39, fg_color=BTN,
                      text_color=TEXT, hover_color=CARD, font=F(13),
                      command=self.browse_files).pack(side="right", padx=5)
        self.ai_composer_button = ctk.CTkButton(
            header, text="AI helper (optional)", width=141, height=39,
            fg_color="transparent", text_color=MUTED, hover_color=BTN,
            font=F(12), command=self.toggle_ai_composer)
        self.ai_composer_button.pack(side="right", padx=(0, 8))

        # Narrow library: quiet navigation without stacked editing controls.
        self.sidebar = ctk.CTkFrame(self, width=210, fg_color=SURFACE, corner_radius=14)
        self.sidebar.grid(row=1, column=0, sticky="nsew", padx=(22, 9), pady=(0, 9))
        self.sidebar.pack_propagate(False)
        ctk.CTkLabel(self.sidebar, text="WORKFLOW LIBRARY", font=F(11, "bold"),
                     text_color=MUTED).pack(anchor="w", padx=17, pady=(23, 12))
        ctk.CTkLabel(self.sidebar, text="Workflow templates", text_color=TEXT,
                     font=F(14, "bold")).pack(anchor="w", padx=17, pady=(0, 5))
        ctk.CTkLabel(self.sidebar, text="Selecting a template replaces current steps.",
                     text_color=MUTED, font=F(10), wraplength=170,
                     justify="left").pack(anchor="w", padx=17, pady=(0, 9))
        self.preset_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.preset_frame.pack(fill="x", padx=9)
        ctk.CTkFrame(self.sidebar, height=1, fg_color=BORDER).pack(fill="x",
                          padx=16, pady=(17, 13))
        saved_title = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        saved_title.pack(fill="x", padx=14)
        ctk.CTkLabel(saved_title, text="Saved workflows", font=F(13, "bold"),
                     text_color=TEXT).pack(side="left")
        self.saved_toggle = ctk.CTkButton(saved_title, text="Show", width=49, height=26,
                                          fg_color=BTN, text_color=TEXT,
                                          font=F(11), command=self.toggle_saved)
        self.saved_toggle.pack(side="right")
        self.saved_area = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.recipe_frame = ctk.CTkScrollableFrame(self.saved_area, fg_color="transparent",
                                                   height=160, corner_radius=5)
        self.recipe_frame.pack(fill="x", padx=6, pady=(9, 4))
        saved_actions = ctk.CTkFrame(self.saved_area, fg_color="transparent")
        saved_actions.pack(fill="x", padx=10, pady=(2, 6))
        for name, cmd in (("Copy", self.duplicate_recipe),
                          ("Export", self.export_selected_recipe),
                          ("Delete", self.delete_recipe)):
            ctk.CTkButton(saved_actions, text=name, width=53, height=26,
                          fg_color=BTN, text_color=TEXT, font=F(11),
                          command=cmd).pack(side="left", padx=(0, 4))
        ctk.CTkButton(self.saved_area, text="Import recipe", fg_color=BTN,
                      text_color=TEXT, font=F(12), height=31,
                      command=self.import_recipe).pack(fill="x", padx=12, pady=(0, 9))
        ctk.CTkButton(self.sidebar, text="+ Save this workflow", fg_color=BTN,
                      text_color=TEXT, font=F(12), height=34,
                      command=self.save_recipe).pack(fill="x", padx=16, pady=(14, 8))
        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=16, pady=(0, 17))
        ctk.CTkLabel(bottom, text="APPEARANCE", text_color=MUTED,
                     font=F(10, "bold")).pack(anchor="w", pady=(0, 7))
        self.theme_var = tk.StringVar(value="Dark")
        ctk.CTkOptionMenu(bottom, values=["Dark", "Light", "System"],
                          variable=self.theme_var, command=ctk.set_appearance_mode,
                          height=32, fg_color=BTN, button_color=BORDER,
                          text_color=TEXT, font=F(12)).pack(fill="x")
        ctk.CTkLabel(bottom, text="Processed locally. Sources stay safe.",
                     text_color=MUTED, font=F(10), wraplength=175,
                     justify="left").pack(anchor="w", pady=(12, 0))

        # Main workspace: deliberately more room for the document.
        self.mainpane = ctk.CTkFrame(self, fg_color=BG)
        self.mainpane.grid(row=1, column=2, sticky="nsew", padx=(2, 20), pady=(0, 9))
        self.mainpane.grid_columnconfigure(0, weight=1)
        self.mainpane.grid_rowconfigure(2, weight=1)

        composer = ctk.CTkFrame(self.mainpane, fg_color=SURFACE, corner_radius=14)
        self.composer = composer
        self.ai_composer_visible = False
        composer.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        composer.grid_remove()
        composer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(composer, text="Describe your changes",
                     font=F(19, "bold"), text_color=TEXT).grid(
                     row=0, column=0, sticky="w", padx=22, pady=(19, 2))
        ctk.CTkLabel(composer, text="Write an instruction, or choose a workflow on the left.",
                     font=F(12), text_color=MUTED).grid(
                     row=1, column=0, sticky="w", padx=22, pady=(0, 11))
        self.prompt = ctk.CTkTextbox(composer, height=67, fg_color=CARD,
                                     border_color=BORDER, border_width=1,
                                     text_color=TEXT, font=F(14),
                                     wrap="word", corner_radius=9)
        self.prompt.grid(row=2, column=0, padx=22, sticky="ew")
        # AI instructions are optional; the manual workflow builder is primary.
        prompt_actions = ctk.CTkFrame(composer, fg_color="transparent")
        prompt_actions.grid(row=3, column=0, sticky="ew", padx=22, pady=(10, 14))
        self.ai_toggle_button = ctk.CTkButton(prompt_actions, text="AI settings",
                                              width=104, height=31, fg_color="transparent",
                                              text_color=MUTED, hover_color=CARD,
                                              font=F(12), command=self.toggle_ai_settings)
        self.ai_toggle_button.pack(side="left")
        self.chatgpt_button = ctk.CTkButton(
            prompt_actions, text="Continue with ChatGPT", width=176, height=33,
            fg_color=("#111111", "#f0f0f0"),
            text_color=("#ffffff", "#111111"),
            hover_color=("#303030", "#dddddd"), font=F(12, "bold"),
            command=self._chatgpt_button_clicked)
        self.chatgpt_button.pack(side="left", padx=(9, 8))
        self.chatgpt_status_label = ctk.CTkLabel(
            prompt_actions, textvariable=self.chatgpt_status_var,
            text_color=MUTED, font=F(11))
        self.chatgpt_status_label.pack(side="left", padx=(0, 5))
        ctk.CTkButton(prompt_actions, text="Build workflow", command=self.interpret_prompt,
                      fg_color=ACCENT, hover_color=HOVER, width=148,
                      height=35, font=F(13, "bold")).pack(side="right")
        self.ai_options = ctk.CTkFrame(composer, fg_color=CARD, corner_radius=9)
        ai_row = ctk.CTkFrame(self.ai_options, fg_color="transparent")
        ai_row.pack(fill="x", padx=12, pady=(8, 5))
        ctk.CTkLabel(ai_row, text="Interpreter", text_color=MUTED,
                     font=F(12)).pack(side="left", padx=(0, 10))
        self.provider_menu = ctk.CTkOptionMenu(
            ai_row, values=["ChatGPT plan", "Offline", "Ollama (local)", "OpenAI API", "Claude API"],
            variable=self.provider_var, width=145, height=32,
            fg_color=BTN, button_color=BORDER, text_color=TEXT,
            font=F(12), command=self._provider_changed)
        self.provider_menu.pack(side="left")
        self.allow_cloud = ctk.CTkCheckBox(
            ai_row, text="Send instruction text to selected AI (never PDFs)",
            variable=self.consent_var, text_color=TEXT, font=F(11),
            checkbox_width=17, checkbox_height=17)
        self.allow_cloud.pack(side="left", padx=(16, 0))
        self.chatgpt_model_row = ctk.CTkFrame(self.ai_options, fg_color="transparent")
        ctk.CTkLabel(self.chatgpt_model_row, text="ChatGPT model", text_color=MUTED,
                     font=F(12)).pack(side="left", padx=(12, 10))
        self.chatgpt_model_menu = ctk.CTkOptionMenu(
            self.chatgpt_model_row, values=["Connect to select a model"],
            variable=self.model_var, width=210, height=32,
            fg_color=BTN, button_color=BORDER, text_color=TEXT,
            font=F(12), command=self._select_chatgpt_model)
        self.chatgpt_model_menu.pack(side="left")
        ctk.CTkButton(self.chatgpt_model_row, text="Refresh models", width=110,
                      height=31, font=F(11), fg_color=BTN, text_color=TEXT,
                      command=self._load_chatgpt_models).pack(side="left", padx=7)
        ctk.CTkButton(self.chatgpt_model_row, text="Manage usage", width=100,
                      height=31, font=F(11), fg_color=BTN, text_color=TEXT,
                      command=lambda: webbrowser.open(USAGE_URL)).pack(side="left")
        self.ai_privacy_label = ctk.CTkLabel(
            self.ai_options,
            text="ChatGPT receives only instruction text and input labels. PDF files remain local.",
            font=F(11), text_color=MUTED)
        self.ai_privacy_label.pack(anchor="w", padx=13, pady=(3, 10))
        self.ai_settings_visible = False
        self.file_banner = ctk.CTkFrame(composer, fg_color=CARD, corner_radius=8)
        self.file_banner.grid(row=5, column=0, sticky="ew", padx=22, pady=(0, 12))
        ctk.CTkLabel(self.file_banner, textvariable=self.files_summary_var,
                     text_color=TEXT, font=F(11), anchor="w",
                     justify="left", wraplength=750).pack(side="left", fill="x", expand=True, padx=12, pady=8)
        ctk.CTkButton(self.file_banner, text="Clear inputs", width=88, height=27,
                      fg_color=BTN, text_color=TEXT, font=F(11),
                      command=self.clear_files).pack(side="right", padx=9, pady=5)
        suggestion = ctk.CTkFrame(self.mainpane, fg_color="transparent")
        self.suggestion_row = suggestion
        suggestion.grid(row=1, column=0, sticky="ew", pady=(0, 11))
        suggestion.grid_remove()
        ctk.CTkLabel(suggestion, text="Try", text_color=MUTED,
                     font=F(12)).pack(side="left", padx=(3, 10))
        self.examples_frame = ctk.CTkFrame(suggestion, fg_color="transparent")
        self.examples_frame.pack(side="left", fill="x", expand=True)
        self._refresh_suggestions()

        # Preview canvas — one large visual surface, before strip hidden by default.
        canvas = ctk.CTkFrame(self.mainpane, fg_color=SURFACE, corner_radius=14)
        canvas.grid(row=2, column=0, sticky="nsew")
        canvas.grid_columnconfigure(0, weight=1)
        canvas.grid_rowconfigure(4, weight=1)
        toolbar = ctk.CTkFrame(canvas, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        ctk.CTkLabel(toolbar, text="Document preview", font=F(17, "bold"),
                     text_color=TEXT).pack(side="left")
        self.compare_button = ctk.CTkButton(toolbar, text="Compare originals",
                                             width=128, height=30, fg_color=BTN,
                                             hover_color=CARD, text_color=TEXT,
                                             font=F(11), command=self.toggle_compare)
        self.compare_button.pack(side="right", padx=(6, 0))
        for char, delta in (("+", 0.2), ("−", -0.2)):
            ctk.CTkButton(toolbar, text=char, width=30, height=30,
                          fg_color=BTN, hover_color=CARD, text_color=TEXT,
                          font=F(14, "bold"),
                          command=lambda d=delta: self.change_zoom(d)).pack(side="right", padx=3)
        ctk.CTkLabel(toolbar, textvariable=self.zoom_var, font=F(11),
                     text_color=MUTED, width=40).pack(side="right", padx=(8, 6))
        ctk.CTkButton(toolbar, text="Delete page", width=83, height=30,
                      fg_color=BTN, hover_color=CARD, text_color=TEXT,
                      font=F(11), command=self.delete_selected_page).pack(side="right", padx=4)
        ctk.CTkButton(toolbar, text="Rotate", width=62, height=30,
                      fg_color=BTN, hover_color=CARD, text_color=TEXT,
                      font=F(11), command=self.rotate_selected_page).pack(side="right", padx=4)
        self.preview_label = ctk.CTkLabel(canvas, text="Add PDFs to see a preview.",
                                          font=F(12), text_color=MUTED, anchor="w")
        self.preview_label.grid(row=1, column=0, padx=22, pady=(0, 5), sticky="ew")
        self.output_tabs = ctk.CTkScrollableFrame(canvas, orientation="horizontal",
                                                   height=42, fg_color="transparent")
        self.output_tabs.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 5))
        self.before_strip = ctk.CTkFrame(canvas, fg_color=CARD,
                                          corner_radius=8, height=106)
        self.before_strip.grid(row=3, column=0, sticky="ew", padx=17, pady=(0, 9))
        self.before_strip.grid_remove()
        self.compare_visible = False
        self.page_list = ctk.CTkScrollableFrame(canvas, fg_color=CANVAS_BG,
                                                 corner_radius=9)
        self.page_list.grid(row=4, column=0, sticky="nsew", padx=17, pady=(0, 6))
        canvas.bind("<Configure>", self._on_preview_resize)
        page_nav = ctk.CTkFrame(canvas, fg_color="transparent")
        page_nav.grid(row=5, column=0, sticky="ew", padx=20, pady=(5, 15))
        self.prev_btn = ctk.CTkButton(page_nav, text="Previous", width=98, height=31,
                                      fg_color=BTN, hover_color=CARD, text_color=TEXT,
                                      font=F(12),
                                      command=lambda: self.change_page_offset(-12))
        self.prev_btn.pack(side="left")
        self.page_count_label = ctk.CTkLabel(page_nav, text="", text_color=MUTED,
                                             font=F(12))
        self.page_count_label.pack(side="left", padx=15)
        self.next_btn = ctk.CTkButton(page_nav, text="Next", width=84, height=31,
                                      fg_color=BTN, hover_color=CARD, text_color=TEXT,
                                      font=F(12),
                                      command=lambda: self.change_page_offset(12))
        self.next_btn.pack(side="right")

        # Inspector: visible only when the user chooses to edit workflow details.
        self.inspector = ctk.CTkScrollableFrame(self, width=389, fg_color=SURFACE,
                                                corner_radius=14)
        self.inspector.grid(row=1, column=1, sticky="nsew", padx=(4, 10), pady=(0, 9))
        self.inspector_visible = True
        top = ctk.CTkFrame(self.inspector, fg_color="transparent")
        top.pack(fill="x", pady=(9, 17))
        ctk.CTkLabel(top, text="Build your workflow", font=F(19, "bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(top, text="MANUAL MODE", text_color=ACCENT,
                     font=F(10, "bold")).pack(side="right")
        ctk.CTkLabel(self.inspector, text="INPUT FILES", text_color=MUTED,
                     font=F(10, "bold")).pack(anchor="w", pady=(0, 8))
        self.input_status = ctk.CTkLabel(
            self.inspector, textvariable=self.files_summary_var,
            text_color=MUTED, font=F(11), anchor="w",
            justify="left", wraplength=345)
        self.input_status.pack(fill="x", pady=(0, 6))
        self.sources_frame = ctk.CTkFrame(self.inspector, fg_color="transparent")
        self.sources_frame.pack(fill="x")
        ctk.CTkButton(self.inspector, text="+ Add files", command=self.browse_files,
                      fg_color=BTN, text_color=TEXT, font=F(12),
                      height=30).pack(fill="x", pady=(9, 10))
        ctk.CTkLabel(self.inspector, text="START WITH", text_color=MUTED,
                     font=F(10, "bold")).pack(anchor="w", pady=(0, 5))
        self.start_mode_var = tk.StringVar(value="PDF 1 only")
        self.start_mode_menu = ctk.CTkOptionMenu(
            self.inspector, values=list(START_MODES), variable=self.start_mode_var,
            command=self.change_start_mode, fg_color=BTN, button_color=BORDER,
            text_color=TEXT, font=F(12), height=36)
        self.start_mode_menu.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(self.inspector,
                     text="Choose separate PDFs to edit each file before merging.",
                     text_color=MUTED, font=F(11), wraplength=340,
                     justify="left").pack(anchor="w", pady=(0, 17))
        ctk.CTkLabel(self.inspector, text="WORKFLOW STEPS  ·  TOP TO BOTTOM", text_color=MUTED,
                     font=F(10, "bold")).pack(anchor="w")
        ctk.CTkLabel(self.inspector,
                     text="For PDF 2 edits, choose PDF 2 in the step settings. "
                          "Merge edited PDFs only AFTER those edits.",
                     text_color=MUTED, font=F(11), wraplength=345,
                     justify="left").pack(anchor="w", pady=(6, 9))
        self.workflow_label = ctk.CTkLabel(self.inspector, text=self.workflow_name,
                                           font=F(15, "bold"), text_color=TEXT,
                                           wraplength=265, justify="left")
        self.workflow_label.pack(anchor="w", pady=(6, 12))
        self.step_frame = ctk.CTkFrame(self.inspector, fg_color="transparent")
        self.step_frame.pack(fill="x")
        addrow = ctk.CTkFrame(self.inspector, fg_color="transparent")
        addrow.pack(fill="x", pady=(12, 8))
        self.add_op = ctk.CTkOptionMenu(addrow, values=list(STEP_OPTIONS),
                                        fg_color=BTN, button_color=BORDER,
                                        text_color=TEXT, font=F(12), width=172)
        self.add_op.pack(side="left", fill="x", expand=True)
        self.add_op.set("Delete pages")
        ctk.CTkButton(addrow, text="+ Step", width=74, height=33,
                      font=F(12), fg_color=ACCENT, command=self.add_step).pack(
                          side="right", padx=(8, 0))
        ctk.CTkButton(self.inspector, text="+ Merge edited PDFs",
                      fg_color=ACCENT, text_color="#ffffff", font=F(12, "bold"), height=36,
                      command=lambda: self.add_step("merge_documents")).pack(fill="x", pady=(4, 8))
        ctk.CTkButton(self.inspector, text="+ Insert PDF at position 1",
                      fg_color=BTN, text_color=TEXT, font=F(12), height=32,
                      command=lambda: self.add_step("insert_pdf")).pack(fill="x", pady=(0, 10))
        actions = ctk.CTkFrame(self.inspector, fg_color="transparent")
        actions.pack(fill="x", pady=(3, 21))
        for label, cmd in (("Undo", self.undo), ("Redo", self.redo),
                           ("Advanced", self.edit_json)):
            ctk.CTkButton(actions, text=label, font=F(11),
                          fg_color=BTN, text_color=TEXT,
                          width=75, height=30, command=cmd).pack(
                              side="left", padx=(0, 5))
        ctk.CTkButton(self.inspector, text="Save reusable workflow",
                      fg_color=BTN, text_color=TEXT, font=F(12), height=34,
                      command=self.save_recipe).pack(fill="x", pady=(0, 13))
        ctk.CTkFrame(self.inspector, height=1, fg_color=BORDER).pack(fill="x",
                          pady=(0, 18))
        ctk.CTkLabel(self.inspector, text="OUTPUT", text_color=MUTED,
                     font=F(10, "bold")).pack(anchor="w", pady=(0, 6))
        self.outputs_label = ctk.CTkLabel(self.inspector, text="No preview yet",
                                          text_color=TEXT, font=F(12),
                                          justify="left", anchor="w", wraplength=265)
        self.outputs_label.pack(anchor="w", pady=(2, 12))
        ctk.CTkLabel(self.inspector, text="File naming pattern", text_color=MUTED,
                     font=F(12)).pack(anchor="w", pady=(0, 5))
        self.pattern_entry = ctk.CTkEntry(self.inspector,
                                          textvariable=self.filename_pattern,
                                          fg_color=CARD, text_color=TEXT,
                                          border_color=BORDER, font=F(12), height=35)
        self.pattern_entry.pack(fill="x")
        self.pattern_entry.bind("<Return>", lambda _event: self.preview())
        self.pattern_entry.bind("<FocusOut>", lambda _event: self.preview())
        ctk.CTkLabel(self.inspector, text="{source}  ·  {index:02d}",
                     text_color=MUTED, font=F(10)).pack(anchor="w", pady=(6, 13))
        ctk.CTkButton(self.inspector, text="Refresh preview", command=self.preview,
                      fg_color=BTN, text_color=TEXT, height=34,
                      font=F(12)).pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(self.inspector,
                     text="Source files are never overwritten.",
                     font=F(11), text_color=MUTED).pack(anchor="w")

        # Single-line status; execution controls are subtle when idle.
        footer = ctk.CTkFrame(self, fg_color=BG, height=34, corner_radius=0)
        footer.grid(row=2, column=0, columnspan=3, sticky="ew",
                    padx=25, pady=(3, 14))
        ctk.CTkLabel(footer, textvariable=self.status_var, text_color=MUTED,
                     font=F(11), anchor="w").pack(side="left", fill="x", expand=True)
        self.progress = ctk.CTkProgressBar(footer, width=120, height=6,
                                          progress_color=ACCENT)
        self.progress.set(0)
        self.progress.pack(side="right", padx=10)
        self.stop_button = ctk.CTkButton(footer, text="Cancel", width=65, height=28,
                                         state="disabled", command=self.cancel.set,
                                         fg_color=BTN, text_color=TEXT, font=F(11))
        self.stop_button.pack(side="right")

    def toggle_inspector(self):
        self.inspector_visible = not self.inspector_visible
        if self.inspector_visible:
            self.grid_columnconfigure(1, weight=0, minsize=400)
            self.inspector.grid()
            self.mainpane.grid_configure(column=2, columnspan=1, padx=(2, 20))
            self.drawer_button.configure(text="Hide builder")
        else:
            self.inspector.grid_remove()
            self.grid_columnconfigure(1, weight=0, minsize=0)
            self.mainpane.grid_configure(column=1, columnspan=2, padx=(5, 20))
            self.drawer_button.configure(text="Show builder")
        if self.compiled:
            self.after(80, self._render_pages)

    def toggle_ai_composer(self):
        self.ai_composer_visible = not self.ai_composer_visible
        if self.ai_composer_visible:
            self.composer.grid()
            self.suggestion_row.grid()
            self.ai_composer_button.configure(text="Hide AI helper")
        else:
            self.composer.grid_remove()
            self.suggestion_row.grid_remove()
            self.ai_composer_button.configure(text="AI helper (optional)")

    def toggle_saved(self):
        if self.saved_area.winfo_manager():
            self.saved_area.pack_forget()
            self.saved_toggle.configure(text="Show")
        else:
            self.saved_area.pack(fill="x", padx=6)
            self.saved_toggle.configure(text="Hide")

    def toggle_ai_settings(self):
        self.ai_settings_visible = not self.ai_settings_visible
        if self.ai_settings_visible:
            self.ai_options.grid(row=4, column=0, sticky="ew",
                                 padx=22, pady=(0, 14))
            self._provider_changed(self.provider_var.get())
            self.ai_toggle_button.configure(text="Hide AI settings")
        else:
            self.ai_options.grid_remove()
            self.ai_toggle_button.configure(text="AI settings")

    def toggle_compare(self):
        self.compare_visible = not self.compare_visible
        if self.compare_visible:
            self.before_strip.grid()
            self.compare_button.configure(text="Hide comparison")
            if self.compiled:
                self._render_before()
        else:
            self.before_strip.grid_remove()
            self.compare_button.configure(text="Compare originals")

    def _provider_changed(self, mode: str):
        """Keep advanced model controls out of the offline UI."""
        if mode == "ChatGPT plan":
            if not self.chatgpt_model_row.winfo_manager():
                self.chatgpt_model_row.pack(fill="x", before=self.ai_privacy_label,
                                            pady=(0, 6))
        else:
            self.chatgpt_model_row.pack_forget()

    def _sync_chatgpt_ui(self):
        if not self.chatgpt:
            self.chatgpt_status_var.set(self.chatgpt_init_error or "ChatGPT unavailable")
            self.chatgpt_button.configure(text="ChatGPT unavailable", state="disabled")
            return
        session = self.chatgpt.session()
        if session["sharing"]:
            self.chatgpt_status_var.set("Using ChatGPT plan")
            self.chatgpt_button.configure(text="ChatGPT account", state="normal")
        elif session["connected"]:
            self.chatgpt_status_var.set("Plan use not enabled")
            self.chatgpt_button.configure(text="ChatGPT account", state="normal")
        else:
            self.chatgpt_status_var.set("No API key needed")
            self.chatgpt_button.configure(text="Continue with ChatGPT", state="normal")
        self._provider_changed(self.provider_var.get())

    def _chatgpt_button_clicked(self):
        if not self.chatgpt:
            return
        session = self.chatgpt.session()
        if session["profiles"]:
            self._manage_chatgpt_accounts()
        else:
            self.connect_chatgpt()

    def connect_chatgpt(self, *, new_account: bool = False,
                        profile_id: str | None = None):
        if not self.chatgpt:
            self._error(self.chatgpt_init_error or "ChatGPT is unavailable.")
            return
        self.chatgpt_button.configure(state="disabled")
        self.chatgpt_status_var.set("Connecting in browser…")
        self.status_var.set("Authorize PDFManipulator in your browser.")
        def work():
            try:
                session = self.chatgpt.sign_in(new_account=new_account,
                                               profile_id=profile_id)
                models, model_error = [], ""
                if session["sharing"]:
                    try:
                        models = self.chatgpt.models()
                    except ChatGPTError as exc:
                        model_error = str(exc)
                self._dispatch_ui( lambda: self._chatgpt_signed_in(session, models, model_error))
            except Exception as exc:
                msg = str(exc)
                self._dispatch_ui( lambda: self._chatgpt_connect_error(msg))
        threading.Thread(target=work, daemon=True).start()

    def _chatgpt_signed_in(self, session: dict, models: list[dict], model_error: str):
        if session["sharing"]:
            self.provider_var.set("ChatGPT plan")
            self.consent_var.set(True)
            self.status_var.set("ChatGPT connected. Instructions can use your ChatGPT plan.")
        else:
            self.provider_var.set("Offline")
            self.consent_var.set(False)
            self.status_var.set("Signed in, but ChatGPT plan usage was not approved.")
        self._sync_chatgpt_ui()
        self._show_chatgpt_models(models)
        if model_error:
            self.status_var.set("ChatGPT connected, but models could not load: " + model_error[:110])
        if session["sharing"] and self.chatgpt.mark_welcome_seen():
            messagebox.showinfo(
                "You're using your ChatGPT plan",
                "Eligible AI instructions in PDFManipulator can use your ChatGPT plan.\n\n"
                "Only instruction text and generic input labels are sent, never your PDFs.\n"
                "Manage limits in ChatGPT Settings > Usage.",
                parent=self)

    def _chatgpt_connect_error(self, message: str):
        self._sync_chatgpt_ui()
        self.status_var.set("ChatGPT sign-in was not completed.")
        messagebox.showerror("Connect to ChatGPT", message, parent=self)

    def _show_chatgpt_models(self, models: list[dict]):
        self.chatgpt_model_names.clear()
        for item in models:
            label = item["name"]
            if label in self.chatgpt_model_names:
                label += " (" + item["slug"] + ")"
            self.chatgpt_model_names[label] = item["slug"]
        choices = list(self.chatgpt_model_names) or ["No models available"]
        self.chatgpt_model_menu.configure(values=choices)
        selected = self.chatgpt.session()["model"] if self.chatgpt else None
        label = next((label for label, slug in self.chatgpt_model_names.items()
                      if slug == selected), choices[0])
        self.model_var.set(label)

    def _select_chatgpt_model(self, name: str):
        if not self.chatgpt:
            return
        selected = self.chatgpt_model_names.get(name)
        if selected:
            try:
                self.chatgpt.choose_model(selected)
            except ChatGPTError as exc:
                self.status_var.set(str(exc))

    def _load_chatgpt_models(self):
        if not self.chatgpt or not self.chatgpt.session()["sharing"]:
            return
        if getattr(self, "_chatgpt_models_loading", False):
            return
        self._chatgpt_models_loading = True
        def work():
            try:
                models = self.chatgpt.models()
                self._dispatch_ui( lambda: self._show_chatgpt_models(models))
            except Exception as exc:
                msg = str(exc)
                self._dispatch_ui( lambda: self.status_var.set(
                    "Could not load ChatGPT models: " + msg[:100]))
            finally:
                self._dispatch_ui( lambda: setattr(self, "_chatgpt_models_loading", False))
        threading.Thread(target=work, daemon=True).start()

    def _switch_chatgpt_account(self, identity: str, dialog):
        dialog.destroy()
        try:
            session = self.chatgpt.select(identity)
            self.provider_var.set("ChatGPT plan" if session["sharing"] else "Offline")
            self.consent_var.set(session["sharing"])
            self._show_chatgpt_models([])
            self._sync_chatgpt_ui()
            if session["sharing"]:
                self._load_chatgpt_models()
                self.status_var.set("Selected ChatGPT account: " + session["email"])
            else:
                self.connect_chatgpt(profile_id=identity)
        except ChatGPTError as exc:
            self._error(str(exc))

    def _sign_out_chatgpt(self, dialog):
        dialog.destroy()
        self.chatgpt_button.configure(state="disabled")
        self.chatgpt_status_var.set("Disconnecting…")
        def work():
            try:
                confirmed = self.chatgpt.sign_out()
                self._dispatch_ui( lambda: self._chatgpt_signed_out(confirmed))
            except Exception as exc:
                msg = str(exc)
                self._dispatch_ui( lambda: self._chatgpt_connect_error(msg))
        threading.Thread(target=work, daemon=True).start()

    def _chatgpt_signed_out(self, remote_confirmed: bool):
        self.provider_var.set("Offline")
        self.consent_var.set(False)
        self._show_chatgpt_models([])
        self._sync_chatgpt_ui()
        self.status_var.set("ChatGPT disconnected; offline PDF processing remains available.")
        if not remote_confirmed:
            messagebox.showwarning(
                "Local sign-out complete",
                "Local tokens were cleared, but remote revocation could not be confirmed.\n"
                "Disconnect PDFManipulator in ChatGPT Settings to revoke app access.",
                parent=self)

    def _manage_chatgpt_accounts(self):
        if not self.chatgpt:
            return
        session = self.chatgpt.session()
        dialog = ctk.CTkToplevel(self)
        dialog.title("ChatGPT connection")
        dialog.geometry("450x460")
        dialog.minsize(415, 345)
        dialog.transient(self)
        dialog.grab_set()
        frame = ctk.CTkScrollableFrame(dialog, fg_color=SURFACE)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(frame, text="ChatGPT accounts", font=F(19, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=13, pady=(13, 5))
        ctk.CTkLabel(frame,
                     text="Plan usage requires the permission you approve in ChatGPT.",
                     font=F(12), text_color=MUTED, wraplength=355,
                     justify="left").pack(anchor="w", padx=13, pady=(0, 13))
        for profile in session["profiles"]:
            line = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=8)
            line.pack(fill="x", padx=10, pady=4)
            caption = profile["email"] or "ChatGPT account"
            if session["id"] == profile["id"]:
                caption += "  ·  Current"
            ctk.CTkLabel(line, text=caption[:45], font=F(12),
                         text_color=TEXT).pack(side="left", padx=10, pady=10)
            ctk.CTkButton(line, text="Select", width=72, fg_color=BTN,
                          text_color=TEXT, command=lambda p=profile["id"]:
                          self._switch_chatgpt_account(p, dialog)).pack(side="right", padx=8)
        ctk.CTkButton(frame, text="Continue / reconnect with ChatGPT",
                      height=36, font=F(12), fg_color=ACCENT,
                      command=lambda: (dialog.destroy(),
                                       self.connect_chatgpt())).pack(
                                           fill="x", padx=12, pady=(18, 5))
        ctk.CTkButton(frame, text="Add another ChatGPT account",
                      height=34, font=F(12), fg_color=BTN, text_color=TEXT,
                      command=lambda: (dialog.destroy(),
                                       self.connect_chatgpt(new_account=True))).pack(
                                           fill="x", padx=12, pady=5)
        ctk.CTkButton(frame, text="Manage plan usage in ChatGPT",
                      height=33, font=F(12), fg_color=BTN, text_color=TEXT,
                      command=lambda: webbrowser.open(USAGE_URL)).pack(
                                           fill="x", padx=12, pady=5)
        if session["connected"]:
            ctk.CTkButton(frame, text="Sign out of this app",
                          height=34, font=F(12), fg_color=BTN, text_color=TEXT,
                          command=lambda: self._sign_out_chatgpt(dialog)).pack(
                                               fill="x", padx=12, pady=(5, 14))

    def _clear_children(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def _source_mode_step(self, mode: str) -> dict:
        aliases = list(self.sources) or ["input1"]
        if mode == "PDF 1 only":
            return {"op": "load", "source": aliases[0]}
        if mode == "Edit PDFs separately":
            return {"op": "load_each", "sources": aliases}
        if mode == "Merge original PDFs now":
            if len(aliases) < 2:
                raise WorkflowError("Add at least two PDFs to merge them.")
            return {"op": "merge", "sources": aliases}
        if mode == "Duplex scan pair":
            if len(aliases) < 2:
                raise WorkflowError("Duplex scanning requires front and back PDFs.")
            return {"op": "duplex", "fronts": aliases[0], "backs": aliases[1],
                    "reverse_backs": True, "rotate_backs": False}
        raise WorkflowError(f"Unknown input mode: {mode}")

    def change_start_mode(self, mode: str):
        old = self.steps[0]["op"]
        old_mode = next((label for label, op in START_MODES.items() if op == old),
                        "PDF 1 only")
        try:
            new_base = self._source_mode_step(mode)
        except WorkflowError as exc:
            self.start_mode_var.set(old_mode)
            self._error(str(exc))
            return
        if self.steps[0] == new_base:
            return
        if len(self.steps) > 1 and not messagebox.askyesno(
            "Change starting PDFs",
            "Changing the starting PDFs resets the later steps because their "
            "page numbers and targets may change.\n\nReset those steps?",
            parent=self
        ):
            self.start_mode_var.set(old_mode)
            return
        self.workflow_name = "Untitled workflow"
        self.selected_recipe_name = None
        self.active_document = 0
        self.selected_page = None
        self.page_offset = 0
        self.set_steps([new_base])
        self.status_var.set(
            "Starting inputs changed. Add page edits, then Merge edited PDFs "
            "when you are ready to combine them.")

    def _populate_presets(self):
        self._clear_children(self.preset_frame)
        labels = {
            "Duplex Scan Merger": "Duplex scans",
            "Split Every N Pages": "Split PDF",
            "Custom Page Splitter": "Custom splits",
            "PDF Merger": "Merge originals now",
            "Extract Selected Pages": "Extract pages",
            "Reverse Page Order": "Reverse pages",
            "Rotate Scanned Pages": "Rotate pages",
            "Remove Blank Pages": "Remove blanks",
            "Batch PDF Organizer": "Batch organizer",
        }
        for name in PRESETS:
            selected = self.workflow_name == name
            ctk.CTkButton(self.preset_frame, text=labels.get(name, name),
                          anchor="w", fg_color=BTN if selected else "transparent",
                          text_color=TEXT if selected else MUTED,
                          hover_color=CARD, corner_radius=8, height=35,
                          font=F(12, "bold" if selected else "normal"),
                          command=lambda n=name: self.load_recipe(preset(n), confirm=True)).pack(
                              fill="x", pady=1)

    def _populate_recipes(self):
        self._clear_children(self.recipe_frame)
        if not self.recipes:
            ctk.CTkLabel(self.recipe_frame, text="No saved workflows",
                         font=F(11), text_color=MUTED).pack(anchor="w", padx=5, pady=8)
        for name in self.recipes:
            selected = self.selected_recipe_name == name
            ctk.CTkButton(self.recipe_frame, text=name, anchor="w",
                          fg_color=BTN if selected else "transparent",
                          text_color=TEXT, hover_color=CARD, height=31,
                          font=F(12), command=lambda n=name: self.select_recipe(n)).pack(
                              fill="x", pady=2)

    def select_recipe(self, name):
        self.load_recipe(self.recipes[name], confirm=True)

    def duplicate_recipe(self):
        name = self.selected_recipe_name
        if not name or name not in self.recipes:
            self.status_var.set("Select a saved workflow first.")
            return
        copy_name = ctk.CTkInputDialog(title="Duplicate workflow", text="Name for this copy:").get_input()
        if not copy_name:
            return
        try:
            recipe = deepcopy(self.recipes[name])
            recipe["name"] = copy_name
            recipe = validate_recipe(recipe)
            if recipe["name"] in self.recipes:
                raise WorkflowError("A saved workflow with this name already exists.")
            self.recipes[recipe["name"]] = recipe
            save_recipes(self.recipes)
            self._populate_recipes()
            self.select_recipe(recipe["name"])
        except WorkflowError as exc:
            self._error(str(exc))

    def delete_recipe(self):
        name = self.selected_recipe_name
        if not name or name not in self.recipes:
            self.status_var.set("Select a saved workflow first.")
            return
        if messagebox.askyesno("Delete saved workflow", f"Delete '{name}' from saved workflows?\nPDF files will not be touched.", parent=self):
            updated = dict(self.recipes)
            updated.pop(name)
            try:
                save_recipes(updated)
                self.recipes = updated
                self.selected_recipe_name = None
                self._populate_recipes()
            except WorkflowError as exc:
                self._error(str(exc))

    def export_selected_recipe(self):
        name = self.selected_recipe_name
        if not name or name not in self.recipes:
            self.status_var.set("Select a saved workflow first.")
            return
        path = filedialog.asksaveasfilename(title="Export workflow recipe", defaultextension=".json",
                                            initialfile=name + ".json", filetypes=[("JSON recipe", "*.json")])
        if not path:
            return
        try:
            export_recipe(self.recipes[name], Path(path))
            self.status_var.set(f"Exported '{name}'.")
        except FileExistsError:
            self._error("Export file already exists. Choose a new filename.")
        except WorkflowError as exc:
            self._error(str(exc))

    def _populate_sources(self):
        self._clear_children(self.sources_frame)
        if not self.sources:
            ctk.CTkLabel(self.sources_frame, text="No files selected.",
                         text_color=MUTED, font=F(12)).pack(anchor="w", pady=5)
        for alias, path in self.sources.items():
            line = ctk.CTkFrame(self.sources_frame, fg_color=CARD, corner_radius=8)
            line.pack(fill="x", pady=3)
            ctk.CTkLabel(line, text=alias.replace("input", ""), text_color=ACCENT,
                         width=24, font=F(12, "bold")).pack(side="left", padx=(9, 5))
            ctk.CTkLabel(line, text=path.name[:24], text_color=TEXT,
                         font=F(12), anchor="w").pack(side="left", fill="x", expand=True,
                                                      pady=9)
            ctk.CTkButton(line, text="×", width=25, height=25, fg_color="transparent",
                          hover_color=BORDER, text_color=MUTED, font=F(14),
                          command=lambda a=alias: self.remove_file(a)).pack(
                              side="right", padx=6)

    def _populate_steps(self):
        self._clear_children(self.step_frame)
        self.workflow_label.configure(text=self.workflow_name)
        current_mode = next((label for label, op in START_MODES.items()
                             if self.steps and self.steps[0]["op"] == op), None)
        if current_mode:
            self.start_mode_var.set(current_mode)
        self._populate_presets()
        for i, step in enumerate(self.steps):
            item = ctk.CTkFrame(self.step_frame, fg_color=CARD, corner_radius=9)
            item.pack(fill="x", pady=4)
            top = ctk.CTkFrame(item, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(10, 3))
            ctk.CTkLabel(top, text=f"{i+1:02d}", text_color=ACCENT,
                         width=24, font=F(12, "bold")).pack(side="left", padx=(0, 6))
            step_title = {
                "load": "Start · PDF 1",
                "load_each": "Start · PDFs separately",
                "merge": "Start · Merge originals",
                "duplex": "Start · Duplex scans",
                "merge_documents": "Merge edited PDFs",
            }.get(step["op"], step["op"].replace("_", " ").title())
            ctk.CTkLabel(top, text=step_title,
                         text_color=TEXT, font=F(12, "bold"),
                         anchor="w").pack(side="left", fill="x", expand=True)
            if i > 0:
                ctk.CTkButton(top, text="Edit", fg_color=BTN, text_color=TEXT,
                              font=F(11), width=42, height=25,
                              command=lambda j=i: StepDialog(self, j)).pack(side="right")
            details = describe(step)
            if "document" in step:
                doc_number = step["document"] + 1
                name = list(self.sources.values())[step["document"]].name if (
                    step["document"] < len(self.sources) and self.steps[0]["op"] == "load_each") else ""
                details += f"\nApplies to PDF {doc_number}" + (f" — {name}" if name else "")
            elif i > 0 and step["op"] in DOCUMENT_ACTIONS:
                details += "\nApplies to all current PDF outputs"
            ctk.CTkLabel(item, text=details, text_color=MUTED,
                         wraplength=330, font=F(11), justify="left").pack(
                             fill="x", anchor="w", padx=13, pady=(0, 7))
            if i > 0:
                controls = ctk.CTkFrame(item, fg_color="transparent")
                controls.pack(anchor="w", padx=12, pady=(0, 8))
                for icon, callback in (("↑", lambda j=i: self.move_step(j, -1)),
                                       ("↓", lambda j=i: self.move_step(j, 1)),
                                       ("Remove", lambda j=i: self.remove_step(j))):
                    ctk.CTkButton(controls, text=icon, width=59 if icon == "Remove" else 26,
                                  height=23, fg_color=BTN, text_color=MUTED,
                                  font=F(10), command=callback).pack(
                                      side="left", padx=(0, 5))

    def _setup_drop(self):
        try:
            TkinterDnD._require(self)
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.status_var.set("Drag PDF files into the window, or click Add PDF files.")
        except Exception:
            self.status_var.set("Use Add PDF files to select documents.")

    def _on_drop(self, event):
        self.add_files([p for p in self.tk.splitlist(event.data) if p.lower().endswith(".pdf")])
        return "copy"

    def _bind_shortcuts(self):
        self.bind_all("<Control-o>", lambda _: self.browse_files())
        self.bind_all("<Control-s>", lambda _: self.save_recipe())
        self.bind_all("<Control-z>", lambda _: self.undo())
        self.bind_all("<Control-y>", lambda _: self.redo())

    def _refresh_suggestions(self):
        if not hasattr(self, "examples_frame"):
            return
        self._clear_children(self.examples_frame)
        if len(self.sources) >= 2:
            suggestions = [("Duplex scans", EXAMPLES[2]), ("Merge documents", EXAMPLES[1])]
        else:
            suggestions = [("Split every 3 pages", EXAMPLES[0]), ("Rotate even pages", EXAMPLES[3])]
        for label, prompt in suggestions:
            ctk.CTkButton(self.examples_frame, text=label, fg_color=BTN,
                          text_color=TEXT, hover_color=CARD, font=F(11),
                          height=29, width=142, corner_radius=7,
                          command=lambda value=prompt: self.use_prompt(value)).pack(
                              side="left", padx=(0, 7))

    def use_prompt(self, value: str):
        self.prompt.delete("1.0", "end")
        self.prompt.insert("1.0", value)
        self.prompt.focus_set()

    def browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose PDFs to import", filetypes=[("PDF documents", "*.pdf")],
            parent=self)
        if paths:
            self.add_files(paths)

    def _update_import_banner(self):
        if not self.sources:
            self.files_summary_var.set("No PDFs imported yet — use + Add PDFs.")
            return
        names = [f"{alias}: {path.name}" for alias, path in self.sources.items()]
        summary = f"{len(names)} PDF{'s' if len(names) != 1 else ''} imported  |  "
        summary += "  •  ".join(names[:4])
        if len(names) > 4:
            summary += f"  •  +{len(names)-4} more"
        if (len(self.sources) > 1 and self.steps
                and self.steps[0].get("op") == "load_each"
                and not any(step.get("op") == "merge_documents" for step in self.steps)):
            summary += "  |  PDFs are separate: edit PDF 1/PDF 2, then Merge edited PDFs."
        elif (len(self.sources) > 1 and self.steps
                and self.steps[0].get("op") == "load"
                and not any(step.get("op") == "insert_pdf" for step in self.steps)):
            summary += "  |  Only PDF 1 is active. Choose another Start with mode."
        self.files_summary_var.set(summary)

    def add_files(self, paths):
        existing = {p.resolve() for p in self.sources.values()}
        imported = []
        skipped = []
        for raw in paths:
            path = Path(raw).expanduser().resolve()
            if path.suffix.lower() != ".pdf" or not path.is_file():
                skipped.append(path.name)
                continue
            if path in existing:
                skipped.append(path.name + " (already added)")
                continue
            # PDF validation also occurs during preview/compilation.
            # Reject clearly invalid inputs immediately, so import is not
            # mistaken for success when the file is unreadable.
            try:
                from .engine import _reader
                _reader(path)
            except (WorkflowError, OSError) as exc:
                skipped.append(f"{path.name} (unreadable PDF)")
                continue
            alias = f"input{len(self.sources) + 1}"
            self.sources[alias] = path
            imported.append(f"{alias}: {path.name}")
            existing.add(path)
        if imported and self.steps:
            first = self.steps[0]
            if (self.workflow_name == "Untitled workflow" and len(self.steps) == 1
                    and first["op"] in ("load", "load_each")):
                # A manual workflow starts with each PDF independently, preventing
                # unintended deletions from an already merged document.
                self.steps = [{"op": "load_each", "sources": list(self.sources)}] \
                    if len(self.sources) > 1 else [{"op": "load", "source": "input1"}]
                self._populate_steps()
            elif first["op"] == "load_each":
                self.steps[0] = {"op": "load_each", "sources": list(self.sources)}
                self._populate_steps()
        self._populate_sources()
        self._refresh_suggestions()
        self._update_import_banner()
        self.preview()
        if imported:
            self.status_var.set(
                f"Imported {len(imported)} PDF(s): " + ", ".join(imported[:2]) +
                (f" (+{len(imported)-2} more)" if len(imported) > 2 else ""))
        if skipped:
            self.status_var.set(
                f"Imported {len(imported)} PDF(s). Skipped {len(skipped)} file(s)."
                if imported else "No new PDFs imported.")
            messagebox.showwarning(
                "PDF import",
                "Some selections were not added:\n" + "\n".join(skipped[:8]) +
                ("\n…" if len(skipped) > 8 else ""),
                parent=self)

    def remove_file(self, alias):
        self.sources = {f"input{i}": path for i, path in enumerate(
            (p for k, p in self.sources.items() if k != alias), 1)}
        if self.sources:
            try:
                compile_workflow(self.steps, self.sources)
            except WorkflowError:
                self.steps = [{"op": "load", "source": "input1"}]
                self._populate_steps()
        self.selected_page = None
        self._populate_sources()
        self._refresh_suggestions()
        self._update_import_banner()
        self.preview()
        self.status_var.set(f"Removed {alias} from the current workflow. Original PDFs were not changed.")

    def clear_files(self):
        if not self.sources:
            return
        self.sources.clear()
        self.compiled = None
        self.steps = [{"op": "load", "source": "input1"}]
        self.selected_page = None
        self.active_document = 0
        self.page_offset = 0
        self._populate_sources()
        self._populate_steps()
        self._refresh_suggestions()
        self._update_import_banner()
        self.preview()
        self.status_var.set("Cleared imported PDFs. Files on disk are unchanged.")

    def set_steps(self, steps: list[dict]):
        try:
            validated = validate_steps(steps)
        except WorkflowError as exc:
            messagebox.showerror("Invalid workflow", str(exc), parent=self)
            return
        self.undo_stack.append(deepcopy(self.steps))
        self.undo_stack = self.undo_stack[-50:]
        self.redo_stack.clear()
        self.steps = validated
        self._populate_steps()
        self._update_import_banner()
        self.preview()

    def load_recipe(self, recipe, *, confirm: bool = False):
        if confirm and (len(self.steps) > 1 or self.selected_recipe_name):
            if not messagebox.askyesno(
                "Replace current workflow",
                "Open this template or saved workflow? Your current unsaved "
                "steps will be replaced; imported PDFs will remain available.",
                parent=self):
                return
        try:
            checked = validate_recipe(recipe)
            if checked["name"] in ("PDF Merger", "Batch PDF Organizer") and len(self.sources) > 1:
                checked["steps"][0]["sources"] = list(self.sources)
            self.workflow_name = checked["name"]
            self.selected_recipe_name = checked["name"] if checked["name"] in self.recipes else None
            self.status_var.set(f"Selected workflow: {self.workflow_name}")
            self.filename_pattern.set(checked["pattern"])
            self.set_steps(checked["steps"])
            self._update_import_banner()
        except WorkflowError as exc:
            messagebox.showerror("Invalid recipe", str(exc), parent=self)

    def new_workflow(self):
        """Start a fresh workflow instead of overwriting an existing recipe."""
        if self.sources or self.selected_recipe_name or len(self.steps) > 1:
            if not messagebox.askyesno(
                "New workflow",
                "Start a new workflow? This clears the current inputs and unsaved steps.\n"
                "Saved workflows and your original PDF files stay unchanged.",
                parent=self
            ):
                return
        self.sources.clear()
        self.steps = [{"op": "load", "source": "input1"}]
        self.workflow_name = "Untitled workflow"
        self.selected_recipe_name = None
        self.filename_pattern.set("{source}_{index:02d}")
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.compiled = None
        self.selected_page = None
        self.active_document = 0
        self.page_offset = 0
        self.zoom_scale = 1.0
        self.zoom_var.set("100%")
        self.prompt.delete("1.0", "end")
        self._populate_sources()
        self._populate_steps()
        self._refresh_suggestions()
        self._update_import_banner()
        self.preview()
        self.status_var.set("New workflow created. Add PDF files or choose a quick action.")

    def add_step(self, operation: str | None = None, *, open_editor: bool = True):
        """Append a manually configured operation to the currently visible plan."""
        op = operation or STEP_OPTIONS[self.add_op.get()]
        if not self.sources:
            self._error("Import your PDFs first, then choose an operation.")
            return
        if op == "merge_documents":
            if not self.compiled or len(self.compiled.documents) < 2:
                self._error(
                    "To merge PDFs after editing them, choose 'Edit PDFs separately' "
                    "under Start with, then add your page edits first.")
                return
            step = {"op": op, "order": list(range(1, len(self.compiled.documents) + 1))}
        else:
            if op == "insert_pdf" and len(self.sources) < 2:
                self._error("Import another PDF before inserting one.")
                return
            step = {"op": op, **deepcopy(OP_DEFAULTS[op])}
            if op == "insert_pdf":
                step["source"] = list(self.sources)[1]
                step["position"] = 1
            if op in DOCUMENT_ACTIONS and self.compiled:
                # Explicitly bind each edit to the currently selected output,
                # not an accidentally merged document.
                if len(self.compiled.documents) > 1:
                    step["document"] = self.active_document
                if op == "reorder":
                    step["order"] = list(
                        range(1, len(self.compiled.documents[self.active_document].pages) + 1))
                if op in ("delete", "extract", "duplicate") and self.selected_page is not None:
                    step["pages"] = str(self.selected_page + 1)
        old_count = len(self.steps)
        self.set_steps(self.steps + [step])
        if len(self.steps) != old_count + 1:
            return
        self.status_var.set(f"Added step {len(self.steps)}: {op.replace('_', ' ')}. "
                            "Use Edit to adjust the selected PDF and page numbers.")
        if open_editor and op in DOCUMENT_ACTIONS:
            self.after(75, lambda index=old_count: StepDialog(self, index))

    def move_step(self, index, delta):
        dest = index + delta
        if index == 0 or dest < 1 or dest >= len(self.steps):
            return
        new = deepcopy(self.steps)
        new[index], new[dest] = new[dest], new[index]
        self.set_steps(new)

    def remove_step(self, index):
        if index == 0:
            messagebox.showinfo("Input step", "The first step loads your source files and cannot be removed.", parent=self)
        elif len(self.steps) > 1:
            self.set_steps(self.steps[:index] + self.steps[index + 1:])

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(deepcopy(self.steps))
            self.steps = self.undo_stack.pop()
            self._populate_steps()
            self.preview()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(deepcopy(self.steps))
            self.steps = self.redo_stack.pop()
            self._populate_steps()
            self.preview()

    def edit_json(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Advanced workflow editor")
        dialog.geometry("590x530")
        dialog.transient(self)
        dialog.grab_set()
        editor = ctk.CTkTextbox(dialog, wrap="none", font=F(12))
        editor.pack(fill="both", expand=True, padx=15, pady=15)
        editor.insert("1.0", json.dumps(self.steps, indent=2))
        def commit():
            try:
                value = json.loads(editor.get("1.0", "end"))
                new = validate_steps(value)
                self.set_steps(new)
                dialog.destroy()
            except (ValueError, WorkflowError) as exc:
                messagebox.showerror("Invalid workflow", str(exc), parent=dialog)
        ctk.CTkButton(dialog, text="Validate and apply", font=F(13), command=commit).pack(pady=(0, 15))

    def interpret_prompt(self):
        prompt = self.prompt.get("1.0", "end").strip()
        mode = self.provider_var.get()
        aliases = list(self.sources) or ["input1"]
        consent = mode == "Offline" or self.consent_var.get()
        self.status_var.set("Interpreting instructions…")
        self._set_busy(True)
        def work():
            try:
                if mode == "ChatGPT plan":
                    if not self.chatgpt:
                        raise ChatGPTError(self.chatgpt_init_error or "ChatGPT is unavailable.")
                    steps = self.chatgpt.interpret(prompt, aliases, consent=consent)
                else:
                    provider = {"Offline": "offline", "Ollama (local)": "ollama",
                                "OpenAI API": "openai", "Claude API": "anthropic"}[mode]
                    steps = translate(prompt, aliases, provider, consent=consent)
                self._dispatch_ui( lambda: self._interpreted(steps))
            except Exception as exc:
                message = str(exc)
                self._dispatch_ui( lambda: self._error(message))
            finally:
                self._dispatch_ui( lambda: self._set_busy(False))
        threading.Thread(target=work, daemon=True).start()

    def _interpreted(self, steps):
        self.workflow_name = "Custom instructions"
        self.set_steps(steps)
        self.status_var.set("Workflow interpreted. Review the steps and preview before saving.")

    def _error(self, detail):
        self.status_var.set(detail.splitlines()[0][:120])
        messagebox.showerror("PDFManipulator", detail, parent=self)

    def preview(self):
        if not self.sources:
            self.compiled = None
            self.preview_label.configure(text="Add PDF files to preview your changes.")
            self.outputs_label.configure(text="No output yet.")
            self._clear_children(self.output_tabs)
            self._clear_children(self.page_list)
            self._clear_children(self.before_strip)
            return
        try:
            compiled = compile_workflow(self.steps, self.sources)
            names = output_names(compiled, self.filename_pattern.get())
            self.compiled = compiled
            self.active_document = min(self.active_document, len(compiled.documents) - 1)
            self.page_offset = min(self.page_offset, max(0, len(compiled.documents[self.active_document].pages) - 1))
            self.outputs_label.configure(text="\n".join(
                f"{name} · {len(doc.pages)}p" for name, doc in zip(names[:5], compiled.documents[:5])) +
                (f"\n… and {len(names)-5} more" if len(names) > 5 else ""))
            self.preview_label.configure(text=f"{len(self.sources)} input(s)  →  {len(compiled.documents)} output(s)  ·  {compiled.page_count} page(s)")
            self._render_tabs()
            if self.compare_visible:
                self._render_before()
            self._render_pages()
            if compiled.warnings:
                self.status_var.set(" ".join(compiled.warnings)[:200])
            else:
                self.status_var.set("Preview is ready. Drag page thumbnails to reorder; originals stay untouched.")
        except WorkflowError as exc:
            self.compiled = None
            self.preview_label.configure(text=f"Preview: {str(exc).splitlines()[0]}")
            self.outputs_label.configure(text="Fix the workflow or add the missing input.")
            self._clear_children(self.output_tabs)
            self._clear_children(self.page_list)
            self._clear_children(self.before_strip)
            self.status_var.set(str(exc).splitlines()[0][:130])

    def _render_before(self):
        """Show a compact source thumbnail strip above output page thumbnails."""
        self._clear_children(self.before_strip)
        self.before_image_refs.clear()
        ctk.CTkLabel(self.before_strip, text="Original pages", text_color=MUTED,
                     font=F(11, "bold")).pack(side="left", padx=9)
        if not self.compiled:
            return
        from .engine import PageRef
        shown = 0
        for alias, path in list(self.sources.items())[:3]:
            try:
                from pypdf import PdfReader
                limit = min(2, len(PdfReader(str(path)).pages))
                for index in range(limit):
                    img = image_for(PageRef(alias, index), self.compiled.sources, 65)
                    ratio = min(1.0, 95 / max(1, img.height))
                    visual = ctk.CTkImage(light_image=img, dark_image=img,
                                          size=(max(1, int(img.width*ratio)), max(1, int(img.height*ratio))))
                    self.before_image_refs.append(visual)
                    ctk.CTkLabel(self.before_strip, text="", image=visual, height=97,
                                 width=70).pack(side="left", padx=4, pady=4)
                    shown += 1
            except Exception:
                ctk.CTkLabel(self.before_strip, text=f"{alias}\npreview unavailable",
                             text_color=MUTED).pack(side="left", padx=5)
        if not shown:
            ctk.CTkLabel(self.before_strip, text="No source thumbnails", text_color=MUTED).pack(side="left")

    def _render_tabs(self):
        self._clear_children(self.output_tabs)
        if not self.compiled:
            return
        for i, doc in enumerate(self.compiled.documents[:120]):
            ctk.CTkButton(self.output_tabs, text=f"Output {i+1} ({len(doc.pages)}p)",
                          height=31, width=122, fg_color=ACCENT if i == self.active_document else BTN,
                          text_color="#ffffff" if i == self.active_document else TEXT,
                          font=F(12),
                          command=lambda j=i: self.select_document(j)).pack(side="left", padx=3)
        if len(self.compiled.documents) > 120:
            ctk.CTkLabel(self.output_tabs, text="First 120 outputs shown").pack(side="left")

    def select_document(self, index):
        self.active_document = index
        self.page_offset = 0
        self.selected_page = None
        self._render_tabs()
        self._render_pages()

    def change_zoom(self, delta):
        self.zoom_scale = max(0.6, min(2.6, round(self.zoom_scale + delta, 2)))
        self.zoom_var.set(f"{round(self.zoom_scale * 100)}%")
        self._render_pages()

    def _on_preview_resize(self, event):
        if event.width < 200 or not self.compiled:
            return
        last = getattr(self, "_preview_render_width", 0)
        if abs(event.width - last) < 20:
            return
        self._preview_render_width = event.width
        if self._page_resize_job is not None:
            self.after_cancel(self._page_resize_job)
        self._page_resize_job = self.after(120, self._render_pages)

    def _render_pages(self):
        self._page_resize_job = None
        self._clear_children(self.page_list)
        self.image_refs.clear()
        if not self.compiled:
            return
        pages = self.compiled.documents[self.active_document].pages
        end = min(len(pages), self.page_offset + 12)
        self.page_count_label.configure(text=f"{self.page_offset + 1}–{end} of {len(pages)}")
        self.prev_btn.configure(state="normal" if self.page_offset else "disabled")
        self.next_btn.configure(state="normal" if end < len(pages) else "disabled")
        if not pages:
            return
        usable = self.page_list.winfo_width()
        if usable < 200:
            usable = max(430, self.mainpane.winfo_width() - 82)
        cols, thumb_w, thumb_h = thumbnail_layout(max(360, usable - 24), self.zoom_scale)
        # Reset old layout columns when zooming in (six -> five -> four ...).
        for col in range(9):
            self.page_list.grid_columnconfigure(col, weight=1 if col < cols else 0, minsize=0)
        for i in range(self.page_offset, end):
            ref = pages[i]
            card = ctk.CTkFrame(
                self.page_list, fg_color=SURFACE, corner_radius=9,
                border_width=2 if self.selected_page == i else 1,
                border_color=ACCENT if self.selected_page == i else BORDER)
            card.grid(row=(i - self.page_offset) // cols,
                      column=(i - self.page_offset) % cols, sticky="n",
                      padx=4, pady=8)
            card.page_index = i
            try:
                img = image_for(ref, self.compiled.sources, max(thumb_w, 72))
                ratio = min(thumb_w / max(1, img.width),
                            thumb_h / max(1, img.height))
                size = (max(1, int(img.width * ratio)),
                        max(1, int(img.height * ratio)))
                visual = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                self.image_refs.append(visual)
                thumb = ctk.CTkLabel(card, text="", image=visual,
                                     height=thumb_h, width=thumb_w)
            except Exception:
                thumb = ctk.CTkLabel(card, text="Preview unavailable",
                                     height=thumb_h, width=thumb_w,
                                     text_color=MUTED, font=F(10))
            thumb.pack(padx=5, pady=(7, 2))
            thumb.page_index = i
            label = ctk.CTkLabel(
                card, text=f"Page {i+1}  ·  {ref.source} #{ref.index+1}",
                text_color=MUTED, font=F(10), width=thumb_w,
                wraplength=thumb_w, height=25)
            label.pack(padx=3, pady=(0, 6))
            label.page_index = i
            for widget in (card, thumb, label):
                widget.bind("<ButtonPress-1>", lambda _event, p=i: self._start_drag(p))
                widget.bind("<ButtonRelease-1>", self._end_drag)

    def _start_drag(self, number):
        self.drag_page = number
        self.selected_page = number
        # Do not repaint here; it would destroy the widget during a drag.

    def _end_drag(self, event):
        origin = self.drag_page
        self.drag_page = None
        if origin is None or not self.compiled:
            return
        target_widget = self.winfo_containing(event.x_root, event.y_root)
        while target_widget is not None and not hasattr(target_widget, "page_index"):
            target_widget = getattr(target_widget, "master", None)
        dest = getattr(target_widget, "page_index", origin)
        if dest != origin:
            count = len(self.compiled.documents[self.active_document].pages)
            order = list(range(1, count+1))
            moving = order.pop(origin)
            order.insert(dest, moving)
            self.set_steps(self.steps + [{"op": "reorder", "order": order, "document": self.active_document}])
        else:
            self.status_var.set(
                f"Selected output page {origin + 1}. Use Delete page or Rotate, "
                "or drag onto another page to reorder.")
            self._render_pages()

    def change_page_offset(self, count):
        if self.compiled:
            max_start = max(0, len(self.compiled.documents[self.active_document].pages) - 1)
            self.page_offset = max(0, min(max_start, self.page_offset + count))
            self._render_pages()

    def rotate_selected_page(self):
        if self.selected_page is not None and self.compiled:
            self.set_steps(self.steps + [{"op": "rotate", "pages": str(self.selected_page+1),
                                           "degrees": 90, "document": self.active_document}])
        else:
            self.status_var.set("Select a page thumbnail first.")

    def delete_selected_page(self):
        if self.selected_page is None or not self.compiled:
            self.status_var.set("Click a page thumbnail to select it, then choose Delete page.")
            return
        pages = self.compiled.documents[self.active_document].pages
        if len(pages) <= 1:
            self._error("Cannot delete the last page of a PDF. A saved output cannot be empty.")
            return
        number = self.selected_page + 1
        self.selected_page = None
        self.set_steps(self.steps + [{"op": "delete", "pages": str(number),
                                     "document": self.active_document}])
        if self.compiled:
            self.page_offset = max(0, min(self.page_offset, len(pages) - 2))
            self.status_var.set(f"Deleted output page {number} in the preview. "
                                "Click Save as PDF to create the edited file.")

    def save_recipe(self):
        name = ctk.CTkInputDialog(title="Save reusable workflow", text="Workflow name:").get_input()
        if not name:
            return
        try:
            checked = validate_recipe({"name": name, "steps": self.steps,
                                       "pattern": self.filename_pattern.get()})
            self.recipes[checked["name"]] = checked
            save_recipes(self.recipes)
            self.selected_recipe_name = checked["name"]
            self.workflow_name = checked["name"]
            self._populate_recipes()
            self._populate_steps()
            self.status_var.set(f"Saved workflow '{name}'.")
        except WorkflowError as exc:
            self._error(str(exc))

    def import_recipe(self):
        path = filedialog.askopenfilename(filetypes=[("Recipe JSON", "*.json")])
        if path:
            try:
                recipe = import_recipe(Path(path))
                self.recipes[recipe["name"]] = recipe
                save_recipes(self.recipes)
                self._populate_recipes()
                self.load_recipe(recipe)
            except WorkflowError as exc:
                self._error(str(exc))

    def _set_busy(self, value):
        self.busy = value
        self.run_button.configure(state="disabled" if value else "normal")
        self.stop_button.configure(state="normal" if value else "disabled")

    def run(self):
        """Save As for one output, or choose a folder for multiple outputs."""
        if self.busy:
            return
        self.preview()
        if not self.compiled:
            self._error("The output preview is not valid. Fix its error before saving.")
            return
        compilation = self.compiled
        try:
            initial_names = output_names(compilation, self.filename_pattern.get())
            if len(compilation.documents) == 1:
                # An actual filename picker is essential for single-PDF workflows.
                # Never overwrite an existing file or an imported source.
                while True:
                    selected = filedialog.asksaveasfilename(
                        title="Save edited PDF as",
                        defaultextension=".pdf", initialfile=initial_names[0],
                        filetypes=[("PDF document", "*.pdf")],
                        parent=self)
                    if not selected:
                        self.status_var.set("Save canceled. No PDF was changed.")
                        return
                    target = Path(selected).expanduser().resolve()
                    if target.suffix.lower() != ".pdf":
                        messagebox.showwarning(
                            "PDF filename", "Save the output using a .pdf filename.",
                            parent=self)
                        continue
                    if target.exists() or target in compilation.sources.values():
                        messagebox.showwarning(
                            "Choose another filename",
                            "This filename already exists or is one of your original PDFs.\n"
                            "Choose a new filename; PDFManipulator never overwrites files.",
                            parent=self)
                        continue
                    pattern = target.stem.replace("{", "{{").replace("}", "}}")
                    names = output_names(compilation, pattern)
                    if names != [target.name]:
                        messagebox.showwarning(
                            "Invalid filename",
                            "Choose a different PDF filename. This name cannot be used safely.",
                            parent=self)
                        continue
                    folder = target.parent
                    break
            else:
                selected = filedialog.askdirectory(
                    title="Choose where to save the output PDFs", parent=self)
                if not selected:
                    self.status_var.set("Save canceled. No PDF was changed.")
                    return
                folder = Path(selected).expanduser().resolve()
                pattern, names = next_available_pattern(
                    compilation, folder, self.filename_pattern.get())
            if not messagebox.askokcancel(
                "Confirm Save As",
                f"Save {len(names)} PDF file(s) in:\n{folder}\n\n" +
                "\n".join(names[:8]) + ("\n…" if len(names) > 8 else "") +
                "\n\nOriginal PDFs will not be changed or overwritten.",
                parent=self):
                self.status_var.set("Save canceled. No PDF was changed.")
                return
        except (WorkflowError, OSError, ValueError) as exc:
            self._error(str(exc))
            return

        self.cancel.clear()
        self._set_busy(True)
        self.progress.set(0)
        self.status_var.set(f"Saving {len(names)} PDF file(s)…")

        def update(n, total):
            self._dispatch_ui( lambda done=n, count=total:
                       self.progress.set(done / max(1, count)))

        def task():
            try:
                created = execute_workflow(
                    compilation, folder, pattern=pattern,
                    progress=update, cancel=self.cancel)
                self._dispatch_ui( lambda: self._done(created))
            except Exception as exc:
                msg = str(exc)
                self._dispatch_ui( lambda: self._error(msg))
            finally:
                self._dispatch_ui( lambda: self._set_busy(False))
        threading.Thread(target=task, daemon=True).start()

    def _done(self, paths):
        self.progress.set(1)
        self.status_var.set(f"Created {len(paths)} PDF(s) successfully.")
        messagebox.showinfo("Saved", f"Created {len(paths)} PDF(s).\n\nOutput folder:\n{paths[0].parent}", parent=self)

def main():
    app = StudioApp()
    app.mainloop()

if __name__ == "__main__":
    main()
