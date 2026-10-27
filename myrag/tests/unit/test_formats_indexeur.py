"""Le nom sous lequel un fichier part vers l'indexeur (app/services/formats.py)."""

from app.services import formats


def test_un_texte_que_l_indexeur_ne_lit_pas_part_en_txt():
    assert formats.nom_pour_l_indexeur("donnees.csv") == "donnees.csv.txt"
    assert formats.nom_pour_l_indexeur("note.JSON") == "note.JSON.txt"
    assert formats.nom_pour_l_indexeur("sans-extension") == "sans-extension.txt"


def test_un_document_ou_un_texte_lu_garde_son_nom():
    for nom in ("note.md", "note.txt", "rapport.pdf", "lettre.docx", "diapo.pptx", "photo.jpg", "message.eml"):
        assert formats.nom_pour_l_indexeur(nom) == nom
