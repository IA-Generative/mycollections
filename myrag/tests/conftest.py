"""Socle commun des tests de myrag.

Deux contraintes, vérifiées sur le code : `Settings()` s'instancie à l'import de
`app.config` et le moteur à l'import de `app.database` ; plusieurs modules de test
importent `app.*` à la collecte. Une fixture arriverait donc trop tard — les variables
sont posées ICI, en tête de module, avant tout import de l'application. On ASSIGNE
(jamais `setdefault`) : aucune vraie base ne doit recevoir le `DELETE FROM collections`
d'un test.

Cinq modules historiques construisent `TestClient(app)` sans `with`, donc sans le
cycle de vie qui crée les tables : la fixture de session ci-dessous le joue une fois.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

_REP = tempfile.mkdtemp(prefix="myrag-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_REP}/base.db"
os.environ["DATA_DIR"] = f"{_REP}/data"
os.environ["MYRAG_PSEUDO_SEL"] = "sel-de-test"
os.environ["CAPACITES_URL"] = ""
os.environ["AUTH_ENABLED"] = "false"
os.environ["MYRAG_GROUPE_EXIGE"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from app.auth import CurrentUser, current_user  # noqa: E402

#: Toutes les tables liées à une collection par `collection_name` — les 7 historiques
#: et celles du collectif. Une table oubliée ici laisse des orphelins entre modules.
TABLES_PAR_COLLECTION = (
    "source_files", "eval_runs", "eval_datasets", "feedback", "ingest_jobs",
    "publication_history", "publications",
    "proposition", "signalement", "grille_controle", "evenement",
)

SUPERADMIN = CurrentUser(sub="op-superadmin", username="op", groups=["/myrag/superadmin"])
GROUPE_TESTEURS = "/g/mirai-beta-testeurs"


def personne(n: int | str, *groupes: str) -> CurrentUser:
    """Une personne du groupe des testeurs, sans autre droit."""
    return CurrentUser(sub=f"personne-{n}", username=f"p{n}", groups=[GROUPE_TESTEURS, *groupes])


@pytest.fixture(scope="session", autouse=True)
def _base_initialisee():
    from app.main import app
    with TestClient(app):
        pass


@pytest.fixture
def client():
    from app.main import app
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def en_tant_que(client):
    from app.main import app

    def _f(user: CurrentUser):
        app.dependency_overrides[current_user] = lambda: user
        return user
    return _f


@pytest.fixture(autouse=True)
def capacites(monkeypatch):
    """Par défaut dans les tests : tout est activé, seuil 5. Rappeler pour changer."""
    from app.services import capacites as module

    def _poser(**drapeaux):
        valeur = {"demandes": True, "signalements": True, "seuil_chantier": 5, **drapeaux}
        monkeypatch.setattr(module, "lire", lambda: dict(valeur))
        return valeur
    _poser()
    return _poser


@pytest.fixture
def purger():
    def _f(name: str):
        chemin = os.environ["DATABASE_URL"].split("///")[-1]
        con = sqlite3.connect(chemin)
        try:
            for t in TABLES_PAR_COLLECTION:
                con.execute(f"DELETE FROM {t} WHERE collection_name = ?", (name,))
            con.execute("DELETE FROM abonnement WHERE objet_type='collection' AND objet_id = ?", (name,))
            con.execute("DELETE FROM collections WHERE name = ?", (name,))
            con.commit()
        finally:
            con.close()
    return _f


@pytest.fixture
def creer_collection(client, en_tant_que):
    """Crée une collection lisible du groupe des testeurs, en tant que `createur`."""
    def _f(name: str, createur: CurrentUser | None = None, **champs):
        en_tant_que(createur or personne("createur"))
        with patch("app.routers.collections.OpenRAGClient") as cls:
            cls.return_value.create_partition = AsyncMock(return_value={})
            r = client.post("/api/collections", json={
                "name": name, "scope": "group", "scope_groups": [GROUPE_TESTEURS], **champs,
            })
        assert r.status_code == 200, r.text
        return r.json()["collection"]
    return _f


@pytest.fixture
def nom(request, purger):
    """Un nom de collection unique par test, purgé après."""
    n = ("t-" + request.node.name.lower().replace("_", "-").replace("[", "-").replace("]", ""))[:60]
    purger(n)
    yield n
    purger(n)
