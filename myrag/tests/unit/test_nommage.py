"""Le titre que lit une personne — jamais l'identifiant brut."""

import pytest

from app.services.nommage import cle_valide, titre_de, titre_depuis_alias, titre_depuis_nom


@pytest.mark.parametrize("name,attendu", [
    ("amorce-natinf", "NATINF"),
    ("amorce-ta-caa-ceseda", "TA CAA CESEDA"),
    ("demo-teletravail-et-charte", "Teletravail et charte"),
    ("dgef-sdst-faq", "DGEF SDST FAQ"),
    ("legifrance", "Legifrance"),
    ("amorce-", "Amorce"),  # un préfixe seul n'est pas retiré : il ne resterait rien
    ("", ""),
])
def test_le_titre_deduit_du_nom_perd_son_prefixe_de_provenance(name, attendu):
    assert titre_depuis_nom(name) == attendu


@pytest.mark.parametrize("alias,attendu", [
    ("📚 Télétravail — politique interne", "Télétravail — politique interne"),
    ("📖 Légifrance (corpus partagé)", "Légifrance"),
    ("Mirai RAG — Droit des étrangers (textes légaux)", "Droit des étrangers (textes légaux)"),
    ("📚 demo-x", ""),          # le défaut du wizard : un identifiant déguisé
    ("MirAI demo-x", ""),       # le défaut de la page de publication
    ("openrag-dgef-sdst-faq", ""),
    (None, ""),
])
def test_un_alias_qui_n_est_qu_un_identifiant_ne_fait_pas_un_titre(alias, attendu):
    assert titre_depuis_alias(alias, "demo-x") == attendu


def test_le_titre_de_la_fiche_prime_sur_le_nom():
    assert titre_de({"name": "amorce-natinf", "titre": "Codes NATINF"}) == "Codes NATINF"
    assert titre_de({"name": "amorce-natinf", "titre": "  "}) == "NATINF"
    assert titre_de({"name": "amorce-natinf"}) == "NATINF"


@pytest.mark.parametrize("cle,ok", [
    ("droit-etrangers", True), ("a1", True), ("Droit", False), ("droit_etrangers", False),
    ("-droit", False), ("droit--etrangers", False), ("", False), ("x" * 65, False),
])
def test_une_cle_de_categorie_est_un_identifiant_propre(cle, ok):
    assert cle_valide(cle) is ok
