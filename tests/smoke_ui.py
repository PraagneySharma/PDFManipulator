"""Noninteractive smoke test of desktop UI with real temporary PDF thumbnails."""
import tempfile
from pathlib import Path
from pypdf import PdfWriter
from studio.ui import StudioApp
from studio.recipes import preset

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
        print("UI full flow passed:", app.compiled.page_count, "pages")
        app.after(150,app.destroy)
        app.mainloop()

if __name__ == "__main__":
    main()
