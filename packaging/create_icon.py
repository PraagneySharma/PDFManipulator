"""Create the desktop icon for the local Windows executable.

Uses Pillow; no external assets or runtime web dependencies.
"""
from pathlib import Path
from PIL import Image, ImageDraw

SIZE = 256
OUT = Path(__file__).resolve().parent / "pdf_manipulator.ico"

def draw_icon():
    scale = 4
    sz = SIZE * scale
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    def q(points): return tuple(int(x*scale) for x in points)
    # Rounded blue square behind a white PDF page.
    d.rounded_rectangle(q((8, 8, 248, 248)), radius=53*scale, fill="#347BE8")
    d.rounded_rectangle(q((55, 36, 198, 218)), radius=16*scale, fill="#FFFFFF")
    d.polygon([(168*scale, 36*scale), (198*scale, 66*scale), (168*scale, 66*scale)], fill="#DAE9FF")
    d.line([(80*scale,112*scale),(173*scale,112*scale)], fill="#347BE8", width=13*scale)
    d.line([(80*scale,144*scale),(173*scale,144*scale)], fill="#347BE8", width=13*scale)
    d.line([(80*scale,176*scale),(140*scale,176*scale)], fill="#347BE8", width=13*scale)
    img = img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    img.save(OUT, format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    print(OUT)

if __name__ == "__main__":
    draw_icon()
