"""Diagnostic d'octobre 2026, P2 : les routes anciennes ne vérifiaient qu'un jeton valide.

Écrit AVANT le correctif (doit échouer sur le code d'avant) : chaque route qui lit une
collection exige de pouvoir la lire (404 sinon, sans divulguer qu'elle existe), chaque route
qui l'écrit exige de la gérer (403 pour qui la lit seulement).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.auth import CurrentUser
from tests.conftest import SUPERADMIN, personne

ETRANGER = CurrentUser(sub="etranger", username="e", groups=["/g/rien-a-voir"])
LECTEUR = personne("simple-lecteur")


@pytest.fixture
def privee(creer_collection, nom):
    """Une collection lisible du seul groupe des testeurs ; « createur » la gère."""
    creer_collection(nom)
    return nom


LECTURES = [
    ("get", "/api/playground/{n}/bank", None),
    ("get", "/api/qr-cache/{n}", None),
    ("get", "/api/eval/{n}/datasets", None),
    ("get", "/api/sources/legifrance/status/{n}", None),
    ("get", "/api/sources/drive/status/{n}", None),
]

ECRITURES = [
    ("post", "/api/qr-cache/{n}", {"question": "Q ?", "answer": "R."}),
    ("delete", "/api/qr-cache/{n}/x", None),
    ("post", "/api/eval/{n}/datasets", {"name": "jeu", "questions": []}),
    ("delete", "/api/eval/{n}/datasets/1", None),
    ("post", "/api/playground/{n}/generate-eval", {}),
    ("post", "/api/sources/legifrance/add", {"collection": "{n}", "legifrance_id": "LEGITEXT000006070158", "type": "code"}),
    ("post", "/api/sources/drive/sync/{n}", None),
]


def _appel(client, methode, chemin, corps, nom):
    chemin = chemin.format(n=nom)
    if isinstance(corps, dict):
        corps = {k: (v.format(n=nom) if isinstance(v, str) else v) for k, v in corps.items()}
    fn = getattr(client, methode)
    return fn(chemin, json=corps) if corps is not None and methode != "delete" else fn(chemin)


@pytest.mark.parametrize("methode,chemin,corps", LECTURES + ECRITURES)
def test_qui_ne_lit_pas_la_collection_ne_voit_rien(client, en_tant_que, privee, methode, chemin, corps):
    en_tant_que(ETRANGER)
    assert _appel(client, methode, chemin, corps, privee).status_code == 404


@pytest.mark.parametrize("methode,chemin,corps", ECRITURES)
def test_qui_lit_sans_gerer_ne_modifie_rien(client, en_tant_que, privee, methode, chemin, corps):
    en_tant_que(LECTEUR)
    assert _appel(client, methode, chemin, corps, privee).status_code == 403


@pytest.mark.parametrize("methode,chemin,corps", LECTURES)
def test_qui_lit_la_collection_lit_ses_donnees(client, en_tant_que, privee, methode, chemin, corps):
    en_tant_que(LECTEUR)
    assert _appel(client, methode, chemin, corps, privee).status_code == 200


def test_le_gestionnaire_ecrit_dans_le_cache_et_les_jeux(client, en_tant_que, privee):
    en_tant_que(personne("createur"))
    assert client.post(f"/api/qr-cache/{privee}", json={"question": "Q ?", "answer": "R."}).status_code == 200
    assert client.post(f"/api/eval/{privee}/datasets", json={"name": "jeu", "questions": []}).status_code == 200


def test_les_travaux_d_indexation_ne_se_lisent_que_pour_ses_collections(client, en_tant_que, privee):
    en_tant_que(personne("createur"))
    with patch("app.routers.ingest.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.upload_chunk = AsyncMock(return_value={})
        job = client.post(f"/api/ingest/{privee}", files={"file": ("a.md", b"# T\n\nTexte.", "text/markdown")}).json()["job_id"]
    en_tant_que(ETRANGER)
    assert client.get(f"/api/ingest/jobs/{job}").status_code == 404
    assert all(j["collection"] != privee for j in client.get("/api/ingest/jobs").json()["jobs"])
    en_tant_que(LECTEUR)
    assert client.get(f"/api/ingest/jobs/{job}").status_code == 200


@pytest.mark.parametrize("methode,chemin", [("post", "/api/collections/templates"),
                                            ("put", "/api/collections/templates/essai-p2"),
                                            ("delete", "/api/collections/templates/essai-p2")])
def test_les_modeles_de_consignes_se_reglent_par_l_administration(client, en_tant_que, methode, chemin):
    en_tant_que(personne("quelqu-un"))
    corps = {"key": "essai-p2", "name": "Essai", "prompt": "Tu es…", "description": ""}
    r = getattr(client, methode)(chemin, json=corps) if methode != "delete" else client.delete(chemin)
    assert r.status_code == 403
