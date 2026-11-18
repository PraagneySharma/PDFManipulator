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
        assert app.inspector_visible, "Workflow builder must open by default."
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
        assert first.name in app.files_summary_var.get()
        assert second.name in app.files_summary_var.get()

        # Preview zoom remains responsive with the builder visible.
        app.change_start_mode("Merge original PDFs now")
        app.zoom_scale = 1.0
        app.zoom_var.set("100%")
        app.update()
        app._render_pages()
        assert app.compiled and app.compiled.page_count == 6
        cards = [child for child in app.page_list.winfo_children()
                 if hasattr(child, "page_index")]
        assert len({card.grid_info()["column"] for card in cards}) == 6, (
            "Six columns must fit at default zoom")
        app.change_zoom(0.4)
        app.update()
        cards = [child for child in app.page_list.winfo_children()
                 if hasattr(child, "page_index")]
        assert len({card.grid_info()["column"] for card in cards}) < 6
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
