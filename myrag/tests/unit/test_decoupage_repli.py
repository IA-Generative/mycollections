"""Diagnostic d'octobre 2026, P2 : le découpage « article » (et « qr ») rendait ZÉRO passage sur
un texte sans en-tête d'article (ou sans question), et le dépôt échouait en « Aucun chunk
produit ». Écrit avant le correctif : un découpage explicite qui ne trouve pas ses marqueurs
se replie sur un découpage par sections ou par longueur, sans rien perdre du texte."""

import pytest

from app.services.chunker import chunk_document

TEXTE = ("Note de service.\n\nPremier paragraphe qui explique le contexte de la note et "
         "son objet.\n\n## Modalités\n\nLe télétravail est ouvert deux jours par semaine.\n")


@pytest.mark.parametrize("strategie", ["article", "qr"])
def test_un_decoupage_sans_ses_marqueurs_se_replie(strategie):
    morceaux = chunk_document(TEXTE, strategy=strategie)
    assert morceaux, f"« {strategie} » sans marqueurs ne doit pas rendre zéro passage"
    tout = " ".join(m["content"] for m in morceaux)
    assert "deux jours par semaine" in tout and "Premier paragraphe" in tout, "rien du texte ne doit se perdre"


def test_un_vrai_code_reste_decoupe_par_article():
    code = "Article L1\n\nPremier article.\n\nArticle L2\n\nSecond article.\n"
    morceaux = chunk_document(code, strategy="article")
    assert len(morceaux) == 2
