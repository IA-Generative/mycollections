"""A7 : le serveur MCP des assistants (`/mcp`, Streamable HTTP, sans état). Les requêtes passent par
l'application complète, avec de vrais jetons signés par une clé de test : l'identité relayée aux
outils est celle du jeton, jamais celle d'un argument."""

from __future__ import annotations

import json
import os
import sqlite3
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

pytest.importorskip("mcp")

import app.auth
import app.config
from app.routers import assistants as routes_assistants
from tests.conftest import GROUPE_TESTEURS, SUPERADMIN
from tests.harnais.conftest import IDENTITES, fiche_d_essai
from tests.harnais.test_fiables import QUESTION, REPONSE, _semer

_CLE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ENTETES = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
OUTILS = {"lister_sources", "proposer_sources", "rechercher"}


@pytest.fixture
def jetons(client, monkeypatch):
    """Authentification active, jetons signés par une clé de test. À demander APRÈS les fixtures qui créent des données."""
    from app.main import app as application

    application.dependency_overrides.clear()
    monkeypatch.setattr(app.config.settings, "auth_enabled", True)
    monkeypatch.setattr(app.config.settings, "myrag_groupe_exige", GROUPE_TESTEURS)
    routes_assistants._debit._comptes.clear()

    class _Cle:
        key = _CLE.public_key()

    class _Jwks:
        def get_signing_key_from_jwt(self, _jeton):
            return _Cle()

    monkeypatch.setattr(app.auth, "_get_jwks_client", lambda: _Jwks())

    def _jeton(nom: str = "alice", cle=_CLE, **claims):
        u = IDENTITES[nom]
        maintenant = int(time.time())
        corps = {"iss": app.auth._issuer(), "iat": maintenant, "exp": maintenant + 300, "sub": u.sub, "groups": list(u.groups), "azp": "mycollections-front", **claims}
        return {"Authorization": "Bearer " + jwt.encode(corps, cle, algorithm="RS256")}

    return _jeton


def rpc(client, methode: str, params: dict | None = None, *, entetes: dict | None = None):
    corps = {"jsonrpc": "2.0", "id": 1, "method": methode, "params": params or {}}
    return client.post("/mcp", json=corps, headers={**ENTETES, **(entetes or {})})


def appeler(client, jeton: dict, outil: str, **arguments) -> tuple[bool, dict | str]:
    """(erreur, contenu) d'un appel d'outil : le contenu est décodé quand l'outil a répondu."""
    r = rpc(client, "tools/call", {"name": outil, "arguments": arguments}, entetes=jeton)
    assert r.status_code == 200, r.text
    resultat = r.json()["result"]
    texte = resultat["content"][0]["text"]
    return bool(resultat.get("isError")), texte if resultat.get("isError") else json.loads(texte)


def _nettoyer(idents: list[str]) -> None:
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        for i in idents:
            for t in ("assistant_versions", "consignes", "plans_journal"):
                con.execute(f"DELETE FROM {t} WHERE assistant_id = ?", (i,))
            con.execute("DELETE FROM evenement WHERE objet_type = 'assistant' AND objet_id = ?", (i,))
            con.execute("DELETE FROM assistants WHERE id = ?", (i,))
        con.commit()
    finally:
        con.close()


# ─── tools/list ──────────────────────────────────────────────────────────────────


def test_tools_list_rend_trois_outils_sans_aucun_assistant(client, jetons):
    r = rpc(client, "tools/list", entetes=jetons())
    assert r.status_code == 200, r.text
    outils = r.json()["result"]["tools"]
    assert {o["name"] for o in outils} == OUTILS and len(outils) == 3
    assert all(len(o["description"]) > 60 and o["inputSchema"]["type"] == "object" for o in outils)  # des descriptions à lire par un modèle
    erreur, contenu = appeler(client, jetons(), "lister_sources")
    assert not erreur and contenu["assistants"] == []


def test_tools_list_rend_trois_outils_avec_cinquante_assistants(client, en_tant_que, jeu, theatre_branche, jetons, monkeypatch):
    idents = [f"t-mcp-{i:02d}-{os.urandom(3).hex()}" for i in range(50)]
    try:
        monkeypatch.setattr(app.config.settings, "auth_enabled", False)  # la création passe par les routes d'administration
        en_tant_que(SUPERADMIN)
        for ident in idents:
            assert client.put(f"/api/assistants/{ident}", json=fiche_d_essai(jeu, ident).model_dump(mode="json")).status_code == 200
            assert client.post(f"/api/assistants/{ident}/publier").status_code == 200
        monkeypatch.setattr(app.config.settings, "auth_enabled", True)
        client.app.dependency_overrides.clear()
        entetes = jetons()
        assert {o["name"] for o in rpc(client, "tools/list", entetes=entetes).json()["result"]["tools"]} == OUTILS
        erreur, contenu = appeler(client, entetes, "lister_sources")
        assert not erreur
        vus = {a["id"]: a for a in contenu["assistants"]}
        assert set(idents) <= set(vus)
        # Alice lit `mienne` et `partagee` ; `secrete` n'est ni nommée ni comptée.
        assert {c["id"] for c in vus[idents[0]]["collections"]} == {jeu["mienne"], jeu["partagee"]}
        assert {"id", "titre", "description"} == set(vus[idents[0]]["collections"][0])
        assert jeu["secrete"] not in json.dumps(contenu)
    finally:
        _nettoyer(idents)


# ─── L'identité et les droits ────────────────────────────────────────────────────


def test_l_identite_du_jeton_est_relayee_aux_outils(client, assistant_publie, jeu, theatre_branche, jetons, monkeypatch):
    from app.services import assistant_recherche as moteur

    vus = []
    charger = moteur.charger

    async def espion(ident, user, *a, **k):
        vus.append((user.sub, tuple(user.groups)))
        return await charger(ident, user, *a, **k)

    monkeypatch.setattr(moteur, "charger", espion)
    erreur, _ = appeler(client, jetons("bob"), "proposer_sources", question="budget", assistant=assistant_publie)
    assert not erreur
    assert vus == [(IDENTITES["bob"].sub, tuple(IDENTITES["bob"].groups))]


def test_une_personne_sans_droit_ne_recoit_aucun_passage_de_la_collection_secrete(client, en_tant_que, jeu, ident_assistant, theatre_branche, jetons, monkeypatch):
    # Ici `secrete` est une source ordinaire (`selon_question`) : le plan de Bob la vise bel et bien.
    monkeypatch.setattr(app.config.settings, "auth_enabled", False)
    en_tant_que(SUPERADMIN)
    sources = [
        {"id": jeu[k], "type": "collection", "regime": r, "rang": i}
        for i, (k, r) in enumerate([("mienne", "toujours"), ("partagee", "selon_question"), ("secrete", "selon_question")], start=1)
    ]
    assistant_publie = ident_assistant
    assert client.put(f"/api/assistants/{assistant_publie}", json=fiche_d_essai(jeu, assistant_publie, sources=sources).model_dump(mode="json")).status_code == 200
    assert client.post(f"/api/assistants/{assistant_publie}/publier").status_code == 200
    monkeypatch.setattr(app.config.settings, "auth_enabled", True)
    client.app.dependency_overrides.clear()
    # Bob lit `secrete` : les passages y sont (témoin positif : le théâtre les rend bien)…
    erreur, bob = appeler(client, jetons("bob"), "rechercher", question="budget", assistant=assistant_publie)
    assert not erreur
    assert any(p["collection"]["id"] == jeu["secrete"] for p in bob["passages"])
    # …Alice, non : ni passage, ni nom de la collection dans le plan, même en la demandant.
    erreur, alice = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie)
    assert not erreur and alice["passages"]
    assert jeu["secrete"] not in json.dumps(alice)
    erreur, contenu = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie, sources=[jeu["secrete"]])
    assert erreur and jeu["secrete"] not in contenu.replace("Aucune des collections demandées", "")
    # Une personne du groupe qui n'a que le droit commun : `partagee` seule.
    erreur, tiers = appeler(client, jetons("alice", sub="personne-tiers"), "rechercher", question="budget", assistant=assistant_publie)
    assert not erreur and {p["collection"]["id"] for p in tiers["passages"]} == {jeu["partagee"]}
    assert jeu["secrete"] not in json.dumps(tiers) and jeu["mienne"] not in json.dumps(tiers)


def test_rechercher_rend_titre_texte_url_signee_collection_et_plan(client, assistant_publie, jeu, theatre_branche, jetons):
    erreur, contenu = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie)
    assert not erreur
    premier = contenu["passages"][0]
    assert {"titre", "texte", "url", "collection", "score"} <= set(premier)
    assert premier["url"].startswith("https://mycollections.fake-domain.name/api/openrag/extract/") and "sig=" in premier["url"]
    assert premier["collection"]["id"] in {jeu["mienne"], jeu["partagee"]}
    assert {s["id"] for s in contenu["plan"]["sources"]} <= {jeu["mienne"], jeu["partagee"]}
    assert contenu["reponse"] is None


def test_sources_restreint_la_recherche(client, assistant_publie, jeu, theatre_branche, jetons):
    erreur, contenu = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie, sources=[jeu["partagee"]])
    assert not erreur
    assert {p["collection"]["id"] for p in contenu["passages"]} == {jeu["partagee"]}
    assert set(theatre_branche.sources_appelees()) == {jeu["partagee"]}


def test_proposer_sources_ne_cherche_rien(client, assistant_publie, jeu, theatre_branche, jetons):
    erreur, plan = appeler(client, jetons("alice"), "proposer_sources", question="budget", assistant=assistant_publie)
    assert not erreur and plan["sources"] and theatre_branche.appels == []
    assert jeu["secrete"] not in json.dumps(plan)


def test_une_reponse_fiable_est_rendue_telle_quelle(client, en_tant_que, jeu, ident_assistant, theatre_branche, jetons, monkeypatch):
    from tests.harnais.test_fiables import _publier

    monkeypatch.setattr(app.config.settings, "auth_enabled", False)  # le semis passe par les routes d'administration
    _semer(client, en_tant_que, jeu["partagee"])
    _publier(client, en_tant_que, jeu, ident_assistant)
    monkeypatch.setattr(app.config.settings, "auth_enabled", True)
    client.app.dependency_overrides.clear()
    erreur, contenu = appeler(client, jetons("alice"), "rechercher", question=QUESTION, assistant=ident_assistant)
    assert not erreur and contenu["reponse"] == REPONSE and contenu["passages"] == []
    assert contenu["plan"]["reponse_fiable"]["score"] == 1.0 and theatre_branche.appels == []


def test_assistant_inconnu_message_en_francais(client, jeu, theatre_branche, jetons):
    erreur, message = appeler(client, jetons(), "rechercher", question="budget", assistant="assistant-inconnu")
    assert erreur and "introuvable" in message and "lister_sources" in message


def test_le_debit_par_personne_est_celui_de_plan_et_executer(client, assistant_publie, theatre_branche, jetons, monkeypatch):
    monkeypatch.setattr(app.config.settings, "assistants_par_minute", 2)
    entetes = jetons("alice")
    assert not appeler(client, entetes, "proposer_sources", question="budget", assistant=assistant_publie)[0]
    assert not appeler(client, entetes, "rechercher", question="budget", assistant=assistant_publie)[0]
    erreur, message = appeler(client, entetes, "rechercher", question="budget", assistant=assistant_publie)
    assert erreur and "Trop de questions" in message
    assert not appeler(client, jetons("bob"), "rechercher", question="budget", assistant=assistant_publie)[0]  # le plafond est par personne


# ─── La porte : jeton, audience, drapeau ─────────────────────────────────────────


def test_sans_jeton_refus(client, jetons):
    r = rpc(client, "tools/list")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_jeton_invalide_refus(client, jetons):
    autre = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert rpc(client, "tools/list", entetes=jetons(cle=autre)).status_code == 401
    assert rpc(client, "tools/list", entetes=jetons(exp=1)).status_code == 401
    assert rpc(client, "tools/list", entetes={"Authorization": "Basic abc"}).status_code == 401


def test_audience_d_un_autre_service_refus(client, jetons):
    r = rpc(client, "tools/list", entetes=jetons(azp="un-autre-service", aud=["account"]))
    assert r.status_code == 403
    assert rpc(client, "tools/list", entetes=jetons(azp="mysearch", aud=["account"])).status_code == 403  # un client tiers doit porter l'audience
    assert rpc(client, "tools/list", entetes=jetons(azp="mysearch", aud=["mycollections-front"])).status_code == 200


def test_groupe_exige_refus(client, jetons):
    assert rpc(client, "tools/list", entetes=jetons("dehors")).status_code == 403


def test_drapeau_assistants_faux_serveur_indisponible(client, jetons, capacites):
    capacites(assistants=False)
    r = rpc(client, "tools/list", entetes=jetons())
    assert r.status_code == 404
    assert rpc(client, "tools/list").status_code == 404  # même sans jeton : la fonction n'existe pas


def test_sans_authentification_en_developpement_la_personne_de_developpement(client, monkeypatch):
    from app.main import app as application

    application.dependency_overrides.clear()
    assert not app.config.settings.auth_enabled
    r = rpc(client, "tools/list")
    assert r.status_code == 200 and {o["name"] for o in r.json()["result"]["tools"]} == OUTILS


def test_la_route_est_montee_a_l_adresse_exacte():
    from app.main import app as application

    assert "/mcp" in {getattr(r, "path", None) for r in application.routes}
