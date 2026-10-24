"""Les scans (#145) : repérés avant l'envoi, envoyés quand même (l'indexeur les lit s'il a l'OCR),
comptés dans l'état d'une collection Résana, et accompagnés du conseil de déposer la version
électronique quand l'indexeur n'a rien pu en tirer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.routers import ingest, sources_resana
from app.services import formats
from app.services.job_store import create_job, get_job
from app.services.openrag_client import EnvoiDocument, EtatTache
from tests.unit._faux_resana import DocFaux
from tests.unit._pdf_fictif import PDF_SCAN, PDF_TEXTE
from tests.unit.test_resana_routes import CREATEUR, _importer, faux, privee  # noqa: F401 — fixtures


def test_un_pdf_sans_texte_est_un_scan():
    assert formats.est_un_scan("releve.pdf", PDF_SCAN)
    assert not formats.est_un_scan("releve.pdf", PDF_TEXTE)
    # Ni un autre format, ni un PDF qu'on ne sait pas lire : l'indexeur dira ce qu'il en est.
    assert not formats.est_un_scan("releve.docx", PDF_SCAN)
    assert not formats.est_un_scan("abime.pdf", b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF")


def _client(etat: str, erreur: str = ""):
    c = AsyncMock()
    c.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
    c.task_state = AsyncMock(return_value=EtatTache(task_state=etat))
    c.task_error = AsyncMock(return_value=erreur)
    return c


@pytest.fixture(autouse=True)
def _suivi_rapide(monkeypatch):
    monkeypatch.setattr(ingest, "SUIVI_DOCUMENT_S", 0.0)


@pytest.mark.asyncio
async def test_un_scan_part_marque_et_son_echec_dit_quoi_faire():
    job = await create_job("x", "releve.pdf", "openrag", "public")
    client = _client("FAILED", "NoIndexableContentError: NO_INDEXABLE_CONTENT")
    with patch("app.routers.ingest.OpenRAGClient", return_value=client):
        _, erreur, qualite = await ingest._indexer_document_background(job["job_id"], "x", "releve.pdf", PDF_SCAN)
    assert client.upload_document.await_args.kwargs["metadata"]["scan"] is True
    assert qualite == {"etat": "sans_texte"} and "de préférence non signée" in erreur
    j = await get_job(job["job_id"])
    assert j is not None and "version électronique" in j["error"]


@pytest.mark.asyncio
async def test_un_pdf_electronique_ne_porte_ni_marque_ni_conseil():
    job = await create_job("x", "note.pdf", "openrag", "public")
    client = _client("COMPLETED")
    with patch("app.routers.ingest.OpenRAGClient", return_value=client):
        _, erreur, _ = await ingest._indexer_document_background(job["job_id"], "x", "note.pdf", PDF_TEXTE)
    assert "scan" not in client.upload_document.await_args.kwargs["metadata"] and erreur is None


def test_les_scans_resana_sont_comptes(client, en_tant_que, faux, privee, monkeypatch):
    faux.documents[:] = [
        DocFaux(id="s1", titre="Relevé fictif 1", nom_fichier="releve-1.pdf", contenu=PDF_SCAN, mime="application/pdf"),
        DocFaux(id="s2", titre="Relevé fictif 2", nom_fichier="releve-2.pdf", contenu=PDF_SCAN + b"\n% autre", mime="application/pdf"),
        DocFaux(id="t1", titre="Note fictive", nom_fichier="note.pdf", contenu=PDF_TEXTE, mime="application/pdf"),
    ]
    envois: dict[str, dict] = {}

    async def indexer(job_id, collection, nom, contenu, metadata=None, file_id=None):
        envois[nom] = metadata or {}
        # L'indexeur a l'OCR pour le premier scan, pas pour le second.
        if nom == "releve-2.pdf":
            return file_id, "OpenRAG n'a pas pu lire : NO_INDEXABLE_CONTENT", {"etat": "sans_texte"}
        return file_id, None, {"etat": "complet", "passages": 2, "sans_contexte": 0}

    monkeypatch.setattr(sources_resana.depot, "_indexer_document_background", indexer)
    en_tant_que(CREATEUR)
    assert _importer(client, privee).status_code == 200
    assert envois["releve-1.pdf"].get("scan") and envois["releve-2.pdf"].get("scan") and "scan" not in envois["note.pdf"]
    qualite = client.get(f"/api/sources/resana/status/{privee}").json()["qualite"]
    assert (qualite["scans"], qualite["scans_lus"]) == (2, 1)
    assert qualite["par_etat"] == {"complet": 2, "sans_texte": 1}


def test_le_script_de_marquage_ne_touche_que_les_identifiants_listes():
    from scripts.marquer_scans import marquer

    documents = {
        "1": {"file_id": "resana-1-aa", "erreur": "n'a pas pu lire"},
        "2": {"file_id": "resana-2-bb"},
        "3": {"file_id": "resana-3-cc"},
    }
    assert marquer(documents, {"resana-2-bb", "resana-9-zz"}, "sans_texte") == ["2"]
    assert documents["2"] == {"file_id": "resana-2-bb", "scan": True, "qualite": {"etat": "sans_texte"}}
    assert "scan" not in documents["3"]
    # Relu par OCR : complet, et l'ancienne erreur s'efface.
    assert marquer(documents, {"resana-1-aa"}, "complet") == ["1"]
    assert documents["1"] == {"file_id": "resana-1-aa", "scan": True, "qualite": {"etat": "complet"}}
    assert sources_resana.bilan_qualite({"documents": documents})["scans_lus"] == 1
