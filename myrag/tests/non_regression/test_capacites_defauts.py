"""Les capacités, figées par inclusion (le lot 0 en ajoute) : /api/config porte au moins les
clés actuelles, et sans menu aucun drapeau n'est activé — quel que soit leur nombre."""

from __future__ import annotations

from app.services import capacites as module_capacites


def test_api_config_porte_les_cles_actuelles(client, capacites):
    capacites(demandes=True, signalements=False, seuil_chantier=7)
    c = client.get("/api/config").json()
    assert {"demandes": True, "signalements": False, "seuil_chantier": 7}.items() <= c.items()
    assert {"app_title", "openrag_url", "generation"} <= set(c)


def test_sans_menu_aucun_drapeau_n_est_active(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "capacites_url", "")
    module_capacites.oublier()
    v = module_capacites._lire_depuis_le_menu()
    assert v["seuil_chantier"] == 5
    assert {"demandes", "signalements"} <= set(module_capacites.DRAPEAUX)
    assert all(v[d] is False for d in module_capacites.DRAPEAUX)
