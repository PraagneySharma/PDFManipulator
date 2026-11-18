"""Full Windows GUI regression for manual-first PDF workflow editing."""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from pdfmanipulator.ui import StudioApp, StepDialog
from pdfmanipulator.recipes import preset


def make(path, numbers):
    writer = PdfWriter()
    for value in numbers:
        writer.add_blank_page(width=600 + value, height=800)
    with path.open("wb") as output:
        writer.write(output)


def ids(path):
    return [int(page.mediabox.width) - 600 for page in PdfReader(path).pages]


def main():
    with TemporaryDirectory() as temp:
        first = Path(temp) / "first.pdf"
        second = Path(temp) / "second.pdf"
        make(first, [1, 2, 3])
        make(second, [8, 9, 10])

        app = StudioApp()
        app.update()
        assert app.inspector_visible, "Workflow editor must open by default."
        assert not app.sidebar_visible, "Template library must not crowd the main view."
        assert app.inspector._parent_frame.winfo_manager() == "grid"
        assert not app.composer.winfo_manager(), "AI must be optional and hidden."
        assert app.start_mode_var.get() == "PDF 1 only"

        app.add_files([first, second])
        app.update()
        assert app.steps[0] == {
            "op": "load_each", "sources": ["input1", "input2"]}, app.steps
        assert app.start_mode_var.get() == "Edit PDFs separately"
        assert app.compiled and len(app.compiled.documents) == 2
        assert "2 PDFs imported" in app.files_summary_var.get()
        assert app.active_document == 1, "Imported PDF 2 should be shown immediately."
        assert "PDF 2" in app.preview_name_var.get(), app.preview_name_var.get()
        assert second.name in app.preview_name_var.get()
        app.view_source_pdf("input1")
        assert app.active_document == 0
        assert "PDF 1" in app.preview_name_var.get()
        app.view_source_pdf("input2")
        assert app.active_document == 1
        app.toggle_sidebar()
        assert app.sidebar_visible
        app.toggle_sidebar()
        assert not app.sidebar_visible
        assert first.name in app.files_summary_var.get()
        assert second.name in app.files_summary_var.get()

        # Preview zoom remains responsive with the builder visible.
        app.change_start_mode("Merge original PDFs now")
        app.zoom_scale = 1.0
        app.zoom_var.set("100%")
        app.update()
        app._render_pages()
        app.update()
        assert app.compiled and app.compiled.page_count == 6
        cards = [child for child in app.page_list.winfo_children()
                 if hasattr(child, "page_index")]
        default_columns = len({card.grid_info()["column"] for card in cards})
        assert 2 <= default_columns <= 4, (
            f"Pages must be readable and fit on screen, got {default_columns} columns")
        viewport = app.page_list._parent_canvas
        assert max(card.winfo_rootx() + card.winfo_width() for card in cards) <= (
            viewport.winfo_rootx() + viewport.winfo_width() + 6), (
                "Thumbnail cards spill beyond the visible preview at Windows DPI scale")
        app.change_zoom(0.4)
        app.update()
        cards = [child for child in app.page_list.winfo_children()
                 if hasattr(child, "page_index")]
        assert len({card.grid_info()["column"] for card in cards}) < default_columns
        assert max(card.winfo_rootx() + card.winfo_width() for card in cards) <= (
            viewport.winfo_rootx() + viewport.winfo_width() + 6), (
                "Zoomed-in cards must fit within viewer width")
        app.toggle_fit_page()
        app.update()
        assert app.fit_full_page
        assert "Fit" in app.zoom_var.get()
        assert app.image_refs, "Fit mode must display complete page images."
        fitted_width, fitted_height = app.image_refs[0]._size
        from customtkinter import ScalingTracker
        scale = ScalingTracker.get_widget_scaling(app)
        viewport_width = app.page_list._parent_canvas.winfo_width() / scale
        viewport_height = app.page_list._parent_canvas.winfo_height() / scale
        assert fitted_width <= viewport_width, (
            "Fit page exceeds preview width")
        assert fitted_height <= max(170, int(viewport_height - 65)), (
            f"Fit page ({fitted_height}) exceeds visible viewer height "
            f"({viewport_height})")
        app.toggle_fit_page()
        assert not app.fit_full_page
        app.change_zoom(-0.4)

        # Switch back to individual PDF editing.
        app.change_start_mode("Edit PDFs separately")
        app.update()
        assert len(app.compiled.documents) == 2

        # Manually add Delete, then choose PDF 2 in the actual step editor.
        app.add_step("delete", open_editor=False)
        assert app.steps[-1]["op"] == "delete"
        dialog = StepDialog(app, 1)
        app.update()
        target = next(name for name, index in dialog.target_choices.items()
                      if index == 1)
        assert "PDF 2" in target
        dialog.target_var.set(target)
        dialog.commit()
        app.update()
        assert app.steps[1] == {"op": "delete", "pages": "1", "document": 1}
        assert ids(second) == [8, 9, 10]

        # Merge after applying the PDF-specific deletion.
        app.add_step("merge_documents", open_editor=False)
        app.update()
        assert [step["op"] for step in app.steps] == [
            "load_each", "delete", "merge_documents"], app.steps
        assert app.compiled and len(app.compiled.documents) == 1
        assert "Combined PDF" in app.preview_name_var.get()
        app.view_source_pdf("input2")
        assert "ORIGINAL PDF 2" in app.preview_name_var.get()
        assert app.source_view_alias == "input2"
        app.show_edited_result()
        assert app.source_view_alias is None
        assert "Combined PDF" in app.preview_name_var.get()
        assert [(p.source, p.index) for p in app.compiled.documents[0].pages] == [
            ("input1", 0), ("input1", 1), ("input1", 2),
            ("input2", 1), ("input2", 2)]

        # The workflow must export an actual, correctly ordered PDF.
        destination = Path(temp) / "Manually Edited.pdf"
        with patch("pdfmanipulator.ui.filedialog.asksaveasfilename",
                   return_value=str(destination)) as picker, \
             patch("pdfmanipulator.ui.messagebox.askokcancel", return_value=True), \
             patch("pdfmanipulator.ui.messagebox.showinfo"):
            app.run()
            deadline = time.monotonic() + 20
            while not destination.exists() and time.monotonic() < deadline:
                app.update()
                time.sleep(0.025)
            for _ in range(10):
                app.update()
                time.sleep(0.01)
            assert picker.call_count == 1, "Single PDF output requires Save As."
            assert destination.is_file()
        assert ids(destination) == [1, 2, 3, 9, 10]
        assert ids(first) == [1, 2, 3]
        assert ids(second) == [8, 9, 10]

        # AI features remain available, but no longer dominate the main screen.
        app.toggle_ai_composer()
        assert app.composer.winfo_manager() == "grid"
        app.toggle_ai_settings()
        assert app.ai_options.winfo_manager() == "grid"
        app.provider_var.set("ChatGPT plan")
        app._provider_changed("ChatGPT plan")
        app.update()
        assert app.chatgpt_model_row.winfo_manager() == "pack"
        app.provider_var.set("Offline")
        app._provider_changed("Offline")
        app.toggle_ai_composer()
        assert not app.composer.winfo_manager()

        # Starting a new manual workflow is not destructive to original PDFs.
        with patch("pdfmanipulator.ui.messagebox.askyesno", return_value=True):
            app.new_workflow()
        app.update()
        assert not app.sources
        assert app.steps == [{"op": "load", "source": "input1"}]
        assert app.inspector_visible
        assert "No PDFs imported" in app.files_summary_var.get()
        print("Manual-first GUI passed: visible builder, two-PDF scoped delete, "
              "post-edit merge, zoom, Save As and optional AI helper.")
        app.after(150, app.destroy)
        app.mainloop()


if __name__ == "__main__":
    main()
