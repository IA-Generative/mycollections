"""Dépôt de fichiers (ADR-0005) : tout fichier accepté part entier vers OpenRAG, qui le
découpe. Un binaire inconnu, un binaire déguisé en texte, un CSV ou un .markdown sont
refusés avec une explication, et seul qui gère la collection l'alimente. Le suivi du
travail et des tâches OpenRAG : test_depot_documents.py."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services import formats
from tests.conftest import personne


@pytest.mark.parametrize("contenu", [b"%PDF-1.7\n...", b"PK\x03\x04docx", b"\x89PNG\r\n", b"abc\x00def", b"MZ\x90\x00binaire"])
def test_un_fichier_qui_n_est_pas_du_texte_n_est_pas_confie_a_openrag(contenu):
    assert formats.nature("x", contenu) is None


def test_le_texte_part_entier_le_csv_et_le_markdown_restent_locaux():
    assert formats.nature("a.md", "Été".encode("utf-8")) is formats.Nature.DOCUMENT
    assert formats.nature("a.txt", "Été".encode("cp1252")) is formats.Nature.DOCUMENT
    assert formats.nature("a.csv", b"a,b\n1,2") is formats.Nature.TEXTE  # lisible localement (graphe), refusé au dépôt
    assert formats.nature("a.markdown", b"# Titre") is formats.Nature.TEXTE
    assert formats.nature("a.md", b"%PDF-1.7 binaire") is None  # l'extension ment


def test_seul_qui_gere_alimente_la_collection(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("simple-lecteur"))
    r = client.post(f"/api/ingest/{nom}", files={"file": ("a.md", b"# Titre\n\nTexte.", "text/markdown")})
    assert r.status_code == 403
    assert client.post(f"/api/ingest/{nom}/reindex").status_code == 403
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.upload_document = AsyncMock(return_value=AsyncMock(task_id="t1"))
        cls.return_value.task_state = AsyncMock(return_value=AsyncMock(task_state="COMPLETED"))
        r = client.post(f"/api/ingest/{nom}", files={"file": ("a.md", b"# Titre\n\nTexte.", "text/markdown")})
    assert r.status_code == 200, r.text
    # Un binaire déguisé en texte, un format inconnu, un CSV : refusés au dépôt.
    r = client.post(f"/api/ingest/{nom}", files={"file": ("a.md", b"%PDF-1.7 binaire", "text/markdown")})
    assert r.status_code == 415
    r = client.post(f"/api/ingest/{nom}", files={"file": ("a.exe", b"MZ\x90\x00binaire", "application/octet-stream")})
    assert r.status_code == 415
    r = client.post(f"/api/ingest/{nom}", files={"file": ("a.csv", b"a,b\n1,2", "text/csv")})
    assert r.status_code == 415 and "convertissez" in r.json()["detail"]
    # Un fichier vide ne part pas vers OpenRAG.
    r = client.post(f"/api/ingest/{nom}", files={"file": ("a.md", b"", "text/markdown")})
    assert r.status_code == 400
