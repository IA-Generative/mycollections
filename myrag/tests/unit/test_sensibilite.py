"""La liste des sensibilités (#134) : six niveaux, les anciennes valeurs lues et réécrites vers un
niveau jamais moins protecteur, une valeur inconnue refusée."""

import asyncio
import os
import sqlite3

import pytest

from app.services.chunker import Sensitivity, valider_sensibilite
from tests.conftest import personne


def test_la_liste_des_sensibilites():
    assert [s.value for s in Sensitivity] == ["public", "internal", "personal", "personal_sensitive", "controlled", "restricted"]


@pytest.mark.parametrize("ancienne", ["confidential", "secret"])
def test_une_ancienne_valeur_devient_diffusion_restreinte(ancienne):
    assert Sensitivity(ancienne) is Sensitivity.RESTRICTED
    assert valider_sensibilite(ancienne) is Sensitivity.RESTRICTED


def test_une_valeur_inconnue_n_est_pas_une_sensibilite():
    assert valider_sensibilite("tres-secret") is None


def test_la_creation_range_une_ancienne_valeur_et_refuse_l_inconnue(client, creer_collection, nom, en_tant_que):
    assert creer_collection(nom, sensitivity="confidential")["sensitivity"] == "restricted"
    en_tant_que(personne("createur"))
    r = client.post("/api/collections", json={"name": f"{nom}-x", "scope": "private", "sensitivity": "tres-secret"})
    assert r.status_code == 422


def test_la_fiche_change_de_sensibilite(client, creer_collection, nom, en_tant_que):
    creer_collection(nom)
    en_tant_que(personne("createur"))
    assert client.patch(f"/api/collections/{nom}", json={"sensitivity": "personal_sensitive"}).json()["sensitivity"] == "personal_sensitive"
    assert client.patch(f"/api/collections/{nom}", json={"sensitivity": "secret"}).json()["sensitivity"] == "restricted"
    r = client.patch(f"/api/collections/{nom}", json={"sensitivity": "tres-secret"})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "sensitivity"
    assert client.get(f"/api/collections/{nom}").json()["sensitivity"] == "restricted"


def _sql(requete, params=()):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        lignes = con.execute(requete, params).fetchall()
        con.commit()
        return lignes
    finally:
        con.close()


def test_le_demarrage_reecrit_les_anciennes_valeurs(client, creer_collection, nom):
    from app.database import _migrer_sensibilites, engine

    creer_collection(nom)
    _sql("UPDATE collections SET sensitivity = 'confidential' WHERE name = ?", (nom,))
    _sql(
        "INSERT INTO ingest_jobs (job_id, collection_name, filename, source_path, strategy, sensitivity, status, total_chunks, uploaded_chunks, failed_chunks, created_at) "
        "VALUES (?, ?, 'a.md', '', 'auto', 'secret', 'done', 0, 0, 0, CURRENT_TIMESTAMP)",
        (f"{nom}-job", nom),
    )

    async def _rejouer():
        async with engine.begin() as conn:
            await _migrer_sensibilites(conn)

    asyncio.run(_rejouer())
    asyncio.run(_rejouer())  # idempotent
    assert _sql("SELECT sensitivity FROM collections WHERE name = ?", (nom,)) == [("restricted",)]
    assert _sql("SELECT sensitivity FROM ingest_jobs WHERE job_id = ?", (f"{nom}-job",)) == [("restricted",)]
    _sql("DELETE FROM ingest_jobs WHERE job_id = ?", (f"{nom}-job",))
