"""Des PDF fictifs d'une page, construits à la main : l'un porte du texte, l'autre n'est qu'une
image de page, comme un scan sans OCR. Aucune donnée réelle."""

from __future__ import annotations


def _pdf(contenu_page: bytes, ressources: bytes) -> bytes:
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources " + ressources + b" >>",
        b"<< /Length %d >>\nstream\n" % len(contenu_page) + contenu_page + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    sortie, positions = b"%PDF-1.4\n", []
    for i, objet in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += b"%d 0 obj\n" % i + objet + b"\nendobj\n"
    xref = len(sortie)
    sortie += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1) + b"".join(b"%010d 00000 n \n" % p for p in positions)
    return sortie + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objets) + 1, xref)


#: Un PDF électronique : du texte, une police.
PDF_TEXTE = _pdf(b"BT /F1 12 Tf 72 720 Td (Releve de decisions fictif, assez de texte pour une vraie page.) Tj ET", b"<< /Font << /F1 5 0 R >> >>")
#: Un scan : aucune couche texte.
PDF_SCAN = _pdf(b"q 595 0 0 842 0 0 cm Q", b"<< >>")
