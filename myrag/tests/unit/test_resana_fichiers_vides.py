"""Un fichier que Résana rend vide (200 sans corps, quand il est saturé) n'est pas un document :
il est redemandé, puis signalé sans être mémorisé ; une série de vides arrête la passe au lieu
d'écarter tout le dossier (mesuré le 2026-10-25 : 341 documents écartés « vides » sur 783)."""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from app.routers import sources_resana
from tests.unit.test_resana_routes import CREATEUR, ENTETE, _doc, _importer, _sources, faux, privee  # noqa: F401 — fixtures


@pytest.fixture(autouse=True)
def sans_attente(monkeypatch):
    pauses: list[float] = []

    async def noter(secondes):
        pauses.append(secondes)

    monkeypatch.setattr(sources_resana, "_pause", noter)
    return pauses


def _travail(client, nom):
    return client.get(f"/api/sources/resana/status/{nom}").json()["travail"]


def _cfg(nom) -> dict:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        (brut,) = con.execute("SELECT source_config_json FROM collections WHERE name = ?", (nom,)).fetchone()
        return json.loads(brut)
    finally:
        con.close()


def test_un_fichier_vide_une_fois_est_redemande_et_indexe(client, en_tant_que, faux, privee, sans_attente):
    faux.documents[0].vides = 1
    en_tant_que(CREATEUR)
    _importer(client, privee)
    travail = _travail(client, privee)
    assert (travail["etat"], travail["ajoutes"], travail["ecartes"]) == ("termine", 2, 0)
    assert _sources(privee) == ["note-a.md", "note-b.md"] and sans_attente == [sources_resana.PAUSES_FICHIER_VIDE[0]]


def test_un_fichier_toujours_vide_est_signale_sans_etre_memorise(client, en_tant_que, faux, privee):
    faux.documents[0].vides = -1
    en_tant_que(CREATEUR)
    _importer(client, privee)
    travail = _travail(client, privee)
    assert travail["etat"] == "termine" and _sources(privee) == ["note-b.md"]
    (e,) = travail["documents_ecartes"]
    assert e["code"] == "fichier_vide" and "vide" in e["raison"]
    assert "a" not in (_cfg(privee).get("ecartes") or {}), "un téléchargement raté ne se mémorise pas"
    # Résana s'est remis : la passe suivante le reprend.
    faux.documents[0].vides = 0
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert _sources(privee) == ["note-a.md", "note-b.md"]


def test_une_serie_de_vides_arrete_la_passe_en_gardant_l_acquis(client, en_tant_que, faux, privee, monkeypatch):
    monkeypatch.setattr(sources_resana, "TELECHARGEMENTS_PARALLELES", 1)
    monkeypatch.setattr(sources_resana, "VIDES_DE_SUITE_MAX", 3)
    faux.documents += [_doc(f"x{k}", f"# X{k}\n\nTexte fictif {k}.", vides=-1) for k in range(5)]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    travail = _travail(client, privee)
    assert travail["etat"] == "partiel" and travail["code"] == "resana_sature"
    assert _sources(privee) == ["note-a.md", "note-b.md"]
    telecharges = [q.url.path.split("/")[-2] for q in faux.requetes if q.url.path.endswith("/fichier")]
    assert "x4" not in telecharges, "la passe s'arrête au lieu de tout essayer"


def test_un_ecart_note_vide_avant_le_correctif_est_retelecharge(client, en_tant_que, faux, privee):
    en_tant_que(CREATEUR)
    _importer(client, privee)
    # Ce qu'une passe d'avant notait : un document « vide » d'empreinte vide, avec sa version.
    cfg = _cfg(privee)
    fiche = cfg["documents"].pop("a")
    cfg["ecartes"] = {
        "a": {
            "sha256": sources_resana.SHA256_VIDE,
            "version_fichier": fiche["version_fichier"],
            "modifie_le": fiche["modifie_le"],
            "raison": "format non pris en charge (.pdf)",
            "code": "format",
            "extension": ".pdf",
        }
    }
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        con.execute("UPDATE collections SET source_config_json = ? WHERE name = ?", (json.dumps(cfg), privee))
        con.commit()
    finally:
        con.close()
    faux.requetes.clear()
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert any(q.url.path.endswith("/documents/a/fichier") for q in faux.requetes)
    assert "a" in _cfg(privee)["documents"] and not _cfg(privee).get("ecartes")
