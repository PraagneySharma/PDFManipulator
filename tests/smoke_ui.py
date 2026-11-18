"""Noninteractive smoke test of desktop UI with real temporary PDF thumbnails."""
import tempfile
import time
from unittest.mock import patch
from pathlib import Path
from pypdf import PdfWriter, PdfReader
from pdfmanipulator.ui import StudioApp
from pdfmanipulator.recipes import preset

def make(path, numbers):
    w = PdfWriter()
    for i in numbers:
        w.add_blank_page(width=600+i, height=800)
    with open(path,"wb") as file:
        w.write(file)

def main():
    with tempfile.TemporaryDirectory() as tmp:
        one, two = Path(tmp)/"fronts.pdf", Path(tmp)/"backs.pdf"
        make(one,[1,3,5])
        make(two,[6,4,2])
        app = StudioApp()
        app.add_files([one,two])
        app.load_recipe(preset("Duplex Scan Merger"))
        app.update()
        assert app.compiled is not None, app.preview_label.cget("text")
        assert app.compiled.page_count == 6
        assert len(app.page_list.winfo_children()) > 0
        assert not app.before_image_refs  # Comparison is intentionally collapsed by default.
        app.toggle_compare()
        app.update()
        assert len(app.before_image_refs) >= 2
        app.change_zoom(0.2)
        app.toggle_inspector()
        app.update()
        assert app.inspector_visible
        assert app.inspector._parent_frame.winfo_manager() == 'grid'
        app.toggle_inspector()
        assert not app.inspector_visible
        assert not app.inspector._parent_frame.winfo_manager()
        app.toggle_ai_settings()
        assert app.ai_options.winfo_manager() == 'grid'
        assert not app.chatgpt_model_row.winfo_manager()
        app.provider_var.set("ChatGPT plan")
        app._provider_changed("ChatGPT plan")
        app.update()
        assert app.chatgpt_model_row.winfo_manager() == "pack"
        app.provider_var.set("Offline")
        app._provider_changed("Offline")
        assert not app.chatgpt_model_row.winfo_manager()
        app.toggle_ai_settings()
        assert not app.ai_options.winfo_manager()
        app.update()
        assert "2 PDFs imported" in app.files_summary_var.get()
        assert one.name in app.files_summary_var.get()
        assert two.name in app.files_summary_var.get()
        # User can merge multiple imported PDFs from the Quick action.
        app.load_recipe(preset("PDF Merger"))
        app.zoom_scale = 1.0
        app.zoom_var.set("100%")
        app.update()
        app._render_pages()
        assert app.compiled and app.compiled.page_count == 6
        cards = [child for child in app.page_list.winfo_children()
                 if hasattr(child, "page_index")]
        assert len({card.grid_info()["column"] for card in cards}) == 6, (
            "Default zoom must show six pages in one row")
        app.change_zoom(0.4)
        app.update()
        cards = [child for child in app.page_list.winfo_children()
                 if hasattr(child, "page_index")]
        assert len({card.grid_info()["column"] for card in cards}) < 6, (
            "Zooming in should show fewer columns")
        app.change_zoom(-0.4)
        # Delete page has to update the actual compiled PDF.
        app.selected_page = 0
        app.delete_selected_page()
        app.update()
        assert app.compiled and app.compiled.page_count == 5
        assert app.steps[-1] == {"op": "delete", "pages": "1", "document": 0}
        # The New workflow control resets inputs, preview, and workflow steps.
        with patch("pdfmanipulator.ui.messagebox.askyesno", return_value=True):
            app.new_workflow()
        app.update()
        assert not app.sources
        assert app.steps == [{"op": "load", "source": "input1"}]
        assert "No PDFs imported" in app.files_summary_var.get()

        # Reproduce the user's exact two-PDF instruction through the GUI.
        app.add_files([one, two])
        app.provider_var.set("Offline")
        app.use_prompt("Delete the first Page of the first PDF. "
                       "Add the second PDF to the first PDF and make sure the second PDF is page 1")
        app.interpret_prompt()
        deadline = time.monotonic() + 12
        while (len(app.steps) != 3 or app.busy) and time.monotonic() < deadline:
            app.update()
            time.sleep(0.025)
        app.update()
        assert [step["op"] for step in app.steps] == ["load", "delete", "insert_pdf"], app.steps
        assert app.compiled and app.compiled.page_count == 5
        expected = [6, 4, 2, 3, 5]
        target = Path(tmp) / "Edited and Merged.pdf"
        with patch("pdfmanipulator.ui.filedialog.asksaveasfilename",
                   return_value=str(target)) as dialog, \
             patch("pdfmanipulator.ui.messagebox.askokcancel", return_value=True), \
             patch("pdfmanipulator.ui.messagebox.showinfo"):
            app.run()
            deadline = time.monotonic() + 20
            while not target.is_file() and time.monotonic() < deadline:
                app.update()
                time.sleep(0.025)
            for _ in range(10):
                app.update()
                time.sleep(0.01)
            assert dialog.call_count == 1, "Single-output Save As must open filename picker."
            assert target.is_file(), "Save As did not create the edited PDF."
        actual = [int(page.mediabox.width)-600 for page in PdfReader(target).pages]
        assert actual == expected, (actual, expected)
        assert [int(p.mediabox.width)-600 for p in PdfReader(one).pages] == [1, 3, 5]
        assert [int(p.mediabox.width)-600 for p in PdfReader(two).pages] == [6, 4, 2]

        print("UI full flow passed: import, merge, delete, six-column zoom, "
              "new workflow, multi-step AI parsing, and Save As PDF")
        app.after(150,app.destroy)
        app.mainloop()

if __name__ == "__main__":
    main()
