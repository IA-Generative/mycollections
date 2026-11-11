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
OUTILS = {"trouver_collections", "lister_sources", "proposer_sources", "rechercher"}


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


def test_tools_list_rend_quatre_outils_sans_aucun_assistant(client, jetons):
    r = rpc(client, "tools/list", entetes=jetons())
    assert r.status_code == 200, r.text
    outils = r.json()["result"]["tools"]
    assert {o["name"] for o in outils} == OUTILS and len(outils) == 4
    assert all(len(o["description"]) > 60 and o["inputSchema"]["type"] == "object" for o in outils)  # des descriptions à lire par un modèle
    erreur, contenu = appeler(client, jetons(), "lister_sources")
    # Sans assistant, restent les collections qu'elle lit (s'il y en a), chacune seule.
    assert not erreur and all(len(a["collections"]) == 1 and a["consignes"] == [] for a in contenu["assistants"])


def test_tools_list_rend_quatre_outils_avec_cinquante_assistants(client, en_tant_que, jeu, theatre_branche, jetons, monkeypatch):
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
        assert vus[idents[0]]["consignes"] == []
    finally:
        _nettoyer(idents)


def test_lister_sources_dit_les_cas_que_l_assistant_sait_traiter(client, en_tant_que, jeu, theatre_branche, jetons, monkeypatch):
    """Les « quand » des consignes, sauf celle qui vaut pour toute question : de quoi préférer un assistant métier à une collection seule."""
    ident = f"t-mcp-consignes-{os.urandom(3).hex()}"
    consignes = [
        {"id": "juridique", "quand": "toujours", "repondre": "Citer l'article."},
        {"id": "budget", "quand": "une question sur le vote du budget", "exemples": ["Quand le budget est-il voté ?"], "chercher": [{"source": jeu["mienne"]}]},
    ]
    try:
        monkeypatch.setattr(app.config.settings, "auth_enabled", False)
        en_tant_que(SUPERADMIN)
        fiche = fiche_d_essai(jeu, ident, consignes=consignes)
        assert client.put(f"/api/assistants/{ident}", json=fiche.model_dump(mode="json")).status_code == 200
        assert client.post(f"/api/assistants/{ident}/publier").status_code == 200
        monkeypatch.setattr(app.config.settings, "auth_enabled", True)
        client.app.dependency_overrides.clear()
        erreur, contenu = appeler(client, jetons(), "lister_sources")
        assert not erreur
        vu = next(a for a in contenu["assistants"] if a["id"] == ident)
        assert vu["consignes"] == ["une question sur le vote du budget"]
    finally:
        _nettoyer([ident])


# ─── Les collections lisibles sans assistant ─────────────────────────────────────


def test_une_collection_lisible_sans_assistant_est_listee_seule_et_s_interroge(client, jeu, theatre_branche, jetons):
    """Une collection non publiée (une amorce, une collection d'équipe) que la personne lit : la recherche la
    lui propose, le MCP aussi — sinon « je ne sais pas où chercher » ne la trouve jamais (campagne du 2026-11-01)."""
    erreur, contenu = appeler(client, jetons("alice"), "lister_sources")
    assert not erreur
    vus = {a["id"]: a for a in contenu["assistants"]}
    for k in ("mienne", "partagee", "ouverte"):
        assert [c["id"] for c in vus[jeu[k]]["collections"]] == [jeu[k]] and vus[jeu[k]]["consignes"] == []
    assert vus[jeu["mienne"]]["titre"] == "Mes notes"
    assert jeu["secrete"] not in json.dumps(contenu)
    erreur, trouve = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=jeu["mienne"])
    assert not erreur and trouve["passages"] and {p["collection"]["id"] for p in trouve["passages"]} == {jeu["mienne"]}
    assert trouve["plan"]["assistant"] == jeu["mienne"]
    erreur, _ = appeler(client, jetons("alice"), "proposer_sources", question="budget", assistant=jeu["partagee"])
    assert not erreur


def test_une_collection_illisible_reste_introuvable(client, jeu, theatre_branche, jetons):
    erreur, contenu = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=jeu["secrete"])
    assert erreur and "introuvable" in contenu
    erreur, bob = appeler(client, jetons("bob"), "rechercher", question="budget", assistant=jeu["secrete"])
    assert not erreur and {p["collection"]["id"] for p in bob["passages"]} == {jeu["secrete"]}


def test_une_collection_deja_portee_seule_n_est_pas_listee_deux_fois(client, en_tant_que, jeu, theatre_branche, jetons, monkeypatch):
    """Un assistant à une source sur `partagee` la porte : pas d'entrée en double. Un assistant qui a pris le nom
    de `ouverte` sans la porter masque l'entrée seule de `ouverte` (son identifiant n'est pas libre)."""
    portant, homonyme = f"t-mcp-portant-{os.urandom(3).hex()}", jeu["ouverte"]
    try:
        monkeypatch.setattr(app.config.settings, "auth_enabled", False)
        en_tant_que(SUPERADMIN)
        une = [{"id": jeu["partagee"], "type": "collection", "regime": "toujours", "rang": 1}]
        for ident in (portant, homonyme):
            assert client.put(f"/api/assistants/{ident}", json=fiche_d_essai(jeu, ident, sources=une).model_dump(mode="json")).status_code == 200
            assert client.post(f"/api/assistants/{ident}/publier").status_code == 200
        monkeypatch.setattr(app.config.settings, "auth_enabled", True)
        client.app.dependency_overrides.clear()
        erreur, contenu = appeler(client, jetons("alice"), "lister_sources")
        assert not erreur
        ids = [a["id"] for a in contenu["assistants"]]
        assert jeu["partagee"] not in ids and portant in ids
        assert ids.count(homonyme) == 1 and next(a for a in contenu["assistants"] if a["id"] == homonyme)["collections"][0]["id"] == jeu["partagee"]
    finally:
        _nettoyer([portant, homonyme])


# ─── Trouver où chercher ─────────────────────────────────────────────────────────


def test_trouver_collections_classe_ce_que_la_personne_lit(client, jeu, theatre_branche, jetons):
    """« Je ne sais pas où chercher » : la question classe les collections lisibles ; le client n'a plus à choisir dans toute la liste."""
    erreur, contenu = appeler(client, jetons("alice"), "trouver_collections", question="Quelles sont les méthodes de l'équipe ?")
    assert not erreur
    sources = contenu["sources"]
    assert sources[0]["id"] == jeu["partagee"] and sources[0]["score"] > 0
    assert {"id", "titre", "description", "collections", "consignes", "score"} == set(sources[0])
    assert [s["score"] for s in sources] == sorted((s["score"] for s in sources), reverse=True)
    assert jeu["secrete"] not in json.dumps(contenu)
    # Ce qu'il rend s'interroge tel quel.
    erreur, trouve = appeler(client, jetons("alice"), "rechercher", question="méthodes", assistant=sources[0]["id"])
    assert not erreur and trouve["passages"]
    # Bob lit `secrete` : elle se classe pour lui.
    erreur, bob = appeler(client, jetons("bob"), "trouver_collections", question="le secret de Bob")
    assert not erreur and bob["sources"][0]["id"] == jeu["secrete"]


def test_trouver_collections_ne_rend_rien_sans_ressemblance_et_borne_la_limite(client, jeu, theatre_branche, jetons):
    erreur, contenu = appeler(client, jetons("alice"), "trouver_collections", question="xylophone zinzolin")
    assert not erreur and contenu["sources"] == []
    erreur, contenu = appeler(client, jetons("alice"), "trouver_collections", question="notes méthodes textes ouverts équipe", limite=1)
    assert not erreur and len(contenu["sources"]) == 1
    erreur, contenu = appeler(client, jetons("alice"), "trouver_collections", question="notes méthodes textes ouverts équipe", limite=500)
    assert not erreur and 2 <= len(contenu["sources"]) <= 10


def test_l_apparieur_du_catalogue_suit_la_configuration(monkeypatch):
    from app.harnais.apparieur import ApparieurEmbeddings, ApparieurSacDeMots
    from app.services import assistant_recherche as moteur

    assert isinstance(moteur.apparieur_catalogue(), ApparieurSacDeMots)
    monkeypatch.setattr(app.config.settings, "catalogue_embeddings_url", "https://modeles.fake-domain.name/v1/")
    assert isinstance(moteur.apparieur_catalogue(), ApparieurSacDeMots), "sans modèle : sac de mots"
    monkeypatch.setattr(app.config.settings, "catalogue_embeddings_modele", "modele-e")
    monkeypatch.setattr(app.config.settings, "catalogue_embeddings_cle", "clef")
    a = moteur.apparieur_catalogue()
    assert isinstance(a, ApparieurEmbeddings) and (a.url, a.modele, a.jeton) == ("https://modeles.fake-domain.name", "modele-e", "clef")


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


def _publier_avec_secrete(client, en_tant_que, jeu, ident: str, monkeypatch) -> str:
    """Un assistant où `secrete` est une source ordinaire (`selon_question`) : le plan de Bob la vise bel et bien."""
    monkeypatch.setattr(app.config.settings, "auth_enabled", False)
    en_tant_que(SUPERADMIN)
    sources = [
        {"id": jeu[k], "type": "collection", "regime": r, "rang": i}
        for i, (k, r) in enumerate([("mienne", "toujours"), ("partagee", "selon_question"), ("secrete", "selon_question")], start=1)
    ]
    assert client.put(f"/api/assistants/{ident}", json=fiche_d_essai(jeu, ident, sources=sources).model_dump(mode="json")).status_code == 200
    assert client.post(f"/api/assistants/{ident}/publier").status_code == 200
    monkeypatch.setattr(app.config.settings, "auth_enabled", True)
    client.app.dependency_overrides.clear()
    return ident


def test_une_personne_sans_droit_ne_recoit_aucun_passage_de_la_collection_secrete(client, en_tant_que, jeu, ident_assistant, theatre_branche, jetons, monkeypatch):
    assistant_publie = _publier_avec_secrete(client, en_tant_que, jeu, ident_assistant, monkeypatch)
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


# ─── Ce que `rechercher` rend : peu, court, citable (essai d'un agent sur la bêta) ──────


#: Un passage de la taille de ceux d'OpenRAG sur la bêta (1,4 à 2,2 Ko) : 20 d'entre eux faisaient 28 à 45 Ko.
LONG = " ".join(["Le budget de la commune est voté avant le 15 avril de l'exercice auquel il s'applique."] * 18)


@pytest.fixture
def passages_longs(theatre_branche, jeu):
    """Vingt-cinq passages longs par collection : le moteur en fusionne 20, plus que la limite par défaut."""
    from tests.harnais.conftest import passage

    theatre_branche.passages = {nom: [passage(nom, f"{cle}-doc", r, score=1 - r / 100, texte=f"{cle} {r} : {LONG}") for r in range(1, 26)] for cle, nom in jeu.items()}
    return theatre_branche


def test_rechercher_rend_huit_passages_par_defaut_et_vingt_au_plus(client, assistant_publie, passages_longs, jetons):
    entetes = jetons("alice")
    erreur, contenu = appeler(client, entetes, "rechercher", question="budget", assistant=assistant_publie)
    assert not erreur and len(contenu["passages"]) == 8
    assert len(appeler(client, entetes, "rechercher", question="budget", assistant=assistant_publie, limite=3)[1]["passages"]) == 3
    assert len(appeler(client, entetes, "rechercher", question="budget", assistant=assistant_publie, limite=20)[1]["passages"]) == 20
    # Au-delà de 20, 20 ; en deçà de 1, 1 : la borne ne fait pas une erreur que le modèle devrait comprendre.
    assert len(appeler(client, entetes, "rechercher", question="budget", assistant=assistant_publie, limite=500)[1]["passages"]) == 20
    assert len(appeler(client, entetes, "rechercher", question="budget", assistant=assistant_publie, limite=0)[1]["passages"]) == 1


def test_la_limite_ne_coupe_pas_le_moteur(client, assistant_publie, passages_longs, jetons):
    """Le moteur cherche et fusionne comme avant ; seuls les premiers passages fusionnés sont rendus."""
    erreur, huit = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie)
    _, vingt = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie, limite=20)
    assert [p["url"].split("?")[0] for p in huit["passages"]] == [p["url"].split("?")[0] for p in vingt["passages"][:8]]


def test_le_texte_est_tronque_proprement_et_le_lien_reste_intact(client, assistant_publie, passages_longs, jetons):
    from app.mcp import serveur

    originaux = [p.texte for ps in passages_longs.passages.values() for p in ps]
    erreur, contenu = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie)
    assert not erreur
    for p in contenu["passages"]:
        assert len(p["texte"]) <= serveur.TEXTE_MAX + 1 and p["texte"].endswith("…")
        debut = p["texte"][:-1]
        assert len(debut) > serveur.TEXTE_MAX - 100
        assert any(o.startswith(debut) and o[len(debut)] == " " for o in originaux)  # coupé entre deux mots
        assert p["url"].startswith("https://mycollections.fake-domain.name/api/openrag/extract/") and "sig=" in p["url"] and "…" not in p["url"]
    # Un texte court n'est pas touché.
    assert serveur._extrait("Court.", serveur.TEXTE_MAX) == "Court."


def test_la_consigne_de_citation_est_dans_la_description_et_dans_la_sortie(client, assistant_publie, theatre_branche, jetons):
    outils = {o["name"]: o for o in rpc(client, "tools/list", entetes=jetons()).json()["result"]["tools"]}
    description = outils["rechercher"]["description"]
    assert "cite chaque passage" in description and "`url`" in description and "[titre](url)" in description
    assert "si aucun passage ne répond, dis-le" in description
    assert outils["rechercher"]["inputSchema"]["properties"]["limite"]["type"] == "integer"
    assert (
        "en premier" in outils["trouver_collections"]["description"]
        and "tout voir" in outils["lister_sources"]["description"]
        and outils["proposer_sources"]["description"].startswith("Facultatif")
    )
    erreur, contenu = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie)
    assert not erreur and "[titre](url)" in contenu["consigne_de_citation"]


def test_aucun_passage_hors_droits_meme_avec_la_limite_maximale(client, en_tant_que, jeu, ident_assistant, passages_longs, jetons, monkeypatch):
    assistant = _publier_avec_secrete(client, en_tant_que, jeu, ident_assistant, monkeypatch)
    erreur, bob = appeler(client, jetons("bob"), "rechercher", question="budget", assistant=assistant, limite=20)
    assert not erreur and any(p["collection"]["id"] == jeu["secrete"] for p in bob["passages"])  # témoin positif
    erreur, alice = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant, limite=20)
    assert not erreur and len(alice["passages"]) == 20
    assert jeu["secrete"] not in json.dumps(alice)


def test_taille_d_une_reponse_avant_apres(client, assistant_publie, passages_longs, jetons, monkeypatch):
    """La taille d'une réponse de `rechercher` : avant (20 passages en texte intégral), après (8, extraits)."""
    from app.mcp import serveur

    _, apres = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie)
    monkeypatch.setattr(serveur, "TEXTE_MAX", 10**6)
    _, avant = appeler(client, jetons("alice"), "rechercher", question="budget", assistant=assistant_publie, limite=20)
    octets_avant, octets_apres = (len(json.dumps(c, ensure_ascii=False, indent=2).encode()) for c in (avant, apres))
    print(f"\nrechercher : avant {octets_avant} octets (20 passages), après {octets_apres} octets (8 passages)")
    assert octets_avant > 25_000 and octets_apres < octets_avant / 3


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


def test_un_jeton_de_mirai_chat_groupes_courts_et_chemins_sous_un_second_claim(client, jeu, theatre_branche, jetons, monkeypatch):
    """Le client de MirAI Chat garde `groups` en noms courts ; ses chemins complets arrivent sous un second claim.
    Sans le réglage, ce jeton n'entre pas ; avec, il a les droits de la personne, ni plus ni moins."""
    alice = IDENTITES["alice"]
    courts = [g.rsplit("/", 1)[-1] for g in alice.groups]
    jeton = jetons("alice", azp="mirai-beta", aud=["mycollections-front"], groups=courts, groupes_mycollections=list(alice.groups))
    assert rpc(client, "tools/list", entetes=jeton).status_code == 403  # défaut : seul `groups` est lu
    monkeypatch.setattr(app.config.settings, "claims_groupes", "groupes_mycollections,groups")
    assert rpc(client, "tools/list", entetes=jeton).status_code == 200
    erreur, contenu = appeler(client, jeton, "lister_sources")
    assert not erreur and {jeu["mienne"], jeu["partagee"]} <= {a["id"] for a in contenu["assistants"]} and jeu["secrete"] not in json.dumps(contenu)
    # Le jeton du front (pas de second claim) entre toujours ; un second claim en noms courts ne donne rien.
    assert rpc(client, "tools/list", entetes=jetons("alice")).status_code == 200
    assert rpc(client, "tools/list", entetes=jetons("alice", groups=list(alice.groups), groupes_mycollections=courts)).status_code == 403
    # Un second claim vide (personne sans groupe) l'emporte sur `groups` : pas d'entrée.
    assert rpc(client, "tools/list", entetes=jetons("alice", groupes_mycollections=[])).status_code == 403


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
