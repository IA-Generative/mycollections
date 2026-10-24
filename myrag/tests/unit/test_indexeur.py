"""L'indexeur : OpenRAG derrière une interface, et un autre moteur qui le remplace sans toucher aux
sources (ici : l'import Résana, joué avec un indexeur en mémoire)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.indexeur import DejaPresent, Envoi, IndexeurOpenRAG, Refuse, Suivi, qualite_echec, qualite_lecture
from app.services.openrag_client import EnvoiDocument, EtatTache


def _erreur(statut: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://openrag"), response=httpx.Response(statut))


@pytest.mark.asyncio
async def test_openrag_traduit_ses_reponses():
    client = MagicMock()
    client.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f-1", task_id="t-1"))
    client.task_state = AsyncMock(side_effect=[EtatTache(task_state="RUNNING"), EtatTache(task_state="SUCCESS"), EtatTache(task_state="FAILED")])
    client.task_error = AsyncMock(return_value="NoIndexableContent")
    idx = IndexeurOpenRAG(client)
    assert await idx.envoyer("c", "a.pdf", b"%PDF", mime="application/pdf", metadata={}, identifiant="f-1") == Envoi("f-1", "t-1")
    assert client.upload_document.await_args.kwargs["file_id"] == "f-1"
    assert [await idx.suivre("t-1") for _ in range(3)] == [Suivi("en_cours"), Suivi("lu"), Suivi("echec", "NoIndexableContent")]

    client.upload_document = AsyncMock(side_effect=_erreur(409))
    with pytest.raises(DejaPresent):
        await idx.envoyer("c", "a.pdf", b"%PDF", mime="application/pdf", metadata={}, identifiant="f-1")
    client.upload_document = AsyncMock(side_effect=_erreur(413))
    with pytest.raises(Refuse) as e:
        await idx.envoyer("c", "a.pdf", b"%PDF", mime="application/pdf", metadata={})
    assert e.value.statut == 413


def test_qualite_d_un_document_lu():
    # OpenRAG 2.3 : étapes en échec (liste ou dictionnaire) et compte des passages sans contexte.
    assert qualite_lecture(None) is None
    assert qualite_lecture({"file_id": "f"}) is None  # l'indexeur ne dit rien : on ne sait pas
    assert qualite_lecture({"degraded_stages": []}) == {"etat": "complet"}
    assert qualite_lecture({"degraded_stages": {}, "contextualization": {"total": 12, "failed": 0}}) == {"etat": "complet", "passages": 12, "sans_contexte": 0}
    assert qualite_lecture({"degraded_stages": {"contextualize": "429"}, "contextualization": {"total": 17, "failed": 7}}) == {
        "etat": "sans_contexte",
        "passages": 17,
        "sans_contexte": 7,
        "etapes": ["contextualize"],
    }
    assert qualite_lecture({"degraded_stages": ["contextualize"]})["etat"] == "sans_contexte"
    assert qualite_lecture({"degraded_stages": ["caption"]}) == {"etat": "degrade", "etapes": ["caption"]}
    assert qualite_echec("NoIndexableContentError: NO_INDEXABLE_CONTENT: No indexable content") == {"etat": "sans_texte"}
    assert qualite_echec("PDF chiffré") == {"etat": "echec"}


@pytest.mark.asyncio
async def test_openrag_rend_la_qualite_avec_la_lecture():
    client = MagicMock()
    details = {"degraded_stages": {"contextualize": "x"}, "contextualization": {"total": 4, "failed": 1}}
    client.task_state = AsyncMock(side_effect=[EtatTache(task_state="COMPLETED", details=details), EtatTache(task_state="COMPLETED_DEGRADED", details={"degraded_stages": []})])
    idx = IndexeurOpenRAG(client)
    assert await idx.suivre("t") == Suivi("lu", qualite={"etat": "sans_contexte", "passages": 4, "sans_contexte": 1, "etapes": ["contextualize"]})
    assert (await idx.suivre("t")).qualite == {"etat": "complet"}


class IndexeurEnMemoire:
    """Un autre moteur, le plus simple possible : il garde les documents dans un dictionnaire."""

    nom = "memoire"

    def __init__(self):
        self.documents: dict[tuple[str, str], dict] = {}

    async def preparer(self, collection):
        pass

    async def envoyer(self, collection, nom, contenu, *, mime, metadata, identifiant=None):
        ident = identifiant or nom
        if (collection, ident) in self.documents:
            raise DejaPresent(ident)
        self.documents[(collection, ident)] = {"nom": nom, "taille": len(contenu), **metadata}
        return Envoi(ident, "")

    async def suivre(self, tache):
        return Suivi("lu")

    async def retirer(self, collection, identifiant):
        self.documents.pop((collection, identifiant), None)

    async def vider(self, collection):
        for cle in [c for c in self.documents if c[0] == collection]:
            del self.documents[cle]


from tests.unit.test_resana_routes import faux, privee  # noqa: E402, F401 — fixtures


def test_un_autre_indexeur_remplace_openrag_pour_resana(client, en_tant_que, faux, privee, monkeypatch):
    from app.routers import ingest
    from tests.unit.test_resana_routes import CREATEUR, ENTETE, _doc, _importer

    memoire = IndexeurEnMemoire()
    monkeypatch.setattr(ingest, "_indexeur", lambda timeout=300.0: memoire)
    en_tant_que(CREATEUR)
    _importer(client, privee)
    assert sorted(v["nom"] for v in memoire.documents.values()) == ["note-a.md", "note-b.md"]
    assert all(v["url"].startswith("https://") for v in memoire.documents.values())

    faux.documents = [_doc("b", "# B\n\nDeuxième texte fictif, corrigé.")]
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert [v["nom"] for v in memoire.documents.values()] == ["note-b.md"] and len(memoire.documents) == 1
    assert not faux.openrag.upload_document.await_count, "OpenRAG n'a rien reçu"
