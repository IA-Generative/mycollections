"""Les connecteurs déclarés par configuration : la déclaration, le périmètre (lisible de tous si et
seulement si déclaré), l'exécution d'un assistant à une collection et un connecteur, la recherche v1."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import settings
from app.harnais import perimetre
from app.harnais.connecteurs.eligibilite import ConnecteurEligibilite
from app.harnais.contrat import FicheAssistant, Passage
from app.services import connecteurs_declares
from tests.conftest import SUPERADMIN
from tests.harnais.conftest import IDENTITES

URL = "http://referentiel.fake-domain.name"
ID = "eligibilite-dgef"
LIGNE = {"id": 7, "intitule": "Carte de résident", "pieces": "Justificatif de domicile, passeport"}


def declaration(**modifs) -> dict:
    d = {
        "id": ID,
        "type": "eligibilite",
        "url": URL,
        "titre": "Référentiel d'éligibilité",
        "description": "Titres de séjour et pièces.",
        "tables": ["titres"],
        "exemples": ["Quelles pièces pour une carte de résident ?"],
    }
    return {**d, **modifs}


@pytest.fixture
def declarer(monkeypatch):
    def _f(*entrees) -> None:
        monkeypatch.setattr(settings, "connecteurs", json.dumps(list(entrees)))

    return _f


# ─── La déclaration ──────────────────────────────────────────────────────────────────────────


def test_rien_n_est_declare_par_defaut(monkeypatch):
    monkeypatch.setattr(settings, "connecteurs", "")
    assert connecteurs_declares.declarations() == {}


@pytest.mark.parametrize(
    "brut", ["pas du json", '{"id": "x"}', "[1]", json.dumps([declaration(type="inconnu")]), json.dumps([declaration(tables=[])]), json.dumps([declaration(id="A")])]
)
def test_une_declaration_invalide_est_ignoree_sans_rien_casser(monkeypatch, brut):
    monkeypatch.setattr(settings, "connecteurs", brut)
    assert connecteurs_declares.declarations() == {}


def test_la_premiere_declaration_d_un_identifiant_l_emporte(declarer):
    declarer(declaration(), declaration(titre="Autre"))
    assert connecteurs_declares.declarations()[ID].titre == "Référentiel d'éligibilité"


def test_la_vue_publique_ne_montre_ni_l_adresse_ni_les_tables(declarer):
    declarer(declaration())
    vue = connecteurs_declares.publique(connecteurs_declares.declarations()[ID])
    assert vue == {
        "id": ID,
        "type": "connecteur",
        "titre": "Référentiel d'éligibilité",
        "description": "Titres de séjour et pièces.",
        "exemples": ["Quelles pièces pour une carte de résident ?"],
    }
    assert URL not in json.dumps(vue)


# ─── Le périmètre ────────────────────────────────────────────────────────────────────────────


def _fiche(*sources) -> FicheAssistant:
    return FicheAssistant.model_validate({"assistant": "asst-essai", "titre": "Essai", "sources": list(sources)})


CONNECTEUR = {"id": ID, "type": "connecteur", "regime": "selon_question"}
COLLECTION_FERMEE = {"id": "col-fermee", "type": "collection", "regime": "toujours"}


def test_un_connecteur_declare_est_lisible_de_tous_et_une_collection_fermee_non():
    fiche = _fiche(COLLECTION_FERMEE, CONNECTEUR)
    cols = {"col-fermee": {"name": "col-fermee", "scope": "private", "scope_groups": [], "created_by": "autre", "archived_at": None}}
    assert perimetre.sources_lisibles(fiche, cols, groupes=[], sub="n-importe-qui", connecteurs={ID}) == [ID]


def test_un_connecteur_non_declare_n_est_jamais_lisible():
    fiche = _fiche(CONNECTEUR)
    assert perimetre.sources_lisibles(fiche, {}, groupes=["/myrag/superadmin"], sub="x", connecteurs=set()) == []
    assert perimetre.sources_lisibles(fiche, {}, groupes=[], sub="x") == []  # par défaut : aucun


def test_un_connecteur_ne_se_declare_pas_collection_et_reciproquement():
    fiche = _fiche({"id": ID, "type": "collection", "regime": "toujours"})
    assert perimetre.sources_lisibles(fiche, {}, groupes=[], sub="x", connecteurs={ID}) == []


def test_le_passage_d_un_connecteur_non_declare_est_filtre_et_le_temoin_negatif_le_voit():
    p = Passage(source=ID, etape=1, rang=1, document="titres:abc", texte="ligne")
    assert perimetre.restreindre_passages([p], []) == []
    assert perimetre.restreindre_passages([p], [ID]) == [p]  # témoin : sans filtre la ligne sortirait


# ─── L'exécution et la recherche v1 ──────────────────────────────────────────────────────────


@pytest.fixture
def referentiel(monkeypatch):
    """Le service d'éligibilité simulé ; journalise les requêtes reçues."""
    requetes: list[httpx.Request] = []

    async def repondre(requete: httpx.Request) -> httpx.Response:
        requetes.append(requete)
        q = requete.url.params.get("q", "").lower()
        return httpx.Response(200, json=[LIGNE] if q in str(LIGNE).lower() else [])

    def fabrique(**options):
        return ConnecteurEligibilite(client=httpx.AsyncClient(transport=httpx.MockTransport(repondre)), **options)

    monkeypatch.setattr("app.services.assistant_recherche.ConnecteurEligibilite", fabrique)
    return requetes


@pytest.fixture
def assistant_mixte(client, en_tant_que, jeu, ident_assistant, declarer, referentiel, theatre_branche):
    """Un assistant à une collection (`ouverte`, lisible de tous) et un connecteur, publié."""
    declarer(declaration())
    en_tant_que(SUPERADMIN)
    fiche = {
        "assistant": ident_assistant,
        "titre": "Assistant mixte",
        "sources": [{"id": jeu["ouverte"], "type": "collection", "regime": "toujours", "rang": 1}, {"id": ID, "type": "connecteur", "regime": "toujours", "rang": 2}],
    }
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche).status_code == 200
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    return ident_assistant


def test_les_deux_connecteurs_sont_appeles_et_leurs_passages_fusionnes(client, en_tant_que, jeu, assistant_mixte, theatre_branche, referentiel):
    en_tant_que(IDENTITES["dehors"])
    r = client.post(f"/api/v1/assistants/{assistant_mixte}/executer", json={"question": "carte de résident"})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert theatre_branche.sources_appelees() == [jeu["ouverte"]]
    assert referentiel, "le connecteur du référentiel n'a pas été appelé"
    assert corps["par_source"] == {jeu["ouverte"]: 2, ID: 1}
    assert {p["source"] for p in corps["passages"]} == {jeu["ouverte"], ID}


def test_la_recherche_v1_rend_la_ligne_du_referentiel_dans_la_forme_du_contrat(client, en_tant_que, jeu, assistant_mixte, referentiel):
    en_tant_que(IDENTITES["dehors"])
    r = client.get("/api/v1/search", params={"q": "carte de résident", "assistant": assistant_mixte})
    assert r.status_code == 200, r.text
    corps = r.json()
    ligne = next(x for x in corps["results"] if x["context"]["collection"]["id"] == ID)
    assert ligne["context"] == {"collection": {"id": ID, "title": "Référentiel d'éligibilité"}, "right": "reader"}
    assert ligne["title"] == "Carte de résident" and ligne["url"] is None
    assert ligne["id"].startswith(f"{ID}:titres:")
    [hit] = ligne["hits"]
    assert "Justificatif de domicile" in hit["snippet"] and hit["url"] is None and hit["field"] == "content"
    assert {"id", "title", "date", "url", "score", "hits", "context"} <= set(ligne)
    autres = [x for x in corps["results"] if x["context"]["collection"]["id"] == jeu["ouverte"]]
    assert autres and all(x["url"] for x in autres)  # les collections gardent leur lien signé
    assert corps["plan"]["sources_ignorees"] == 0


def test_aucun_en_tete_d_autorisation_ne_part_vers_le_referentiel(client, en_tant_que, assistant_mixte, referentiel):
    en_tant_que(IDENTITES["alice"])
    client.get("/api/v1/search", params={"q": "carte de résident", "assistant": assistant_mixte}, headers={"Authorization": "Bearer jeton-secret"})
    assert referentiel
    assert all("authorization" not in {k.lower() for k in r.headers} and "jeton-secret" not in str(r.url) for r in referentiel)


def test_un_connecteur_retire_de_la_configuration_n_est_plus_cherche(client, en_tant_que, assistant_mixte, referentiel, monkeypatch):
    monkeypatch.setattr(settings, "connecteurs", "")
    en_tant_que(IDENTITES["dehors"])
    r = client.get("/api/v1/search", params={"q": "carte de résident", "assistant": assistant_mixte})
    assert r.status_code == 200
    assert not referentiel
    assert {x["context"]["collection"]["id"] for x in r.json()["results"]}.isdisjoint({ID})
    assert r.json()["plan"]["sources_ignorees"] == 1


def test_le_planificateur_a_regles_connait_la_description_du_connecteur(declarer):
    from app.services import assistant_recherche

    declarer(declaration())

    class Charge:
        collections: dict = {}
        version = 1

    regles = assistant_recherche.planificateur_regles(Charge(), app=object())  # type: ignore[arg-type]
    assert "Titres de séjour" in regles.descriptions[ID] and "carte de résident" in regles.descriptions[ID]


# ─── Les routes de la fiche ──────────────────────────────────────────────────────────────────


def test_la_liste_des_connecteurs_ne_donne_ni_adresse_ni_table(client, en_tant_que, declarer):
    declarer(declaration())
    en_tant_que(IDENTITES["dehors"])
    r = client.get("/api/assistants/connecteurs")
    assert r.status_code == 200
    assert r.json() == {"connecteurs": [connecteurs_declares.publique(connecteurs_declares.declarations()[ID])]}
    assert URL not in r.text and "tables" not in r.text


def test_la_liste_est_vide_sans_configuration(client, en_tant_que, monkeypatch):
    monkeypatch.setattr(settings, "connecteurs", "")
    en_tant_que(IDENTITES["dehors"])
    assert client.get("/api/assistants/connecteurs").json() == {"connecteurs": []}


def test_assembler_ne_demande_de_gerer_que_les_collections(client, en_tant_que, jeu, ident_assistant, declarer):
    """Alice gère `mienne` : elle peut assembler `mienne` + le connecteur, qui ne la retient pas."""
    declarer(declaration())
    en_tant_que(IDENTITES["alice"])
    fiche = {"assistant": ident_assistant, "titre": "À moi", "sources": [{"id": jeu["mienne"], "type": "collection"}, {"id": ID, "type": "connecteur"}]}
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche).status_code == 200
    # …mais pas avec une collection qu'elle ne gère pas
    fiche["sources"].append({"id": jeu["secrete"], "type": "collection"})
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche).status_code == 403
