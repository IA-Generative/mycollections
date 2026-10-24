"""Le débit d'indexation : suivi rapproché au début, envois simultanés réglables et bornés, débit
mesuré dans l'état du travail."""

from __future__ import annotations

import asyncio

from app.routers import ingest, sources_resana
from tests.unit.test_resana_routes import CREATEUR, _doc, _importer, faux, privee  # noqa: F401 — fixtures


def test_le_suivi_est_rapproche_au_debut_puis_s_espace(monkeypatch):
    monkeypatch.setattr(ingest, "SUIVI_DOCUMENT_S", 3.0)
    assert [ingest.pause_de_suivi(t) for t in (0, 14, 15, 59, 60, 600)] == [1.0, 1.0, 2.0, 2.0, 3.0, 3.0]
    monkeypatch.setattr(ingest, "SUIVI_DOCUMENT_S", 0.0)
    assert ingest.pause_de_suivi(0) == 0.0  # les tests n'attendent pas


def test_les_envois_simultanes_sont_reglables_et_bornes(monkeypatch):
    for reglage, attendu in ((4, 4), (8, 8), (0, 4), (50, 16), (-3, 1)):
        monkeypatch.setattr(sources_resana.settings, "resana_envois_paralleles", reglage)
        assert sources_resana.envois_paralleles() == attendu


def test_le_reglage_limite_vraiment_les_envois_et_le_debit_est_mesure(client, en_tant_que, faux, privee, monkeypatch):
    monkeypatch.setattr(sources_resana.settings, "resana_envois_paralleles", 2)
    faux.documents = [_doc(f"d{k}", f"# Note {k}\n\nTexte fictif numéro {k}.") for k in range(7)]
    en_vol = {"n": 0, "max": 0}

    async def indexer(job_id, collection, nom, contenu, metadata=None, file_id=None):
        en_vol["n"] += 1
        en_vol["max"] = max(en_vol["max"], en_vol["n"])
        await asyncio.sleep(0.02)
        en_vol["n"] -= 1
        return file_id, None, {"etat": "complet"}

    monkeypatch.setattr(sources_resana.depot, "_indexer_document_background", indexer)
    en_tant_que(CREATEUR)
    _importer(client, privee)
    assert en_vol["max"] == 2
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert travail["ajoutes"] == 7 and travail["envois_paralleles"] == 2 and travail["debit_docs_min"] > 0
