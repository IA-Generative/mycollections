"""Partager une collection à un groupe dans l'assistant (diagnostic d'octobre 2026).

L'assistant désigne un groupe par un identifiant interne. Les publications « à un groupe »
envoyaient le chemin saisi (« myrag/x », « /myrag/x ») comme identifiant : la fiche ne visait
personne, sans erreur. Mesuré sur la bêta : deux collections publiées ainsi, visibles de nul.
"""

from unittest.mock import AsyncMock

import pytest

from app.services import fiche_assistant
from app.services.owui_client import OwuiClient

GROUPES = [{"id": "b39ff556-0000", "name": "mirai-beta-testeurs-admin"},
           {"id": "8d48a7a2-0000", "name": "Experimentation DGEF"}]


class _Rep:
    status_code = 200
    def raise_for_status(self): pass
    def json(self): return GROUPES


@pytest.mark.asyncio
async def test_un_nom_un_chemin_ou_un_identifiant_designent_le_meme_groupe(monkeypatch):
    import httpx

    class Faux:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _Rep()
    monkeypatch.setattr(httpx, "AsyncClient", Faux)
    c = OwuiClient.__new__(OwuiClient)
    c.base_url, c.api_key, c.timeout = "http://socle", "k", 5
    ids, inconnus = await c.ids_de_groupes(["/g/mirai-beta-testeurs-admin", "experimentation dgef", "8d48a7a2-0000", "myrag/absent"])
    assert ids == ["b39ff556-0000", "8d48a7a2-0000", "8d48a7a2-0000"]
    assert inconnus == ["myrag/absent"]


@pytest.mark.asyncio
async def test_la_fiche_vise_l_identifiant_du_groupe_ou_ne_part_pas(monkeypatch):
    voulue = {"model_id": "openrag-x", "name": "X", "tags": [], "access_control": None,
              "access_grants": [{"principal_type": "group", "principal_id": "/g/mirai-beta-testeurs-admin"}],
              "groupes_saisis": ["/g/mirai-beta-testeurs-admin"]}
    monkeypatch.setattr(fiche_assistant, "_voulue", AsyncMock(side_effect=lambda n: dict(voulue)))
    client = AsyncMock()
    client.ids_de_groupes = AsyncMock(return_value=(["b39ff556-0000"], []))
    await fiche_assistant.synchroniser_fiche("x", client=client)
    envoye = client.upsert_model.await_args.kwargs
    assert envoye["access_grants"] == [{"principal_type": "group", "principal_id": "b39ff556-0000", "permission": "read"}]
    assert "groupes_saisis" not in envoye

    client = AsyncMock()
    client.ids_de_groupes = AsyncMock(return_value=([], ["/g/mirai-beta-testeurs-admin"]))
    with pytest.raises(fiche_assistant.GroupeInconnu):
        await fiche_assistant.synchroniser_fiche("x", client=client)
    client.upsert_model.assert_not_awaited()


@pytest.mark.asyncio
async def test_la_resynchronisation_ne_touche_pas_aux_droits(monkeypatch):
    voulue = {"model_id": "openrag-x", "name": "X", "tags": [], "access_control": None,
              "access_grants": [], "groupes_saisis": ["/g/quelque-chose"]}
    monkeypatch.setattr(fiche_assistant, "_voulue", AsyncMock(side_effect=lambda n: dict(voulue)))
    client = AsyncMock()
    await fiche_assistant.synchroniser_fiche("x", client=client, garder_les_droits=True)
    client.ids_de_groupes.assert_not_awaited()
