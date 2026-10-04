"""Une image de chaque écran, à 1280 px et à 390 px, avec son texte visible : l'instrument du
rapport d'ergonomie. Ne s'exécute qu'avec E2E_CAPTURES ; ne vérifie rien d'autre que
« l'écran se charge »."""
from __future__ import annotations

import re

import pytest

ECRANS_TESTEUR = [
    ("/", "20-accueil"),
    ("/admin/catalog", "21-catalogue"),
    ("/mes-collections", "22-mes-collections"),
    ("/demandes", "23-demandes"),
    ("/guide", "24-guide"),
    ("/admin/create", "25-creation-etape-1"),
]

ECRANS_COLLECTION = [
    ("", "30-fiche"),
    ("/playground", "31-bac-a-sable"),
    ("/publish", "32-publication"),
    ("/config", "33-reglages"),
    ("/prompt", "34-consignes"),
    ("/upload", "35-ajouter-des-documents"),
    ("/graph", "36-graphe"),
]


@pytest.mark.captures
@pytest.mark.parametrize("chemin,nom", ECRANS_TESTEUR)
def test_capture_ecran(session_testeur, captures, chemin, nom):
    page = session_testeur.aller(chemin)
    page.wait_for_timeout(1_500)
    captures.prendre(page, nom)


@pytest.mark.captures
@pytest.mark.parametrize("suffixe,nom", ECRANS_COLLECTION)
def test_capture_ecran_de_collection(session_testeur, collection_publiee, captures, suffixe, nom):
    page = session_testeur.aller(f"/c/{collection_publiee['name']}{suffixe}")
    page.wait_for_timeout(2_500)
    captures.prendre(page, nom)


@pytest.mark.captures
def test_capture_ecrans_d_administration(session_admin, captures):
    for chemin, nom in (("/admin", "40-administration"), ("/admin/categories", "41-categories"), ("/admin/amorces", "42-amorces")):
        page = session_admin.aller(chemin)
        page.wait_for_timeout(1_500)
        captures.prendre(page, nom)
