"""Republier une collection ne doit RIEN effacer de ce que Mes collections ne gère pas.

Le défaut verrouillé ici (constaté sur `ceseda-legifrance` le 2026-09-19) : la fiche du
modèle était réécrite en entier, `params` vides. Le prompt système réglé dans l'assistant
disparaissait ; la collection répondait encore — mais ne nommait plus ses articles.
"""

import asyncio
import json

import httpx
import pytest

from app.services import owui_client as module
from app.services.owui_client import OwuiClient, fusionner_fiche

EXISTANTE = {
    "id": "openrag-ceseda-legifrance",
    "name": "CESEDA — texte Légifrance (articles en vigueur)",
    "params": {"system": "Tu cites l'article et son lien Légifrance.", "temperature": 0.2},
    "meta": {
        "description": "Le CESEDA en vigueur, article par article.",
        "profile_image_url": "/static/ceseda.png",
        "suggestion_prompts": [{"content": "Que prévoit l'article L. 423-1 ?"}],
        "tags": [{"name": "Droit des étrangers"}, {"name": "Mes collections"}],
        "toolIds": ["explorateur-graphrag"],
        "filterIds": ["lien-graphe"],
        "capabilities": {"vision": True},
    },
}


def _voulue(description="", suggestions=None):
    return {
        "id": "openrag-ceseda-legifrance", "name": "CESEDA",
        "meta": {"description": description or "Collection MyRAG openrag-ceseda-legifrance",
                 "profile_image_url": "/static/favicon.png",
                 "suggestion_prompts": [{"content": p} for p in (suggestions or [])],
                 "tags": [{"name": "Mes collections"}],
                 "capabilities": {"vision": False, "usage": False, "citations": True}},
        "params": {}, "base_model_id": None, "access_grants": [], "is_active": True,
    }


def test_le_prompt_et_les_parametres_survivent_a_une_republication():
    f = fusionner_fiche(EXISTANTE, _voulue())
    assert f["params"] == {"system": "Tu cites l'article et son lien Légifrance.", "temperature": 0.2}


def test_un_prompt_fourni_remplace_le_prompt_et_lui_seul():
    f = fusionner_fiche(EXISTANTE, _voulue(), system_prompt="Nouveau prompt.")
    assert f["params"] == {"system": "Nouveau prompt.", "temperature": 0.2}


def test_les_outils_et_les_filtres_poses_ailleurs_restent():
    meta = fusionner_fiche(EXISTANTE, _voulue())["meta"]
    assert meta["toolIds"] == ["explorateur-graphrag"] and meta["filterIds"] == ["lien-graphe"]


def test_une_description_vide_ne_remplace_pas_une_description_redigee():
    assert fusionner_fiche(EXISTANTE, _voulue())["meta"]["description"] == "Le CESEDA en vigueur, article par article."
    voulue = _voulue("Nouvelle description.")
    assert fusionner_fiche(EXISTANTE, voulue, description="Nouvelle description.")["meta"]["description"] == "Nouvelle description."


def test_les_etiquettes_d_ailleurs_restent_et_la_notre_n_est_pas_doublee():
    noms = [t["name"] for t in fusionner_fiche(EXISTANTE, _voulue())["meta"]["tags"]]
    assert noms == ["Droit des étrangers", "Mes collections"]


def test_les_suggestions_ne_sont_remplacees_que_si_on_en_fournit():
    gardees = fusionner_fiche(EXISTANTE, _voulue())["meta"]["suggestion_prompts"]
    assert gardees == [{"content": "Que prévoit l'article L. 423-1 ?"}]
    remplacees = fusionner_fiche(EXISTANTE, _voulue(suggestions=["Autre question ?"]), suggestions_fournies=True)
    assert remplacees["meta"]["suggestion_prompts"] == [{"content": "Autre question ?"}]


def test_ce_que_mes_collections_gere_est_bien_pose():
    f = fusionner_fiche(EXISTANTE, _voulue())
    assert f["name"] == "CESEDA" and f["base_model_id"] is None and f["access_grants"] == []
    assert f["meta"]["capabilities"] == {"vision": False, "usage": False, "citations": True}


def test_premiere_publication_la_fiche_voulue_part_telle_quelle():
    assert fusionner_fiche(None, _voulue("Une description.")) == _voulue("Une description.")


def test_la_fiche_existante_n_est_pas_modifiee_en_place():
    avant = json.dumps(EXISTANTE, sort_keys=True)
    fusionner_fiche(EXISTANTE, _voulue(), system_prompt="x")
    assert json.dumps(EXISTANTE, sort_keys=True) == avant


# ─── De bout en bout, contre un faux socle ───────────────────────────────────────────

def _socle(monkeypatch, lecture: httpx.Response | Exception):
    """Un OpenWebUI de théâtre : répond `lecture` au GET de la fiche, accepte la mise à jour."""
    envois = []

    def repondre(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            if isinstance(lecture, Exception):
                raise lecture
            return lecture
        envois.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "ok"})

    vrai = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient",
                        lambda **k: vrai(transport=httpx.MockTransport(repondre), **k))
    return envois


def _republier(**k):
    client = OwuiClient(api_key="cle-de-test", base_url="http://socle.test")
    return asyncio.run(client.upsert_model(model_id="openrag-ceseda-legifrance", name="CESEDA", **k))


def test_republier_envoie_au_socle_le_prompt_qu_il_avait(monkeypatch):
    envois = _socle(monkeypatch, httpx.Response(200, json=EXISTANTE))
    _republier()
    assert len(envois) == 1
    assert envois[0]["params"]["system"] == "Tu cites l'article et son lien Légifrance."
    assert envois[0]["meta"]["toolIds"] == ["explorateur-graphrag"]


@pytest.mark.parametrize("code", [401, 403, 404])
def test_une_fiche_absente_n_empeche_pas_la_premiere_publication(monkeypatch, code):
    envois = _socle(monkeypatch, httpx.Response(code, json={"detail": "absent"}))
    _republier(description="Première publication.")
    assert envois[0]["params"] == {} and envois[0]["meta"]["description"] == "Première publication."


def test_une_reponse_vide_vaut_pas_de_fiche(monkeypatch):
    envois = _socle(monkeypatch, httpx.Response(200, content=b"null", headers={"content-type": "application/json"}))
    _republier()
    assert envois[0]["params"] == {}


@pytest.mark.parametrize("panne", [httpx.Response(503, text="indisponible"), httpx.ConnectTimeout("délai")])
def test_si_la_fiche_est_illisible_on_n_ecrit_rien(monkeypatch, panne):
    """Une panne de lecture n'est pas « pas de fiche » : écrire à l'aveugle effacerait le prompt."""
    envois = _socle(monkeypatch, panne)
    with pytest.raises((httpx.HTTPStatusError, httpx.TransportError)):
        _republier()
    assert envois == []


def test_resynchroniser_une_fiche_restreinte_ne_l_ouvre_pas(monkeypatch):
    restreinte = {**EXISTANTE, "access_grants": [{"id": "g1", "principal_type": "user", "principal_id": "ad49abb7", "permission": "read"}]}
    envois = _socle(monkeypatch, httpx.Response(200, json=restreinte))
    _republier(access_grants=[{"principal_type": "user", "principal_id": "*", "permission": "read"}], garder_les_droits=True)
    assert envois[0]["access_grants"] == [{"principal_type": "user", "principal_id": "ad49abb7", "permission": "read"}]


def test_resynchroniser_ne_cree_jamais_une_fiche(monkeypatch):
    from app.services.owui_client import FicheAbsente
    envois = _socle(monkeypatch, httpx.Response(404, json={"detail": "absent"}))
    with pytest.raises(FicheAbsente):
        _republier(garder_les_droits=True)
    assert envois == []
