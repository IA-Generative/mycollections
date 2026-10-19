"""PDF, Word, PowerPoint… et le texte aussi : confiés tels quels à OpenRAG, qui les lit et
les découpe (ADR-0005) ; le travail suit la tâche d'OpenRAG jusqu'au bout et dit vrai
(réussi, ou en échec avec la raison)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.routers import ingest
from app.services import formats
from app.services.job_store import create_job, get_job, update_job
from app.services.openrag_client import EnvoiDocument, EtatTache, ResultatPartition
from tests.conftest import personne

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF"
DOCX = b"PK\x03\x04" + b"\x00" * 40


@pytest.mark.parametrize(
    "nom,contenu,attendu",
    [
        ("note.md", b"# Titre\n\nTexte.", "document"),
        ("note.txt", b"du texte", "document"),
        ("tableau.csv", b"a;b\n1;2", "texte"),
        ("note.markdown", b"# Titre", "texte"),
        ("sans-extension", b"du texte", "texte"),
        ("rapport.PDF", PDF, "document"),
        ("note.docx", DOCX, "document"),
        ("vieux.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 10, "document"),
        ("scan.jpg", b"\xff\xd8\xff\xe0", "document"),
        ("mail.eml", b"From: a@b\nSubject: x\n\ncorps", "document"),
        ("faux.pdf", b"ceci n'est pas un pdf", None),
        ("deguise.md", PDF, None),
        ("programme.exe", b"MZ\x90\x00", None),
    ],
)
def test_nature_d_un_fichier(nom, contenu, attendu):
    assert formats.nature(nom, contenu) == attendu


def test_types_mime_annonces_a_openrag():
    assert formats.type_mime("a.pdf") == "application/pdf"
    assert formats.type_mime("a.txt") == "text/plain"
    assert formats.type_mime("dossier/b.MD") == "text/markdown"
    assert formats.type_mime("dossier/b.PPTX").endswith("presentationml.presentation")


def _client(etats=("QUEUED", "RUNNING", "COMPLETED"), envoi=None, erreur=""):
    c = AsyncMock()
    c.create_partition = AsyncMock(return_value=ResultatPartition(status="ok"))
    c.upload_document = envoi or AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
    c.task_state = AsyncMock(side_effect=[EtatTache(task_state=e) for e in etats])
    c.task_error = AsyncMock(return_value=erreur)
    return c


@pytest.fixture(autouse=True)
def _suivi_rapide(monkeypatch):
    monkeypatch.setattr(ingest, "SUIVI_DOCUMENT_S", 0.0)


def test_un_pdf_part_tel_quel_et_le_travail_suit_la_tache(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value = _client()
        r = client.post(f"/api/ingest/{nom}", files={"file": ("rapport.pdf", PDF, "application/pdf")})
        assert r.status_code == 200, r.text
        assert r.json()["strategy"] == "openrag" and r.json()["total_chunks"] is None
        import time

        for _ in range(100):
            job = client.get(f"/api/ingest/jobs/{r.json()['job_id']}").json()
            if job["status"].startswith("done"):
                break
            time.sleep(0.02)
    envoi = cls.return_value.upload_document
    envoi.assert_awaited_once()
    partition, fichier, contenu, mime = envoi.await_args.args
    assert (partition, fichier, contenu, mime) == (nom, "rapport.pdf", PDF, "application/pdf")
    assert envoi.await_args.kwargs["metadata"]["sensitivity"] == "public"  # ADR-0005 — transmise à OpenRAG
    assert job["status"] == "done" and job["uploaded_chunks"] == 1 and job["failed_chunks"] == 0


def test_un_texte_part_entier_aussi_et_sa_sensibilite_voyage(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value = _client()
        r = client.post(
            f"/api/ingest/{nom}",
            data={"sensitivity": "internal"},
            files={"file": ("note.md", b"# Titre\n\nTexte.", "text/markdown")},
        )
        assert r.status_code == 200, r.text
        import time

        for _ in range(100):
            if cls.return_value.upload_document.await_count >= 1:
                break
            time.sleep(0.02)
    envoi = cls.return_value.upload_document
    assert envoi.await_args.args == (nom, "note.md", b"# Titre\n\nTexte.", "text/markdown")
    assert envoi.await_args.kwargs["metadata"] == {"title": "note.md", "sensitivity": "internal"}
    assert cls.return_value.upload_chunk.await_count == 0  # plus de découpage maison (ADR-0005)


@pytest.mark.asyncio
async def test_une_tache_en_echec_rend_le_travail_en_echec_avec_la_raison():
    job = await create_job("x", "a.pdf", "openrag", "public")
    with patch("app.routers.ingest.OpenRAGClient", return_value=_client(("RUNNING", "FAILED"), erreur="PDF chiffré")):
        await ingest._indexer_document_background(job["job_id"], "x", "a.pdf", PDF, "public")
    j = await get_job(job["job_id"])
    assert j is not None
    assert j["status"] == "done_with_errors" and "PDF chiffré" in j["error"]


@pytest.mark.asyncio
async def test_un_document_deja_present_compte_comme_reussi():
    job = await create_job("x", "a.pdf", "openrag", "public")
    reponse = httpx.Response(409, request=httpx.Request("POST", "http://o"))
    envoi = AsyncMock(side_effect=httpx.HTTPStatusError("conflit", request=reponse.request, response=reponse))
    with patch("app.routers.ingest.OpenRAGClient", return_value=_client(envoi=envoi)):
        await ingest._indexer_document_background(job["job_id"], "x", "a.pdf", PDF, "public")
    j = await get_job(job["job_id"])
    assert j is not None and j["status"] == "done"


@pytest.mark.asyncio
async def test_un_format_refuse_par_openrag_est_dit():
    job = await create_job("x", "a.pdf", "openrag", "public")
    reponse = httpx.Response(415, request=httpx.Request("POST", "http://o"))
    envoi = AsyncMock(side_effect=httpx.HTTPStatusError("refus", request=reponse.request, response=reponse))
    with patch("app.routers.ingest.OpenRAGClient", return_value=_client(envoi=envoi)):
        await ingest._indexer_document_background(job["job_id"], "x", "a.pdf", PDF, "public")
    j = await get_job(job["job_id"])
    assert j is not None
    assert j["status"] == "done_with_errors" and "format ou taille" in j["error"]


def test_trop_gros(client, en_tant_que, creer_collection, nom, monkeypatch):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    monkeypatch.setattr(ingest, "DOCUMENT_MAX_OCTETS", 10)
    r = client.post(f"/api/ingest/{nom}", files={"file": ("rapport.pdf", PDF, "application/pdf")})
    assert r.status_code == 413


def test_reindexer_une_collection(client, en_tant_que, creer_collection, nom):
    """Réindexer = maintenance (ADR-0005) : partition vidée, sources renvoyées telles
    quelles, sensibilité reprise par fichier — sans paramètre de découpage."""
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value = _client(etats=["COMPLETED"] * 4)
        cls.return_value.delete_partition = AsyncMock(return_value={})
        assert client.post(f"/api/ingest/{nom}", files={"file": ("a.pdf", PDF, "application/pdf")}).status_code == 200
        assert (
            client.post(
                f"/api/ingest/{nom}",
                data={"sensitivity": "internal"},
                files={"file": ("b.md", b"# B\n\nTexte.", "text/markdown")},
            ).status_code
            == 200
        )
        r = client.post(f"/api/ingest/{nom}/reindex")
        assert r.status_code == 200, r.text
        assert r.json()["files_reindexed"] == 2 and "strategy" not in r.json()
        # Les envois partent en tâche de fond : on les attend tant que le faux client est en place.
        import time

        for _ in range(100):
            if cls.return_value.upload_document.await_count >= 4:
                break
            time.sleep(0.02)
    assert cls.return_value.upload_document.await_count == 4  # chaque fichier, au dépôt puis à la réindexation
    # Les tâches de fond ne garantissent pas l'ordre des envois : on vérifie l'appariement
    # fichier ↔ sensibilité, qui doit être le même au dépôt et à la réindexation.
    envois = {(a.args[1], str(a.kwargs["metadata"]["sensitivity"])) for a in cls.return_value.upload_document.await_args_list}
    assert envois == {("a.pdf", "public"), ("b.md", "internal")}  # reprise par fichier à la réindexation
    cls.return_value.delete_partition.assert_awaited_once()


@pytest.mark.asyncio
async def test_un_document_interrompu_reprend_au_demarrage(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls, patch("app.routers.ingest._indexer_document_background", new=AsyncMock(return_value=None)):
        cls.return_value = _client()
        job_id = client.post(f"/api/ingest/{nom}", files={"file": ("a.pdf", PDF, "application/pdf")}).json()["job_id"]
    await update_job(job_id, status="uploading")
    with patch("app.routers.ingest.OpenRAGClient", return_value=_client(("COMPLETED",))) as cls:
        repris = await ingest.reprendre_les_travaux_interrompus()
    assert job_id in repris
    j = await get_job(job_id)
    assert j is not None and j["status"] == "done"
