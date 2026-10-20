"""Réindexer ne double plus le corpus (diagnostic d'octobre 2026, P1) — et ne vide la
partition qu'une fois chaque source vérifiée : format, taille, présence."""

import os
import pathlib
import sqlite3
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.routers import ingest
from app.services.openrag_client import EnvoiDocument, EtatTache
from tests.conftest import personne


def _deposer(client, nom, contenu=b"# Titre\n\nPremier paragraphe.\n\n## Section\n\nSecond paragraphe."):
    return client.post(f"/api/ingest/{nom}", files={"file": ("note.md", contenu, "text/markdown")})


def _sources(client, nom):
    return client.get(f"/api/ingest/{nom}/sources").json()


def test_redeposer_ou_reindexer_ne_duplique_ni_les_sources_ni_le_corpus(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_chunk = AsyncMock(return_value={})
        assert _deposer(client, nom).status_code == 200
        assert _deposer(client, nom).status_code == 200
        r = client.post(f"/api/ingest/{nom}/reindex")
        assert r.status_code == 200, r.text
        assert r.json()["files_reindexed"] == 1
        r = client.post(f"/api/ingest/{nom}/reindex")
        assert r.status_code == 200
        cls.return_value.delete_partition.assert_awaited_with(nom)
    sources = _sources(client, nom)
    liste = sources.get("sources", sources) if isinstance(sources, dict) else sources
    assert len([s for s in liste if s.get("filename") == "note.md"]) == 1


def test_une_source_disparue_est_refusee_sans_rien_effacer(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_chunk = AsyncMock(return_value={})
        _deposer(client, nom)

        for f in (pathlib.Path(settings.data_dir) / "_sources" / nom).glob("*"):
            os.remove(f)
        r = client.post(f"/api/ingest/{nom}/reindex")
        assert r.status_code == 409
        cls.return_value.delete_partition.assert_not_awaited()


def test_une_source_trop_grosse_est_refusee_avant_d_effacer_la_partition(client, en_tant_que, creer_collection, nom, monkeypatch):
    """Un fichier au-dessus de la limite passait les vérifications, et la partition était
    vidée avant que l'envoi n'échoue (413) : la collection restait vide. Refusée avant."""
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
        cls.return_value.task_state = AsyncMock(return_value=EtatTache(task_state="COMPLETED"))
        assert _deposer(client, nom).status_code == 200
        monkeypatch.setattr(ingest, "DOCUMENT_MAX_OCTETS", 10)
        r = client.post(f"/api/ingest/{nom}/reindex")
        assert r.status_code == 413, r.text
        cls.return_value.delete_partition.assert_not_awaited()


def test_une_source_devenue_inacceptable_se_retire_puis_la_reindexation_passe(client, en_tant_que, creer_collection, nom):
    """Une source .csv acceptée avant l'ADR-0005 bloquait la réindexation pour toujours :
    la redéposer convertie ajoute une ligne, l'ancienne reste. Elle se retire maintenant."""
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
        cls.return_value.task_state = AsyncMock(return_value=EtatTache(task_state="COMPLETED"))
        assert _deposer(client, nom).status_code == 200

    # Une source .csv d'avant l'ADR-0005, posée à la main (le dépôt la refuse désormais).
    dossier = pathlib.Path(settings.data_dir) / "_sources" / nom
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "tableau.csv").write_bytes(b"a;b\n1;2")
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    con.execute(
        "INSERT INTO source_files (collection_name, filename, original_url, storage_path, file_size, content_type, "
        "checksum, strategy_used, chunks_produced, sensitivity, created_at) "
        "VALUES (?, 'tableau.csv', '', ?, 7, 'text/csv', 'x', 'section-v2', 0, 'public', datetime('now'))",
        (nom, str(dossier / "tableau.csv")),
    )
    con.commit()
    con.close()

    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
        cls.return_value.task_state = AsyncMock(return_value=EtatTache(task_state="COMPLETED"))
        r = client.post(f"/api/ingest/{nom}/reindex")
        assert r.status_code == 415, r.text
        cls.return_value.delete_partition.assert_not_awaited()

        sources = _sources(client, nom)
        liste = sources.get("sources", sources) if isinstance(sources, dict) else sources
        csv_id = next(s["id"] for s in liste if s["filename"] == "tableau.csv")
        r = client.delete(f"/api/ingest/{nom}/sources/{csv_id}")
        assert r.status_code == 200, r.text
        assert not (dossier / "tableau.csv").exists(), "le fichier conservé disparaît aussi"

        r = client.post(f"/api/ingest/{nom}/reindex")
        assert r.status_code == 200 and r.json()["files_reindexed"] == 1, r.text


def test_retirer_la_derniere_source_vide_aussi_la_partition(client, en_tant_que, creer_collection, nom):
    """La réindexation refuse une collection sans sources (400) : les passages de la
    dernière source retirée seraient restés indépurables. La partition est vidée
    d'abord — si OpenRAG ne répond pas, rien n'est effacé."""
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
        cls.return_value.task_state = AsyncMock(return_value=EtatTache(task_state="COMPLETED"))
        assert _deposer(client, nom).status_code == 200
        assert client.post(f"/api/ingest/{nom}", files={"file": ("annexe.md", b"# A\n\nTexte.", "text/markdown")}).status_code == 200
        sources = _sources(client, nom)
        liste = sources.get("sources", sources) if isinstance(sources, dict) else sources
        ids = {s["filename"]: s["id"] for s in liste}

        r = client.delete(f"/api/ingest/{nom}/sources/{ids['note.md']}")
        assert r.status_code == 200, r.text
        cls.return_value.delete_partition.assert_not_awaited(), "il reste une source : la partition garde ses passages"

        cls.return_value.delete_partition.reset_mock()
        cls.return_value.create_partition.reset_mock()
        r = client.delete(f"/api/ingest/{nom}/sources/{ids['annexe.md']}")
        assert r.status_code == 200, r.text
        cls.return_value.delete_partition.assert_awaited_once_with(nom)
        cls.return_value.create_partition.assert_awaited_once_with(nom)
        assert _sources(client, nom)["sources"] == []


def test_un_fichier_partage_par_des_doublons_ne_disparait_avec_la_premiere_ligne(client, en_tant_que, creer_collection, nom):
    """Avant l'ADR-0005, des lignes en double désignaient le même fichier ; la
    réindexation n'en garde qu'une. Retirer l'une ne doit pas effacer le fichier sous
    l'autre — seulement avec la dernière."""
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        cls.return_value.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
        cls.return_value.task_state = AsyncMock(return_value=EtatTache(task_state="COMPLETED"))
        assert _deposer(client, nom).status_code == 200

    # Un doublon d'avant l'ADR-0005 : deux lignes, un même fichier conservé.
    dossier = pathlib.Path(settings.data_dir) / "_sources" / nom
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    chemin = con.execute("SELECT storage_path FROM source_files WHERE collection_name=? AND filename='note.md'", (nom,)).fetchone()[0]
    con.execute(
        "INSERT INTO source_files (collection_name, filename, original_url, storage_path, file_size, content_type, "
        "checksum, strategy_used, chunks_produced, sensitivity, created_at) "
        "VALUES (?, 'note.md', '', ?, 10, 'text/markdown', 'x', 'section-v2', 0, 'public', datetime('now'))",
        (nom, chemin),
    )
    con.commit()
    con.close()

    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.delete_partition = AsyncMock(return_value={})
        sources = _sources(client, nom)
        liste = sources.get("sources", sources) if isinstance(sources, dict) else sources
        ids = [s["id"] for s in liste if s["filename"] == "note.md"]
        assert len(ids) == 2

        r = client.delete(f"/api/ingest/{nom}/sources/{ids[0]}")
        assert r.status_code == 200, r.text
        assert (dossier / "note.md").exists(), "l'autre ligne désigne encore ce fichier"
        cls.return_value.delete_partition.assert_not_awaited(), "une ligne reste : la partition garde ses passages"

        r = client.delete(f"/api/ingest/{nom}/sources/{ids[1]}")
        assert r.status_code == 200, r.text
        assert not (dossier / "note.md").exists(), "avec la dernière ligne, le fichier disparaît"
        cls.return_value.delete_partition.assert_awaited_once_with(nom)


def test_retirer_une_source_exige_la_gestion_et_connait_la_collection(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
        cls.return_value.task_state = AsyncMock(return_value=EtatTache(task_state="COMPLETED"))
        assert _deposer(client, nom).status_code == 200
        sources = _sources(client, nom)
        liste = sources.get("sources", sources) if isinstance(sources, dict) else sources
        source_id = liste[0]["id"]

    en_tant_que(personne("simple-lecteur"))  # le groupe des testeurs lit, ne gère pas
    r = client.delete(f"/api/ingest/{nom}/sources/{source_id}")
    assert r.status_code == 403, r.text

    en_tant_que(personne("createur"))
    assert client.delete(f"/api/ingest/{nom}/sources/99999").status_code == 404
    assert client.delete(f"/api/ingest/autre-collection/sources/{source_id}").status_code == 404
