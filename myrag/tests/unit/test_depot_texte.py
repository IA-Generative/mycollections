"""Dépôt de documents (diagnostic d'octobre 2026) : le découpage maison ne lit que du texte, un
binaire inconnu est refusé, et seul qui gère la collection l'alimente. Les documents (PDF, Word…)
passent par OpenRAG : test_depot_documents.py."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers.ingest import texte_ou_refus
from tests.conftest import personne


@pytest.mark.parametrize("contenu", [b"%PDF-1.7\n...", b"PK\x03\x04docx", b"\x89PNG\r\n", b"abc\x00def", b"\xff\xfe\xfa\x80\x81"])
def test_un_fichier_qui_n_est_pas_du_texte_est_refuse_avec_une_explication(contenu):
    with pytest.raises(HTTPException) as e:
        texte_ou_refus(contenu, "x")
    assert e.value.status_code == 415 and "Formats acceptés" in e.value.detail


def test_le_texte_passe_en_utf8_et_en_windows():
    assert texte_ou_refus("Été".encode("utf-8"), "a.md") == "Été"
    assert texte_ou_refus("Été".encode("cp1252"), "a.txt") == "Été"


def test_seul_qui_gere_alimente_la_collection(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("simple-lecteur"))
    r = client.post(f"/api/ingest/{nom}", files={"file": ("a.md", b"# Titre\n\nTexte.", "text/markdown")})
    assert r.status_code == 403
    assert client.post(f"/api/ingest/{nom}/reindex").status_code == 403
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.upload_chunk = AsyncMock(return_value={})
        r = client.post(f"/api/ingest/{nom}", files={"file": ("a.md", b"# Titre\n\nTexte.", "text/markdown")})
    assert r.status_code == 200, r.text
    # Un binaire déguisé en texte, ou un format inconnu, reste refusé.
    r = client.post(f"/api/ingest/{nom}", files={"file": ("a.md", b"%PDF-1.7 binaire", "text/markdown")})
    assert r.status_code == 415
    r = client.post(f"/api/ingest/{nom}", files={"file": ("a.exe", b"MZ\x90\x00binaire", "application/octet-stream")})
    assert r.status_code == 415
