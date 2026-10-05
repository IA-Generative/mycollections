"""Diagnostic d'octobre 2026, P2 : /health disait « 0.1.0 » quelle que soit l'image (0.3.22 en
service) et « ok » sans rien vérifier. Écrit avant le correctif.

- /__version__ (ADR-0004, format Dockerflow) sert le journal que l'image porte, /app/version.json ;
  hors image, l'objet « dev » à sept clés, jamais une erreur ; sans authentification.
- /health s'appuie dessus pour la version, et dit l'état des dépendances (base, OpenRAG) sans
  jamais tomber : une sonde de vivacité qui échoue quand OpenRAG est lent ferait redémarrer le pod.
"""

import json
from unittest.mock import AsyncMock, patch

CLES = {"source", "version", "commit", "build", "code_date", "changes", "history"}


def test_hors_image_la_version_est_dev(client):
    r = client.get("/__version__")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert set(r.json()) == CLES and r.json()["version"] == "dev"


def test_dans_l_image_le_journal_est_servi_tel_quel(client, tmp_path, monkeypatch):
    from app import version
    fichier = tmp_path / "version.json"
    journal = {"source": "https://github.com/IA-Generative/mycollections", "version": "0.3.23", "commit": "abc",
               "build": "", "code_date": "2026-10-04T20:00:00Z", "changes": ["Une phrase."], "history": []}
    fichier.write_text(json.dumps(journal), encoding="utf-8")
    monkeypatch.setattr(version, "VERSION_JSON", fichier)
    assert client.get("/__version__").json() == journal
    sante = client.get("/health").json()
    assert sante["version"] == "0.3.23", "la santé dit la version de l'image, pas une constante"


def test_la_route_de_version_ne_demande_pas_de_jeton_et_n_est_pas_dans_le_schema(client):
    from app.main import app
    assert "/__version__" not in {r.path for r in app.routes if getattr(r, "include_in_schema", False)}


def test_la_sante_dit_l_etat_des_dependances_sans_tomber(client):
    with patch("app.main.OpenRAGClient") as cls:
        cls.return_value.health_check = AsyncMock(return_value=False)
        r = client.get("/health")
    assert r.status_code == 200, "une dépendance en panne ne doit pas faire redémarrer le pod"
    corps = r.json()
    assert corps["status"] == "degraded"
    assert corps["dependances"]["base"] == "ok" and corps["dependances"]["openrag"] == "ko"
    with patch("app.main.OpenRAGClient") as cls:
        cls.return_value.health_check = AsyncMock(return_value=True)
        from app import main
        main._sante_cache.clear()
        assert client.get("/health").json()["status"] == "ok"
