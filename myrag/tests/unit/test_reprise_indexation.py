"""Diagnostic d'octobre 2026, P2 : une indexation en cours était perdue au redémarrage du
backend — la tâche de fond disparaissait, le travail restait « uploading » pour toujours.
Écrit avant le correctif : au démarrage, les travaux interrompus reprennent depuis le fichier
source conservé ; sans fichier, ils sont marqués « interrompu » avec ce qu'il faut faire. Un
morceau déjà indexé à l'identique (OpenRAG répond 409) compte comme réussi."""

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
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.upload_chunk = AsyncMock(side_effect=RuntimeError("pod arrêté"))
        job_id = _deposer(client, nom).json()["job_id"]
    await update_job(job_id, status="uploading", uploaded_chunks=0, failed_chunks=0)  # comme après un arrêt

    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.upload_chunk = AsyncMock(return_value={})
        repris = await ingest.reprendre_les_travaux_interrompus()
    assert job_id in repris
    job = await get_job(job_id)
    assert job["status"] == "done", job


@pytest.mark.asyncio
async def test_sans_fichier_source_le_travail_est_dit_interrompu(client, en_tant_que, creer_collection, nom):
    from app.routers import ingest
    from app.services.job_store import create_job, get_job, update_job
    creer_collection(nom)
    job = await create_job(nom, "disparu.md", "auto", "public")
    await update_job(job["job_id"], status="uploading")
    await ingest.reprendre_les_travaux_interrompus()
    apres = await get_job(job["job_id"])
    assert apres["status"] == "interrupted" and "redéposez" in (apres.get("error") or "")


@pytest.mark.asyncio
async def test_un_morceau_deja_indexe_compte_comme_reussi(client, en_tant_que, creer_collection, nom):
    from app.routers import ingest
    from app.services.job_store import create_job, get_job
    creer_collection(nom)
    job = await create_job(nom, "x.md", "auto", "public")
    deja = httpx.HTTPStatusError("409", request=httpx.Request("POST", "http://o"), response=httpx.Response(409))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.upload_chunk = AsyncMock(side_effect=deja)
        await ingest._upload_chunks_background(job["job_id"], nom, [{"content": "a"}, {"content": "b"}])
    assert (await get_job(job["job_id"]))["status"] == "done"
