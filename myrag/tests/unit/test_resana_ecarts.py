"""Les documents écartés d'un import Résana : un code stable, une explication, un export tableur."""

from app.services import resana_ecarts as m


def test_un_code_connu_est_garde_sinon_il_vient_du_texte():
    assert m.coder("peu importe", "doublon") == "doublon"
    assert m.coder("même contenu que « Note A »") == "doublon"
    assert m.coder("format non pris en charge") == "format"
    assert m.coder("Résana vous refuse ce document.") == "hors_droits"
    assert m.coder("conversion en PDF impossible (x)") == "conversion"
    assert m.coder("texte illisible") == "illisible"
    assert m.coder("document vide") == "vide"
    assert m.coder("trop volumineux pour l'indexation") == "trop_volumineux"
    assert m.coder("Un document dépasse la taille admise (100 Mo).") == "trop_volumineux"
    assert m.coder("") == "autre" and m.coder(None, "inconnu") == "autre"


def test_chaque_code_a_une_explication_et_un_quoi_faire():
    for code in m.EXPLICATIONS:
        ex = m.expliquer(code)
        assert ex["code"] == code and ex["libelle"] and ex["explication"] and ex["quoi_faire"]
    assert m.expliquer("n_importe_quoi")["code"] == "autre"


def test_le_csv_a_un_bom_un_point_virgule_et_neutralise_les_formules():
    csv = m.vers_csv(
        [
            {
                "titre": "=HYPERLINK(1)",
                "chemin": "Notes",
                "raison": "même contenu que « A »",
                "code": "doublon",
                "doublon_de_titre": "A",
                "url": "https://resana.fake-domain.name/e/ged/1",
            }
        ]
    )
    lignes = csv.split("\r\n")
    assert lignes[0].startswith("﻿") and lignes[0].lstrip("﻿") == ";".join(m.COLONNES_CSV)
    assert lignes[1].startswith("'=HYPERLINK(1);Notes;même contenu que « A »;") and lignes[1].endswith(";A;https://resana.fake-domain.name/e/ged/1")
