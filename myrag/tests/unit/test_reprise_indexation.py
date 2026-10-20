"""Diagnostic d'octobre 2026, P2 : une indexation en cours était perdue au redémarrage du
backend — la tâche de fond disparaissait, le travail restait « uploading » pour toujours.
Écrit avant le correctif : au démarrage, les travaux interrompus reprennent depuis le
fichier source conservé, renvoyé entier à OpenRAG qui le découpe (ADR-0005) ; sans fichier,
ils sont marqués « interrompu » avec ce qu'il faut faire. Un document déjà indexé
(OpenRAG répond 409) compte comme réussi."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tests.conftest import personne


def _deposer(client, nom):
    return client.post(f"/api/ingest/{nom}", files={"file": ("note.md", b"# T\n\nPremier.\n\n## S\n\nSecond.", "text/markdown")})


@pytest.mark.asyncio
async def test_un_travail_interrompu_reprend_au_demarrage(client, en_tant_que, creer_collection, nom):
    from app.routers import ingest
    from app.services.job_store import get_job, update_job

    creer_collection(nom)
    en_tant_que(personne("createur"))
    # Le dépôt s'arrête avant l'envoi à OpenRAG : la tâche de fond ne tourne pas (comme un pod
    # arrêté juste après l'enregistrement de la source), et ne peut donc pas finir le travail
    # en concurrence du test.
    with patch("app.routers.ingest.OpenRAGClient") as cls, patch("app.routers.ingest._indexer_document_background", new=AsyncMock(return_value=None)):
        cls.return_value.create_partition = AsyncMock(return_value={})
        job_id = _deposer(client, nom).json()["job_id"]
    await update_job(job_id, status="uploading", uploaded_chunks=0, failed_chunks=0)  # comme après un arrêt

    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.upload_document = AsyncMock(return_value=SimpleNamespace(task_id="t1"))
        cls.return_value.task_state = AsyncMock(return_value=SimpleNamespace(task_state="COMPLETED"))
        repris = await ingest.reprendre_les_travaux_interrompus()
    assert job_id in repris
    job = await get_job(job_id)
    assert job is not None
    assert job["status"] == "done", job


@pytest.mark.asyncio
async def test_sans_fichier_source_le_travail_est_dit_interrompu(client, en_tant_que, creer_collection, nom):
    from app.routers import ingest
    from app.services.job_store import create_job, get_job, update_job

    creer_collection(nom)
    job = await create_job(nom, "disparu.md", "openrag", "public")
    await update_job(job["job_id"], status="uploading")
    await ingest.reprendre_les_travaux_interrompus()
    apres = await get_job(job["job_id"])
    assert apres is not None
    assert apres["status"] == "interrupted" and "redéposez" in (apres.get("error") or "")


@pytest.mark.asyncio
async def test_un_fichier_illisible_n_arrete_pas_la_reprise(client, en_tant_que, creer_collection, nom):
    """Un fichier conservé illisible (permissions, secteur défaillant) tuait la reprise
    entière : ce travail dit quoi faire, les suivants reprennent."""
    from pathlib import Path

    from app.config import settings
    from app.routers import ingest
    from app.services.job_store import get_job, update_job

    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls, patch("app.routers.ingest._indexer_document_background", new=AsyncMock(return_value=None)):
        cls.return_value.create_partition = AsyncMock(return_value={})
        bon = _deposer(client, nom).json()["job_id"]
        mauvais = client.post(f"/api/ingest/{nom}", files={"file": ("annexe.md", b"# A\n\nTexte.", "text/markdown")}).json()["job_id"]
    await update_job(bon, status="uploading", uploaded_chunks=0, failed_chunks=0)
    await update_job(mauvais, status="uploading", uploaded_chunks=0, failed_chunks=0)

    # Le fichier du second travail devient illisible : un répertoire à sa place.
    chemin = Path(settings.data_dir) / "_sources" / nom / "annexe.md"
    chemin.unlink()
    chemin.mkdir()
    try:
        with patch("app.routers.ingest.OpenRAGClient") as cls:
            cls.return_value.upload_document = AsyncMock(return_value=SimpleNamespace(task_id="t1"))
            cls.return_value.task_state = AsyncMock(return_value=SimpleNamespace(task_state="COMPLETED"))
            repris = await ingest.reprendre_les_travaux_interrompus()
    finally:
        chemin.rmdir()
    assert mauvais not in repris and bon in repris
    j = await get_job(mauvais)
    assert j is not None and j["status"] == "interrupted" and "redéposez" in (j.get("error") or "")
    j = await get_job(bon)
    assert j is not None and j["status"] == "done"


@pytest.mark.asyncio
async def test_un_document_deja_indexe_compte_comme_reussi(client, en_tant_que, creer_collection, nom):
    from app.routers import ingest
    from app.services.job_store import create_job, get_job

    creer_collection(nom)
    job = await create_job(nom, "x.md", "openrag", "public")
    deja = httpx.HTTPStatusError("409", request=httpx.Request("POST", "http://o"), response=httpx.Response(409))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.upload_document = AsyncMock(side_effect=deja)
        await ingest._indexer_document_background(job["job_id"], nom, "x.md", b"texte entier", "public")
    j = await get_job(job["job_id"])
    assert j is not None and j["status"] == "done"
