"""Les assistants de recherche (ADR-0003, lot B) : la liste et ce qui distingue un assistant d'une
collection, la création d'un assistant à deux collections, le régime d'une source, une consigne et
« Tester », le bac à sable (réponse et trace), la publication d'une version.

Ignoré si le drapeau `assistants` est faux sur la cible. Sur une prévisualisation, le moteur des
assistants est remplacé par sa doublure (MYCOLLECTIONS_DOUBLURE_ASSISTANTS) : la réponse est fixe,
on vérifie donc la mécanique des écrans, pas le contenu des réponses.

La séquence partage la page du testeur : chaque test reprend là où le précédent s'arrête. Elle crée
deux collections (purgées à la fin) et un assistant, archivé à la fin (rien n'est effacé, mais il
quitte la liste).
"""

from __future__ import annotations

import datetime as _dt
import re

import pytest

from tests.e2e.conftest import _menage, prefixe_de_la_cible

QUESTION = "Quelles pièces fournir pour une demande de titre de séjour ?"
#: Ce que la séquence crée, rempli par la fixture du module.
ESSAI: dict = {}


@pytest.fixture(scope="module", autouse=True)
def assistant_essai(session_testeur):
    r = session_testeur.get("/api/config")
    if r.status != 200 or (r.json() or {}).get("assistants") is not True:
        pytest.skip("drapeau assistants à faux sur cette cible")
    prefixe = prefixe_de_la_cible(session_testeur)
    jour = _dt.date.today().strftime("%Y%m%d")
    collections = [f"{prefixe}e2e-ast1-{jour}", f"{prefixe}e2e-ast2-{jour}"]
    for nom, titre in zip(collections, ("Assistant e2e : guide", "Assistant e2e : code"), strict=True):
        _menage(session_testeur, nom)
        cree = session_testeur.post(
            "/api/collections", {"name": nom, "titre": titre, "description": "Collection d'essai de la suite de bout en bout.", "contact_email": "contact@fake-domain.name"}
        )
        if cree.status != 200:
            pytest.skip(f"création de la collection d'essai refusée ({cree.status}) : parcours des assistants ignoré")
    ESSAI.update(collections=collections, titres=["Assistant e2e : guide", "Assistant e2e : code"], assistant=f"{prefixe}e2e-assistant-{jour}")
    yield ESSAI
    # L'assistant d'essai est archivé (rien n'est effacé, mais il ne se voit plus), puis ses collections purgées.
    session_testeur.post(f"/api/assistants/{ESSAI['assistant']}/archiver", {})
    for nom in collections:
        _menage(session_testeur, nom)


def _fiche(session) -> dict:
    r = session.get(f"/api/assistants/{ESSAI['assistant']}")
    assert r.status == 200, r.status
    return r.json()["fiche"]


def test_la_liste_dit_ce_qu_est_un_assistant(session_testeur, captures):
    page = session_testeur.aller("/assistants")
    assert page.locator("h1").first.inner_text().strip() == "Assistants de recherche"
    texte = session_testeur.texte()
    # Collection et assistant : deux objets distincts, et la page le dit.
    assert "Une collection" in texte
    assert "Il ne contient pas de documents" in texte
    assert page.get_by_role("link", name="Créer un assistant").count() >= 1
    captures.prendre(page, "13-assistants-liste")


def test_creer_un_assistant_a_deux_collections(session_testeur, captures):
    page = session_testeur.aller("/assistants/nouveau")
    page.locator("#titre").fill("Assistant de la suite e2e")
    page.get_by_role("button", name="Le choisir moi-même").click()
    page.locator("#identifiant").fill(ESSAI["assistant"])
    for nom in ESSAI["collections"]:
        # Une case DSFR est masquée sous son libellé : on clique le libellé, comme une personne.
        page.locator(f"label[for='src-{nom}']").click()
        assert page.locator(f"#src-{nom}").is_checked()
    captures.prendre(page, "13-assistants-creation")
    page.get_by_role("button", name="Créer l'assistant").click()
    page.wait_for_url(re.compile(rf"/assistants/{re.escape(ESSAI['assistant'])}/sources$"), timeout=30_000)
    assert [s["id"] for s in _fiche(session_testeur)["sources"]] == ESSAI["collections"]


def test_le_regime_d_une_source(session_testeur):
    page = session_testeur.page
    second = ESSAI["titres"][1]
    page.get_by_label(f"Quand interroger {second}").select_option("sur_consigne")
    page.get_by_role("button", name="Enregistrer les sources").click()
    page.get_by_text("Sources enregistrées").wait_for(timeout=15_000)
    regimes = {s["id"]: s["regime"] for s in _fiche(session_testeur)["sources"]}
    assert regimes[ESSAI["collections"][1]] == "sur_consigne", regimes


def test_une_consigne(session_testeur, captures):
    page = session_testeur.aller(f"/assistants/{ESSAI['assistant']}/consignes")
    page.get_by_role("button", name="Ajouter une consigne").click()
    # Le focus va au premier champ ; Échap annule et rend la main.
    assert page.evaluate("document.activeElement.id") == "quand"
    page.keyboard.press("Escape")
    assert page.locator("#quand").count() == 0
    page.get_by_role("button", name="Ajouter une consigne").click()
    page.locator("#quand").fill("La question porte sur un titre de séjour")
    page.locator("#exemples").fill(QUESTION)
    page.get_by_role("button", name="Ajouter une étape").click()
    page.get_by_role("button", name="Ajouter une étape").click()
    page.locator("#etape-1").select_option(ESSAI["collections"][1])
    page.locator("#avec-1").fill("article_trouve")
    page.locator("#repondre").fill("Citez les passages utilisés.")
    page.get_by_role("button", name="Valider la consigne").click()
    page.get_by_role("button", name="Enregistrer les consignes").click()
    page.get_by_text("Consignes enregistrées").wait_for(timeout=15_000)
    consignes = _fiche(session_testeur)["consignes"]
    assert len(consignes) == 1
    assert consignes[0]["quand"] == "La question porte sur un titre de séjour"
    assert consignes[0]["chercher"] == [{"source": ESSAI["collections"][0], "avec": None}, {"source": ESSAI["collections"][1], "avec": "article_trouve"}]
    captures.prendre(page, "13-assistants-consignes")


def test_tester_une_consigne(session_testeur, captures):
    page = session_testeur.page
    page.locator(".consignes-carte").first.get_by_role("button", name="Tester").click()
    page.get_by_role("heading", name="Comment l'assistant a cherché").wait_for(timeout=30_000)
    assert page.locator("#question-essai").input_value() == QUESTION
    assert "Où chercher" in session_testeur.texte()
    captures.prendre(page, "13-assistants-tester")


def test_le_bac_a_sable(session_testeur, captures):
    page = session_testeur.aller(f"/assistants/{ESSAI['assistant']}/bac-a-sable")
    page.locator("#question").fill(QUESTION)
    page.keyboard.press("Enter")
    reponse = page.locator(".myrag-msg--assistant").first
    reponse.wait_for(timeout=30_000)
    assert "n'a pas pu aboutir" not in reponse.inner_text()
    repli = reponse.locator("summary", has_text="Comment l'assistant a cherché")
    repli.click()
    assert reponse.locator(".assistant-trace").is_visible()
    assert "Où chercher" in reponse.inner_text()
    captures.prendre(page, "13-assistants-bac-a-sable")


def test_publier_une_version(session_testeur, captures):
    page = session_testeur.aller(f"/assistants/{ESSAI['assistant']}/publication")
    page.get_by_role("button", name="Publier une version").click()
    page.get_by_text("Publié : le brouillon est devenu une version.").wait_for(timeout=15_000)
    r = session_testeur.get(f"/api/assistants/{ESSAI['assistant']}/versions")
    assert r.status == 200 and len(r.json().get("versions") or []) >= 1, r.status
    captures.prendre(page, "13-assistants-publication")
