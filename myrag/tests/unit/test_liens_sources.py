"""Les liens vers les sources passent par notre proxy — jamais par l'API publique
d'OpenRAG, dont le SSO finit en « User does not have access to this file »."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.routers.playground import relier_au_proxy


def test_les_liens_de_la_reponse_sont_ramenes_sur_le_proxy():
    texte = ("**Sources :** 1. [ssmsi_69.md](https://api.openrag-mirai.numerique-interieur.com/static/468450154026104240)"
             " 2. [x](http://openrag:8080/extract/12)")
    assert relier_au_proxy(texte) == (
        "**Sources :** 1. [ssmsi_69.md](/api/openrag/extract/468450154026104240) 2. [x](/api/openrag/extract/12)")


def test_un_texte_sans_lien_ne_bouge_pas():
    assert relier_au_proxy("8 302 cambriolages, voir https://www.data.gouv.fr/") == "8 302 cambriolages, voir https://www.data.gouv.fr/"
    assert relier_au_proxy("") == ""


class _Reponse:
    def __init__(self, status, content=b"", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}


@pytest.mark.asyncio
async def test_static_renvoye_vers_le_sso_rend_le_morceau_a_la_place(monkeypatch):
    from app import main as m
    appels = []

    class FauxClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            appels.append(url)
            if "/static/" in url:
                return _Reponse(302, headers={"location": "/auth/login?next=%2Fstatic%2F42", "content-type": "text/html"})
            return _Reponse(200, b'{"page_content": "| 2024 | 8302 |", "metadata": {"filename": "ssmsi_69.md"}}',
                            {"content-type": "application/json"})

    monkeypatch.setattr(httpx, "AsyncClient", FauxClient)
    r = await m.openrag_static_proxy("42")
    assert r.status_code == 200 and b"8302" in r.body and b"kcContext" not in r.body
    assert any("/extract/42" in u for u in appels), "le morceau est servi à la place de la page de connexion"
