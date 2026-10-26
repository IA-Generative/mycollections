"""Génère un fichier par format, chacun avec son code témoin FMT-<EXT>-<n>. Contenu fictif.

    uv run --no-project --with python-docx --with python-pptx --with openpyxl --with pillow \
        python _generer.py <dossier>

Demande LibreOffice (`soffice`) pour les formats convertis. Le .ppt est rangé compressé (.gz) : il
dépasse la taille admise par le dépôt.
"""
import email.message, io, json, shutil, subprocess, sys, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from pptx import Presentation
from pptx.util import Inches
import openpyxl

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SOFFICE = shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"
def phrase(ext, n): return f"Le code de contrôle du format {ext.upper()} est FMT-{ext.upper()}-{n}."
FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 34)

def image(ext, n, nom):
    img = Image.new("RGB", (1400, 260), "white"); d = ImageDraw.Draw(img)
    d.text((40, 60), "Note de contrôle des formats", fill="black", font=FONT)
    d.text((40, 140), phrase(ext, n), fill="black", font=FONT)
    return img

# Texte
(OUT/"format.txt").write_text(f"Note de contrôle des formats\n\n{phrase('txt', 1101)}\n")
(OUT/"format.md").write_text(f"# Note de contrôle des formats\n\n{phrase('md', 1102)}\n")
(OUT/"format.csv").write_text(f"rubrique;valeur\ncontrôle;{phrase('csv', 1103)}\n")
(OUT/"format.html").write_text(f"<html><body><h1>Note de contrôle des formats</h1><p>{phrase('html', 1104)}</p></body></html>")
(OUT/"format.json").write_text(json.dumps({"note": phrase("json", 1105)}, ensure_ascii=False))
# Bureautique de base
doc = Document(); doc.add_heading("Note de contrôle des formats", 1); doc.add_paragraph(phrase("docx", 1201)); doc.save(OUT/"format.docx")
for ext, n in (("doc", 1202), ("odt", 1203), ("rtf", 1204), ("pdf", 1205)):
    d = Document(); d.add_heading("Note de contrôle des formats", 1); d.add_paragraph(phrase(ext, n))
    src = OUT/f"_src-{ext}.docx"; d.save(src)
    subprocess.run([SOFFICE, "--headless", "--convert-to", ext, "--outdir", str(OUT/"_conv"), str(src)], check=True, capture_output=True)
    (OUT/"_conv"/f"_src-{ext}.{ext}").rename(OUT/f"format.{ext}"); src.unlink()
for ext, n in (("pptx", 1301), ("ppt", 1302), ("odp", 1303)):
    p = Presentation(); s = p.slides.add_slide(p.slide_layouts[1]); s.shapes.title.text = "Note de contrôle des formats"; s.placeholders[1].text = phrase(ext, n)
    if ext == "pptx": p.save(OUT/"format.pptx"); continue
    src = OUT/f"_src-{ext}.pptx"; p.save(src)
    subprocess.run([SOFFICE, "--headless", "--convert-to", ext, "--outdir", str(OUT/"_conv"), str(src)], check=True, capture_output=True)
    (OUT/"_conv"/f"_src-{ext}.{ext}").rename(OUT/f"format.{ext}"); src.unlink()
for ext, n in (("xlsx", 1401), ("xls", 1402), ("ods", 1403)):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Contrôle"; ws.append(["Rubrique", "Valeur"]); ws.append(["contrôle", phrase(ext, n)])
    if ext == "xlsx": wb.save(OUT/"format.xlsx"); continue
    src = OUT/f"_src-{ext}.xlsx"; wb.save(src)
    subprocess.run([SOFFICE, "--headless", "--convert-to", ext, "--outdir", str(OUT/"_conv"), str(src)], check=True, capture_output=True)
    (OUT/"_conv"/f"_src-{ext}.{ext}").rename(OUT/f"format.{ext}"); src.unlink()
# Courriel
m = email.message.EmailMessage(); m["From"] = "expediteur@fake-domain.name"; m["To"] = "destinataire@fake-domain.name"; m["Subject"] = "Note de contrôle des formats"
m.set_content(phrase("eml", 1501)); (OUT/"format.eml").write_bytes(bytes(m))
# Images et scan
image("png", 1601, "png").save(OUT/"format.png")
image("jpg", 1602, "jpg").save(OUT/"format.jpg", quality=92)
image("pdf-scan", 1603, "scan").save(OUT/"format-scan.pdf", "PDF", resolution=150)
image("gif", 1604, "gif").save(OUT/"format.gif")
# Archive
b = io.BytesIO()
with zipfile.ZipFile(b, "w") as z: z.writestr("dedans.txt", phrase("zip", 1701))
(OUT/"format.zip").write_bytes(b.getvalue())
import gzip, shutil; shutil.rmtree(OUT/"_conv", ignore_errors=True)
(OUT/"format.ppt.gz").write_bytes(gzip.compress((OUT/"format.ppt").read_bytes(), 9)); (OUT/"format.ppt").unlink()
for f in sorted(OUT.iterdir()): print(f.name, f.stat().st_size)
