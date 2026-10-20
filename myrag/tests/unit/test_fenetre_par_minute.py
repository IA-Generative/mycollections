"""Le débit des questions posées aux assistants : un plafond par personne et par minute, 429
avec Retry-After au-delà ; une autre personne n'est pas freinée."""

from __future__ import annotations

import uuid

from app.services.fenetre_par_minute import Fenetre
from tests.conftest import personne


def test_la_fenetre_compte_par_minute_et_par_cle():
    f = Fenetre(lambda: 2)
    t = 60 * 16_667 + 20.0  # 20 s après le début d'une minute
    assert f.compter("a", maintenant=t) is None
    assert f.compter("a", maintenant=t + 1) is None
    assert f.compter("a", maintenant=t + 2) == 38  # secondes jusqu'à la minute suivante
    assert f.compter("b", maintenant=t + 2) is None, "une autre personne a son propre compte"
    assert f.compter("a", maintenant=t + 60) is None, "la minute suivante repart de zéro"


def test_un_plafond_nul_ne_limite_pas():
    f = Fenetre(lambda: 0)
    assert all(f.compter("a") is None for _ in range(100))


def test_au_dela_du_plafond_le_moteur_rend_429(client, en_tant_que, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "assistants_par_minute", 2)
    monkeypatch.setattr(settings, "doublure_assistants", True)
    pressee, autre = personne(f"pressee-{uuid.uuid4().hex[:6]}"), personne(f"autre-{uuid.uuid4().hex[:6]}")
    en_tant_que(pressee)
    corps = {"question": "Quelles pièces fournir ?"}
    assert client.post("/api/v1/assistants/exemple/executer", json=corps).status_code == 200
    assert client.post("/api/v1/assistants/exemple/plan", json=corps).status_code == 200
    r = client.post("/api/v1/assistants/exemple/executer", json=corps)
    assert r.status_code == 429 and 1 <= int(r.headers["retry-after"]) <= 60
    en_tant_que(autre)
    assert client.post("/api/v1/assistants/exemple/executer", json=corps).status_code == 200
