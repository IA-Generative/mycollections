"""Archiver un assistant : il quitte la liste, ne répond plus (moteur, extension), reste lisible par
qui le gère, ne se modifie plus avant d'être désarchivé ; un assistant miroir suit sa collection."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import personne

ALICE = personne("alice-archive")
LECTEUR = personne("lecteur-archive")


@pytest.fixture
def col(creer_collection, purger):
    nom = f"t-archive-{uuid.uuid4().hex[:6]}"
    creer_collection(nom, ALICE, titre="Collection d'exemple")
    yield nom
    purger(nom)


def _fiche(ident, col):
    return {"assistant": ident, "titre": "Assistant d'exemple", "sources": [{"id": col, "type": "collection", "regime": "toujours", "rang": 1}]}


def test_archiver_retire_et_desarchiver_retablit(client, en_tant_que, col, ident_assistant):
    en_tant_que(ALICE)
    assert client.put(f"/api/assistants/{ident_assistant}", json=_fiche(ident_assistant, col)).status_code == 200
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    en_tant_que(LECTEUR)
    assert client.post(f"/api/assistants/{ident_assistant}/archiver").status_code == 403
    en_tant_que(ALICE)
    r = client.post(f"/api/assistants/{ident_assistant}/archiver")
    assert r.status_code == 200 and r.json() == {"assistant": ident_assistant, "archive": True}
    assert ident_assistant not in {a["id"] for a in client.get("/api/assistants").json()["assistants"]}
    assert client.get(f"/api/assistants/{ident_assistant}").status_code == 200, "qui le gère le retrouve par son adresse"
    assert client.put(f"/api/assistants/{ident_assistant}", json=_fiche(ident_assistant, col)).status_code == 409
    en_tant_que(LECTEUR)
    assert client.post(f"/api/v1/assistants/{ident_assistant}/executer", json={"question": "Une question ?"}).status_code == 404
    en_tant_que(ALICE)
    assert client.post(f"/api/assistants/{ident_assistant}/desarchiver").json() == {"assistant": ident_assistant, "archive": False}
    assert ident_assistant in {a["id"] for a in client.get("/api/assistants").json()["assistants"]}


def test_un_assistant_archive_n_est_plus_propose_par_l_extension(client, en_tant_que, col, ident_assistant):
    en_tant_que(ALICE)
    assert client.put(f"/api/assistants/{ident_assistant}", json=_fiche(ident_assistant, col)).status_code == 200
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    assert client.put(f"/api/assistants/{ident_assistant}/sites", json={"motifs": ["https://www.fake-domain.name/archive/*"]}).status_code == 200
    cibles = lambda: {c["id"] for s in client.get("/api/v1/sites").json()["sites"] for c in s["cibles"]}  # noqa: E731
    assert ident_assistant in cibles()
    assert client.post(f"/api/assistants/{ident_assistant}/archiver").status_code == 200
    assert ident_assistant not in cibles()


def test_un_assistant_miroir_suit_sa_collection(client, en_tant_que, col):
    import asyncio

    from app.services import assistant_store

    ident = f"t-miroir-{uuid.uuid4().hex[:6]}"

    async def poser_miroir():
        from app.harnais.contrat import FicheAssistant

        fiche = FicheAssistant.model_validate(_fiche(ident, col))
        await assistant_store.enregistrer_brouillon(fiche, auteur_hash="robot-test", collection_name=col)

    asyncio.run(poser_miroir())
    en_tant_que(ALICE)
    r = client.post(f"/api/assistants/{ident}/archiver")
    assert r.status_code == 409 and "collection" in r.json()["detail"]
