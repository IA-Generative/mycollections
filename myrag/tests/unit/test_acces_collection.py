"""Le bloc « Où interroger cette collection » : promis seulement quand c'est servi."""

from app.routers.collections import acces_a_la_collection
from app.config import settings


def test_rien_tant_que_la_collection_n_est_pas_publiee_a_tous():
    assert acces_a_la_collection({"name": "x", "etat_collab": "amorcee", "publication": {"state": "draft"}}) is None
    assert acces_a_la_collection({"name": "x", "etat_collab": "publiee_groupe",
                                  "publication": {"state": "published", "visibility": "group"}}) is None


def test_publiee_a_tous_donne_l_assistant_et_l_api(monkeypatch):
    monkeypatch.setattr(settings, "openrag_public_url", "https://api.openrag.exemple/")
    a = acces_a_la_collection({"name": "dgef-sdst-faq", "etat_collab": "publiee_tous", "publication": {}})
    assert a["assistant"] == {"model_id": "openrag-dgef-sdst-faq"}
    assert a["api"]["chat"] == "https://api.openrag.exemple/v1/chat/completions" and a["api"]["model"] == "openrag-dgef-sdst-faq"


def test_sans_adresse_publique_l_api_n_est_pas_promise(monkeypatch):
    monkeypatch.setattr(settings, "openrag_public_url", "")
    monkeypatch.setattr(settings, "openrag_url", "http://openrag:8080")
    a = acces_a_la_collection({"name": "x", "etat_collab": "publiee_tous", "publication": {}})
    assert a["assistant"] and a["api"] is None
