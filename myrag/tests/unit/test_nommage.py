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


# ─── L'identifiant : ce que tapent les applications ───────────────────────────────────

from app.services.nommage import deriver_identifiant, motif_de_refus  # noqa: E402


@pytest.mark.parametrize("titre,attendu", [
    ("Codes NATINF", "codes-natinf"),
    ("Droit des étrangers", "droit-etrangers"),
    ("Sécurité & délinquance !", "securite-delinquance"),
    ("FAQ Séjour et travail (SDST)", "faq-sejour-travail-sdst"),
    ("2024 — Accidents de la circulation", "accidents-circulation"),
    ("De la", "de-la"),                       # que des mots vides : on les garde plutôt que rien
    ("", ""),
])
def test_l_identifiant_derive_du_titre_translittere_au_lieu_de_supprimer(titre, attendu):
    assert deriver_identifiant(titre) == attendu


def test_un_identifiant_derive_est_toujours_acceptable():
    long = "Répertoire national des élus municipaux départementaux régionaux et européens"
    ident = deriver_identifiant(long)
    assert len(ident) <= 40 and not ident.endswith("-") and motif_de_refus(ident) is None


@pytest.mark.parametrize("ident,motif", [
    ("codes-natinf", None), ("rh2", None),
    ("", "empty"), ("ab", "longueur"), ("x" * 41, "longueur"),
    ("Codes", "format"), ("codes_natinf", "format"), ("codes--natinf", "format"), ("-codes", "format"),
    ("2024-codes", "format"), ("test trajectoire écologie", "format"),
    ("all", "reserve"), ("templates", "reserve"),
    ("demo-teletravail", "prefixe"), ("amorce-natinf", "prefixe"), ("rag-etranger", "prefixe"), ("test-x", "prefixe"),
    ("demonstration", None),                  # « demo » sans tiret n'est pas un préfixe de provenance
])
def test_les_motifs_de_refus(ident, motif):
    assert motif_de_refus(ident) == motif


def test_les_prefixes_bannis_se_reglent_par_la_configuration(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "myrag_prefixes_bannis", "brouillon-, tmp-")
    assert motif_de_refus("demo-x") is None and motif_de_refus("tmp-x") == "prefixe"
