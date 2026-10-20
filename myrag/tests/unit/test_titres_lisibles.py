"""Un document sans titre dans ses métadonnées s'affiche sous son nom de fichier rendu lisible :
dans la recherche v1 (Mon portail, l'extension du navigateur) comme dans les passages d'un
assistant. Un titre porté par le document reste tel quel."""

from __future__ import annotations

import pytest

from app.services.nommage import nom_de_fichier_lisible


@pytest.mark.parametrize(
    "nom, attendu",
    [
        ("section_wikipedia_extract", "Wikipedia extract"),
        ("section-le-code-de-controle.md", "Le code de controle"),
        ("circulaire-peines_2026.pdf", "Circulaire peines 2026"),
        ("  note.md ", "Note"),
        ("", ""),
    ],
)
def test_nom_de_fichier_lisible(nom, attendu):
    assert nom_de_fichier_lisible(nom, majuscule=True) == attendu


def test_sans_majuscule_par_defaut():
    assert nom_de_fichier_lisible("section_scope") == "scope"


def test_seuls_les_noms_de_section_changent():
    from app.services.nommage import titre_affiche

    assert titre_affiche("section_scope.md") == "Scope"
    assert titre_affiche("f-1") == "f-1", "un nom de fichier ordinaire reste tel quel (contrat v1)"
    assert titre_affiche("circulaire-peines_2026.md") == "circulaire-peines_2026"


def test_la_recherche_v1_rend_un_titre_lisible():
    from app.routers.recherche import _titre_du_document

    assert _titre_du_document({}, "section_corpus_note.md") == "Corpus note"
    assert _titre_du_document({"filename": "section_included_pages.md"}, "x") == "Included pages"
    assert _titre_du_document({"title": "Méthodes de l'équipe"}, "section_x.md") == "Méthodes de l'équipe"


def test_le_connecteur_du_moteur_rend_un_titre_lisible():
    from app.harnais.connecteurs.openrag import vers_passage
    from app.services.openrag_client import DocumentRecherche

    doc = DocumentRecherche(content="Le texte du passage.", metadata={"partition": "demo", "filename": "section_wikipedia_extract.md", "file_id": "f1", "_id": "m1"})
    p = vers_passage(doc, etape=1, rang=1)
    assert p is not None and p.titre == "Wikipedia extract"
