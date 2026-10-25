"""La qualité d'un tableur lu par l'indexeur (lecteur `spreadsheet`, openrag#15) : un classeur
tronqué à la borne de cellules est « tronqué », pas « dégradé » (le renvoyer le tronquerait de
nouveau) ; les formules sans valeur et les feuilles masquées ignorées sont dites, pas tues."""

from __future__ import annotations

from app.routers import sources_resana
from app.routers.ingest import avis_qualite
from app.services.indexeur import ETATS_QUALITE, qualite_lecture

#: Le détail de tâche que rend OpenRAG pour un tableur (indexer_actor._parse_outcome + stages/parse).
INFO = {
    "sheets": 3,
    "sheets_indexed": 2,
    "hidden_sheets": 1,
    "hidden_sheets_skipped": 1,
    "merged_ranges": 4,
    "formulas_without_value": 0,
    "rows_kept": 10000,
    "rows_total": 20000,
    "truncated": True,
    "max_cells": 50000,
}


def _details(**spreadsheet):
    return {"degraded_stages": ["parse"], "parse_backend": "spreadsheet", "ocr": False, "contextualization": {"total": 40, "failed": 0}, "spreadsheet": {**INFO, **spreadsheet}}


def test_un_tableur_coupe_a_la_borne_est_tronque():
    q = qualite_lecture(_details())
    assert "tronque" in ETATS_QUALITE and q["etat"] == "tronque"
    assert q["tableur"] == {
        "feuilles": 3,
        "feuilles_indexees": 2,
        "feuilles_masquees_ignorees": 1,
        "formules_sans_valeur": 0,
        "lignes_gardees": 10000,
        "lignes_total": 20000,
        "cellules_max": 50000,
        "tronque": True,
    }


def test_une_autre_etape_en_echec_reste_plus_grave():
    assert qualite_lecture({**_details(), "degraded_stages": ["caption", "parse"]})["etat"] == "degrade"
    assert qualite_lecture({**_details(), "contextualization": {"total": 40, "failed": 3}})["etat"] == "sans_contexte"


def test_un_tableur_entier_est_complet_avec_ses_comptes():
    q = qualite_lecture({**_details(truncated=False, rows_kept=12, rows_total=12, formulas_without_value=5), "degraded_stages": []})
    assert q["etat"] == "complet" and q["tableur"]["formules_sans_valeur"] == 5 and q["tableur"]["tronque"] is False


def test_l_avis_dit_ce_qui_manque():
    avis = avis_qualite("budget.xlsx", qualite_lecture(_details(formulas_without_value=2)))
    assert avis.startswith("« budget.xlsx » est indexé, mais seules 10000 lignes sur 20000 sont indexées")
    assert "2 cellules à formule sont vides" in avis and "1 feuille masquée n'a pas été indexée" in avis
    assert avis_qualite("a.xlsx", qualite_lecture({**_details(truncated=False, hidden_sheets_skipped=0), "degraded_stages": []})) is None


def test_un_tableur_tronque_n_est_pas_a_reprendre_et_le_bilan_compte_les_cellules_vides():
    cfg = {
        "documents": {
            "t": {"qualite": qualite_lecture(_details())},
            "f": {"qualite": qualite_lecture({**_details(truncated=False, formulas_without_value=7, hidden_sheets_skipped=0), "degraded_stages": []})},
            "d": {"qualite": {"etat": "degrade", "etapes": ["caption"]}},
        }
    }
    assert sources_resana.a_reprendre(cfg) == {"d"}
    bilan = sources_resana.bilan_qualite(cfg)
    assert bilan["par_etat"] == {"tronque": 1, "complet": 1, "degrade": 1} and bilan["a_reprendre"] == 1
    assert (bilan["tableurs_formules_vides"], bilan["formules_sans_valeur"]) == (1, 7)
    assert (bilan["tableurs_feuilles_masquees"], bilan["feuilles_masquees_ignorees"]) == (1, 1)
