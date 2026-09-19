"""Page « extrait » ouverte en onglet : lisible, sans balises techniques, sans « Retour »."""
from app.main import _decouper_morceau, _extract_render_html, _paragraphes_html

RELU = """[CONTEXT]

Ce document présente l'article R. 532-28-3 du CESEDA.

* filename: CESEDA-R532-28-3__LEGIARTI000043250462.md

[CHUNK_START]

Article R. 532-28-3 du CESEDA (partie 1/3).

Source : https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000043250462

[CHUNK_END]"""


def test_decoupe_le_resume_le_fichier_et_le_texte():
    contexte, fichier, corps = _decouper_morceau(RELU)
    assert contexte == "Ce document présente l'article R. 532-28-3 du CESEDA."
    assert fichier == "CESEDA-R532-28-3__LEGIARTI000043250462.md"
    assert corps.startswith("Article R. 532-28-3")
    assert corps.endswith("LEGIARTI000043250462")


def test_un_texte_sans_balise_ressort_tel_quel():
    assert _decouper_morceau("  # Titre\n\ntexte ") == ("", "", "# Titre\n\ntexte")
    assert _decouper_morceau("[CHUNK_START]\ntexte coupé") == ("", "", "texte coupé")
    assert _decouper_morceau("") == ("", "", "")


def test_les_paragraphes_echappent_puis_lient():
    html = _paragraphes_html("<script>x</script>\n\nVoir https://exemple.fr/a?b=1&c=2.")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '<a href="https://exemple.fr/a?b=1&amp;c=2" target="_blank"' in html
    assert html.endswith(".</p>")  # le point final reste hors du lien


def test_la_page_est_lisible():
    page = _extract_render_html({"page_content": RELU, "page": 1}, "abc", b"", 200)
    for balise in ("[CONTEXT]", "[CHUNK_START]", "[CHUNK_END]", "* filename", "Retour", "history.back"):
        assert balise not in page
    assert "<h1>CESEDA-R532-28-3__LEGIARTI000043250462.md</h1>" in page
    assert "<strong>Page</strong> : 1" in page
    assert "résumé automatique" in page
    assert 'href="https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000043250462"' in page


def test_les_metadonnees_imbriquees_sont_lues():
    page = _extract_render_html(
        {"page_content": "texte", "metadata": {"original_filename": "<a>.md", "partition": "demo"}},
        "abc", b"", 200)
    assert "&lt;a&gt;.md" in page and "<a>.md" not in page
    assert "<strong>Collection</strong> : demo" in page


def test_un_echec_garde_un_indice_sans_retour():
    page = _extract_render_html(None, "abc", b"<oups>", 502)
    assert "HTTP 502" in page and "&lt;oups&gt;" in page and "Retour" not in page
