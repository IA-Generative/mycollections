"""Les sites déclarés (bulle « + IA » de l'extension) : la règle des motifs, qui les déclare,
ce que chacun reçoit dans `GET /api/v1/sites`, l'audience du jeton, la purge."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.auth import CurrentUser
from app.services import sites
from tests.conftest import SUPERADMIN, personne

ALICE = personne("alice-sites")
LECTEUR = personne("lecteur-sites")
DEHORS = CurrentUser(sub="dehors-sites", username="d", groups=["/g/autre"])


# ─── La règle des motifs ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("https://www.legifrance.gouv.fr/codes/*", "https://www.legifrance.gouv.fr/codes/*"),
        ("  https://WWW.Fake-Domain.name/  ", "https://www.fake-domain.name/"),
        ("https://*.fake-domain.name/*", "https://*.fake-domain.name/*"),
        ("https://intranet.fake-domain.name/dossiers/*?onglet=*", "https://intranet.fake-domain.name/dossiers/*?onglet=*"),
    ],
)
def test_un_motif_valide_est_normalise(brut, attendu):
    assert sites.valider_motif(brut) == attendu


@pytest.mark.parametrize(
    "brut, raison",
    [
        ("", "vide"),
        ("http://www.fake-domain.name/*", "https://"),
        ("https://*/*", "explicite"),
        ("https://*.fr/*", "deux niveaux"),
        ("https://www.fake-domain.name", "chemin"),
        ("https://www.fake-domain.name:8443/*", "port"),
        ("https://www.fake-domain.name/page#ancre", "fragment"),
        ("<all_urls>", "https://"),
        ("https://www.fake-domain.name/a b", "espace"),
        ("https://" + "a" * 300 + ".fr/", "300"),
    ],
)
def test_un_motif_invalide_est_refuse_avec_sa_raison(brut, raison):
    with pytest.raises(sites.MotifInvalide, match=raison):
        sites.valider_motif(brut)


def test_les_motifs_sont_dedoublonnes_et_plafonnes():
    assert sites.valider_motifs(["https://a.fake-domain.name/*", "https://A.fake-domain.name/*"]) == ["https://a.fake-domain.name/*"]
    with pytest.raises(sites.MotifInvalide, match="20 motifs"):
        sites.valider_motifs([f"https://s{i}.fake-domain.name/*" for i in range(21)])
    with pytest.raises(sites.MotifInvalide, match="Motif 2"):
        sites.valider_motifs(["https://a.fake-domain.name/*", "ftp://x"])


@pytest.mark.parametrize(
    "url, motif, oui",
    [
        ("https://www.legifrance.gouv.fr/codes/article_lc/X", "https://www.legifrance.gouv.fr/codes/*", True),
        ("https://www.legifrance.gouv.fr/jorf/id/X", "https://www.legifrance.gouv.fr/codes/*", False),
        ("http://www.legifrance.gouv.fr/codes/X", "https://www.legifrance.gouv.fr/codes/*", False),
        ("https://intranet.fake-domain.name/x", "https://*.fake-domain.name/*", True),
        ("https://fake-domain.name/x", "https://*.fake-domain.name/*", True),
        ("https://fake-domain.name.evil.fr/x", "https://*.fake-domain.name/*", False),
        ("https://evilfake-domain.name/x", "https://*.fake-domain.name/*", False),
        ("https://www.fake-domain.name/page#section", "https://www.fake-domain.name/page", True),
        ("https://www.fake-domain.name/page?onglet=2", "https://www.fake-domain.name/page", False),
        ("https://www.fake-domain.name/page?onglet=2", "https://www.fake-domain.name/page?*", True),
        ("https://WWW.FAKE-DOMAIN.NAME/", "https://www.fake-domain.name/", True),
    ],
)
def test_correspond_suit_la_regle_des_match_patterns(url, motif, oui):
    assert sites.correspond(url, motif) is oui


# ─── Les routes ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def cols(creer_collection, purger):
    n = uuid.uuid4().hex[:6]
    c = {"a": f"t-sites-{n}-a", "privee": f"t-sites-{n}-p"}
    creer_collection(c["a"], ALICE, titre="Collection d'exemple")
    creer_collection(c["privee"], ALICE, scope="private", scope_groups=[], titre="Collection privée")
    yield c
    for nom in c.values():
        purger(nom)
    import asyncio

    for nom in c.values():
        asyncio.run(sites.supprimer_cible("collection", nom))


def _url(nom: str) -> str:
    return f"/api/collections/{nom}/sites"


def test_le_gestionnaire_declare_les_sites_et_un_lecteur_les_lit(client, en_tant_que, cols):
    en_tant_que(ALICE)
    r = client.put(_url(cols["a"]), json={"motifs": ["https://WWW.fake-domain.name/guides/*", "https://www.fake-domain.name/guides/*"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"motifs": ["https://www.fake-domain.name/guides/*"], "max": sites.MOTIFS_MAX}
    en_tant_que(LECTEUR)
    assert client.get(_url(cols["a"])).json()["motifs"] == ["https://www.fake-domain.name/guides/*"]
    assert client.put(_url(cols["a"]), json={"motifs": []}).status_code == 403
    en_tant_que(DEHORS)
    assert client.get(_url(cols["a"])).status_code == 404


def test_un_motif_refuse_dit_pourquoi(client, en_tant_que, cols):
    en_tant_que(ALICE)
    r = client.put(_url(cols["a"]), json={"motifs": ["https://*/*"]})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "motif" and "explicite" in r.json()["detail"]["message"]
    assert client.get(_url(cols["a"])).json()["motifs"] == []


def test_la_liste_ne_rend_que_ce_que_la_personne_lit(client, en_tant_que, cols):
    en_tant_que(ALICE)
    assert client.put(_url(cols["a"]), json={"motifs": ["https://www.fake-domain.name/commun/*"]}).status_code == 200
    assert client.put(_url(cols["privee"]), json={"motifs": ["https://www.fake-domain.name/commun/*", "https://prive.fake-domain.name/*"]}).status_code == 200

    def cibles(user):
        en_tant_que(user)
        r = client.get("/api/v1/sites")
        assert r.status_code == 200, r.text
        corps = r.json()
        assert corps["ttl_s"] == sites.TTL_S
        return {s["motif"]: {c["id"] for c in s["cibles"]} for s in corps["sites"]}

    assert cibles(ALICE)["https://www.fake-domain.name/commun/*"] == {cols["a"], cols["privee"]}
    assert cibles(ALICE)["https://prive.fake-domain.name/*"] == {cols["privee"]}
    vu_du_lecteur = cibles(LECTEUR)
    assert vu_du_lecteur.get("https://www.fake-domain.name/commun/*") == {cols["a"]}
    assert "https://prive.fake-domain.name/*" not in vu_du_lecteur, "une collection illisible ne dévoile pas ses sites"
    vu_de_dehors = cibles(DEHORS)
    assert not ({cols["a"], cols["privee"]} & set().union(*vu_de_dehors.values())) if vu_de_dehors else True


def test_les_sites_d_un_assistant(client, en_tant_que, cols, ident_assistant):
    en_tant_que(ALICE)
    fiche = {"assistant": ident_assistant, "titre": "Assistant d'exemple", "sources": [{"id": cols["a"], "type": "collection", "regime": "toujours", "rang": 1}]}
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche).status_code == 200
    r = client.put(f"/api/assistants/{ident_assistant}/sites", json={"motifs": ["https://www.fake-domain.name/sejour/*"]})
    assert r.status_code == 200, r.text
    # Jamais publié : seul qui le gère le reçoit (pour l'essayer) ; un lecteur, non.
    assert any(c["id"] == ident_assistant for s in client.get("/api/v1/sites").json()["sites"] for c in s["cibles"])
    en_tant_que(LECTEUR)
    assert not any(c["id"] == ident_assistant for s in client.get("/api/v1/sites").json()["sites"] for c in s["cibles"])
    assert client.put(f"/api/assistants/{ident_assistant}/sites", json={"motifs": []}).status_code == 403
    en_tant_que(ALICE)
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    en_tant_que(LECTEUR)
    rendu = [c for s in client.get("/api/v1/sites").json()["sites"] for c in s["cibles"] if c["id"] == ident_assistant]
    assert rendu == [{"type": "assistant", "id": ident_assistant, "titre": "Assistant d'exemple"}]
    en_tant_que(SUPERADMIN)
    assert client.put(f"/api/assistants/{ident_assistant}/sites", json={"motifs": []}).status_code == 200


def test_assistants_eteints_pas_de_sites_d_assistant(client, en_tant_que, cols, ident_assistant, capacites):
    en_tant_que(ALICE)
    fiche = {"assistant": ident_assistant, "titre": "Assistant d'exemple", "sources": [{"id": cols["a"], "type": "collection", "regime": "toujours", "rang": 1}]}
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche).status_code == 200
    assert client.put(f"/api/assistants/{ident_assistant}/sites", json={"motifs": ["https://www.fake-domain.name/eteint/*"]}).status_code == 200
    capacites(assistants=False)
    assert client.get(f"/api/assistants/{ident_assistant}/sites").status_code == 404
    assert "https://www.fake-domain.name/eteint/*" not in {s["motif"] for s in client.get("/api/v1/sites").json()["sites"]}


def test_un_jeton_d_un_autre_service_est_refuse(monkeypatch):
    from app.config import settings
    from app.routers import embed

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "recherche_audience", "mycollections-front")
    monkeypatch.setattr(settings, "recherche_clients_audience", "mysearch")
    with pytest.raises(HTTPException) as e:
        embed._audience({"azp": "un-autre-client", "aud": ["account"]})
    assert e.value.status_code == 403 and e.value.detail["code"] == "audience_mismatch"
    embed._audience({"azp": "mycollections-front"})
    embed._audience({"azp": "mirai-extension", "aud": ["account", "mycollections-front"]})


def test_la_purge_d_une_collection_efface_ses_sites():
    import asyncio

    nom = f"t-sites-purge-{uuid.uuid4().hex[:6]}"

    async def scenario():
        await sites.remplacer("collection", nom, ["https://www.fake-domain.name/*"])
        assert await sites.lire("collection", nom)
        assert await sites.supprimer_cible("collection", nom) == 1
        return await sites.lire("collection", nom)

    assert asyncio.run(scenario()) == []


# ─── Sans jeton : 401, ou la liste anonyme de débogage ──────────────────────────────────────


@pytest.fixture
def ouverte(creer_collection, purger):
    nom = f"t-sites-pub-{uuid.uuid4().hex[:6]}"
    creer_collection(nom, ALICE, scope="public", titre="Collection ouverte")
    yield nom
    purger(nom)
    import asyncio

    asyncio.run(sites.supprimer_cible("collection", nom))


def test_sans_jeton_401_par_defaut(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "sites_anonymes", False)
    r = client.get("/api/v1/sites")
    assert r.status_code == 401


def test_sans_jeton_la_liste_anonyme_ne_montre_que_l_ouvert(client, en_tant_que, cols, ouverte, monkeypatch):
    from app.config import settings

    en_tant_que(ALICE)
    assert client.put(_url(ouverte), json={"motifs": ["https://www.fake-domain.name/ouvert/*"]}).status_code == 200
    assert client.put(_url(cols["a"]), json={"motifs": ["https://www.fake-domain.name/groupe/*"]}).status_code == 200
    assert client.put(_url(cols["privee"]), json={"motifs": ["https://www.fake-domain.name/prive/*"]}).status_code == 200
    from app.main import app

    app.dependency_overrides.clear()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "sites_anonymes", True)
    r = client.get("/api/v1/sites")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["anonyme"] is True and r.headers["cache-control"] == "no-store"
    motifs = {s["motif"]: [c["id"] for c in s["cibles"]] for s in corps["sites"]}
    assert motifs.get("https://www.fake-domain.name/ouvert/*") == [ouverte]
    assert "https://www.fake-domain.name/groupe/*" not in motifs and "https://www.fake-domain.name/prive/*" not in motifs


def test_un_jeton_present_ne_prend_jamais_la_voie_anonyme(monkeypatch):
    """Avec un en-tête Authorization, `_anonyme` laisse la main à la vérification du jeton."""
    import asyncio

    from fastapi.security import HTTPAuthorizationCredentials

    from app.config import settings
    from app.routers import embed

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "sites_anonymes", True)
    assert asyncio.run(embed._anonyme(HTTPAuthorizationCredentials(scheme="Bearer", credentials="jeton"))) is None
