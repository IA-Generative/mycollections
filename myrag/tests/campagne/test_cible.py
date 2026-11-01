"""Le client de la cible : jeton renouvelé puis reconnexion, cadence, 429, règles d'arrêt, passerelle."""

from __future__ import annotations

import json

import httpx
import pytest

from scripts.campagne import cible as c
from tests.campagne.conftest import BASE, JETON_URL, FauxSso


def _cible(horloge, gestionnaire, sso=None, **kw):
    sso = sso or FauxSso(horloge)
    client = httpx.Client(transport=httpx.MockTransport(gestionnaire))
    return c.Cible(BASE, sso, client=client, horloge=horloge, dormir=horloge.dormir, **kw), sso


def test_le_premier_appel_se_connecte_une_fois(horloge):
    vus = []

    def gestionnaire(req):
        vus.append(req.headers.get("authorization"))
        return httpx.Response(200, json={})

    cb, sso = _cible(horloge, gestionnaire)
    cb.appel("GET", "/api/x", route="recherche")
    cb.appel("GET", "/api/x", route="recherche")
    assert sso.connexions == 1
    assert vus == ["Bearer acces-1", "Bearer acces-1"]


def test_le_jeton_se_renouvele_par_refresh_token_avant_expiration(horloge):
    formulaires = []

    def gestionnaire(req):
        if str(req.url) == JETON_URL:
            formulaires.append(dict(httpx.QueryParams(req.content.decode())))
            return httpx.Response(200, json={"access_token": "acces-renouvele", "refresh_token": "renouv-2", "expires_in": 300, "refresh_expires_in": 1800})
        return httpx.Response(200, json={"jeton": req.headers["authorization"]})

    cb, sso = _cible(horloge, gestionnaire)
    cb.appel("GET", "/api/x", route="recherche")
    horloge.t += 250  # il reste 50 s : moins que la marge
    r = cb.appel("GET", "/api/x", route="recherche")
    assert r.json()["jeton"] == "Bearer acces-renouvele"
    assert formulaires == [{"grant_type": "refresh_token", "client_id": "client-essai", "refresh_token": "renouv-1"}]
    assert "client_secret" not in formulaires[0]
    assert sso.connexions == 1 and cb.renouvellements == 1


def test_un_renouvellement_refuse_reconnecte_par_le_navigateur(horloge):
    """Session SSO expirée (inactivité) : le refresh répond 400, on se reconnecte une fois."""

    def gestionnaire(req):
        if str(req.url) == JETON_URL:
            return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Session not active"})
        return httpx.Response(200, json={"jeton": req.headers["authorization"]})

    cb, sso = _cible(horloge, gestionnaire)
    cb.appel("GET", "/api/x", route="recherche")
    horloge.t += 3600
    r = cb.appel("GET", "/api/x", route="recherche")
    assert r.json()["jeton"] == "Bearer acces-2"
    assert sso.connexions == 2 and cb.reconnexions == 1


def test_une_reconnexion_impossible_arrete_la_nuit(horloge):
    def gestionnaire(req):
        if str(req.url) == JETON_URL:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={})

    cb, _ = _cible(horloge, gestionnaire, sso=FauxSso(horloge, echoue=True))
    cb.appel("GET", "/api/x", route="recherche")
    horloge.t += 3600
    with pytest.raises(c.SessionPerdue) as e:
        cb.appel("GET", "/api/x", route="recherche")
    assert e.value.motif == "session-perdue"


def test_un_401_renouvelle_le_jeton_et_rejoue_une_fois(horloge):
    statuts = iter([401, 200])

    def gestionnaire(req):
        if str(req.url) == JETON_URL:
            return httpx.Response(200, json={"access_token": "acces-neuf", "expires_in": 300})
        return httpx.Response(next(statuts), json={"jeton": req.headers["authorization"]})

    cb, _ = _cible(horloge, gestionnaire)
    r = cb.appel("GET", "/api/x", route="recherche")
    assert r.status_code == 200 and r.json()["jeton"] == "Bearer acces-neuf"


def test_un_429_respecte_retry_after(horloge):
    statuts = iter([429, 200])

    def gestionnaire(req):
        s = next(statuts)
        return httpx.Response(s, headers={"Retry-After": "17"} if s == 429 else {})

    cb, _ = _cible(horloge, gestionnaire)
    assert cb.appel("POST", "/api/v1/assistants/a/executer", route="assistants").status_code == 200
    assert 17 in horloge.sommes
    assert cb.compteurs["assistants"]["429"] == 1


def test_la_cadence_espace_les_appels_d_une_route(horloge):
    cb, _ = _cible(horloge, lambda req: httpx.Response(200), cadences={"assistants": 20})
    for _ in range(3):
        cb.appel("POST", "/x", route="assistants")
    assert horloge.sommes == [3.0, 3.0]  # 20 par minute : un appel toutes les 3 s


def test_une_rafale_de_429_divise_la_cadence_puis_arrete():
    seau = c.Seau(20, lambda: 0.0, lambda s: None)
    garde = c.Garde()
    for _ in range(c.RAFALE_429):
        garde.noter("assistants", 429, seau)
    assert seau.par_minute == 10.0  # divisée par deux
    with pytest.raises(c.Arret) as e:
        for _ in range(c.RAFALE_429):
            garde.noter("assistants", 429, seau)
    assert e.value.motif == "rafale-429" and not e.value.immediat


def test_un_429_isole_ne_ralentit_pas():
    seau = c.Seau(20, lambda: 0.0, lambda s: None)
    garde = c.Garde()
    for _ in range(10):
        garde.noter("assistants", 429, seau)
        garde.noter("assistants", 200, seau)
    assert seau.par_minute == 20.0


def test_plus_de_20_pourcent_de_5xx_sur_50_arrete_la_nuit():
    seau = c.Seau(0, lambda: 0.0, lambda s: None)
    garde = c.Garde()
    for i in range(50):
        garde.noter("assistants", 200 if i < 40 else 500, seau)  # 20 % tout juste : on continue
    with pytest.raises(c.Arret) as e:
        garde.noter("assistants", 0, seau)  # injoignable compte comme un 5xx : 11 sur 50
    assert e.value.motif == "5xx"


def test_un_incident_de_droits_arrete_tout_immediatement():
    with pytest.raises(c.Arret) as e:
        c.Garde().incident("un passage de essai-secrete")
    assert e.value.immediat and e.value.motif == "incident-droits"


def test_mcp_lit_le_json_et_le_flux_sse(horloge):
    def gestionnaire(req):
        corps = json.loads(req.content)
        assert req.headers["accept"] == "application/json, text/event-stream"
        if corps["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": corps["id"], "result": {"tools": [{"name": "rechercher"}]}})
        sse = f'event: message\ndata: {{"jsonrpc": "2.0", "id": {corps["id"]}, "result": {{"content": []}}}}\n\n'
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    cb, _ = _cible(horloge, gestionnaire)
    assert cb.mcp("tools/list")["tools"][0]["name"] == "rechercher"
    assert cb.mcp("tools/call", {"name": "lister_sources", "arguments": {}}) == {"content": []}


def test_mcp_rend_l_erreur_json_rpc(horloge):
    cb, _ = _cible(horloge, lambda req: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "outil inconnu"}}))
    with pytest.raises(c.ErreurMcp, match="outil inconnu"):
        cb.mcp("tools/call", {"name": "x"})


def test_un_lien_se_suit_sans_jeton_et_jamais_hors_de_la_cible(horloge):
    vus = []

    def gestionnaire(req):
        vus.append((str(req.url), req.headers.get("authorization")))
        return httpx.Response(200)

    cb, sso = _cible(horloge, gestionnaire)
    assert cb.lien(f"{BASE}/api/openrag/extract/m1?exp=1&sig=s") == 200
    assert cb.lien("https://ailleurs.fake-domain.name/piege") is None
    assert vus == [(f"{BASE}/api/openrag/extract/m1?exp=1&sig=s", None)]
    assert sso.connexions == 0  # un lien signé n'a pas besoin de jeton


def test_la_cible_et_la_passerelle_exigent_https():
    with pytest.raises(c.Usage):
        c.origine("http://mycollections.fake-domain.name")
    assert c.origine("http://localhost:8200/") == "http://localhost:8200"
    with pytest.raises(c.Usage):
        c.Passerelle("http://passerelle.fake-domain.name/v1", "cle", max_appels=1)


def test_jeton_de_session_lit_la_cle_oidc_et_ne_s_affiche_pas():
    j = c.jeton_de_session({"cle": "oidc.user:https://sso.fake-domain.name/realms/essai:client-essai", "access_token": "secret", "refresh_token": "r", "expires_at": 10})
    assert (j.autorite, j.client_id) == ("https://sso.fake-domain.name/realms/essai", "client-essai")
    assert "secret" not in repr(j)
    with pytest.raises(c.SessionPerdue):
        c.jeton_de_session(None)


def test_la_passerelle_n_emprunte_jamais_la_clef_du_chat(monkeypatch):
    monkeypatch.delenv("CAMPAGNE_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv("MIRAI_GATEWAY_TOKEN", "clef-du-chat")
    monkeypatch.setenv("CAMPAGNE_GATEWAY_URL", "https://passerelle.fake-domain.name/v1")
    with pytest.raises(c.Usage, match="CAMPAGNE_GATEWAY_TOKEN"):
        c.Passerelle.depuis_env(max_appels=10)


def test_la_passerelle_compte_son_budget_et_sa_clef(monkeypatch):
    entetes = []

    def gestionnaire(req):
        entetes.append(req.headers["authorization"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}})

    monkeypatch.setenv("CAMPAGNE_GATEWAY_TOKEN", "clef-campagne")
    monkeypatch.setenv("CAMPAGNE_GATEWAY_URL", "https://passerelle.fake-domain.name/v1/")
    p = c.Passerelle.depuis_env(max_appels=3, client=httpx.Client(transport=httpx.MockTransport(gestionnaire)), deja=1)
    p.completer({})
    p.completer({})
    with pytest.raises(c.BudgetEpuise):
        p.completer({})
    assert entetes == ["Bearer clef-campagne"] * 2
    assert p.jetons == {"entree": 14, "sortie": 6}


def test_la_passerelle_en_panne_arrete_la_nuit():
    p = c.Passerelle(
        "https://passerelle.fake-domain.name/v1", "cle", max_appels=50, client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(503))), dormir=lambda s: None
    )
    for _ in range(c.Passerelle.ECHECS_MAX - 1):
        with pytest.raises(httpx.HTTPStatusError):
            p.completer({})
    with pytest.raises(c.Arret) as e:
        p.completer({})
    assert e.value.motif == "passerelle"
