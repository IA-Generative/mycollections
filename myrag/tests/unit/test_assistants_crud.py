"""La fiche d'un assistant par l'API : qui la voit, qui la modifie, ce qu'on en montre. Les
droits sont calculés à partir du jeton et des collections ; jamais d'un paramètre du client."""

from __future__ import annotations

import copy

import pytest

from app.auth import CurrentUser
from tests.conftest import SUPERADMIN, personne

ALICE = personne("alice")
BOB = personne("bob")
LECTEUR = personne("lecteur")
DEHORS = CurrentUser(sub="dehors", username="d", groups=["/g/autre"])


@pytest.fixture
def cols(creer_collection, purger):
    """Alice gère `a` (groupe des testeurs) ; Bob gère `b` (privée)."""
    import uuid

    n = uuid.uuid4().hex[:6]
    c = {"a": f"t-crud-{n}-a", "b": f"t-crud-{n}-b"}
    creer_collection(c["a"], ALICE, titre="Collection d'Alice")
    creer_collection(c["b"], BOB, scope="private", scope_groups=[], titre="Collection de Bob")
    yield c
    for nom in c.values():
        purger(nom)


def _fiche(ident: str, *sources: str, **modifs) -> dict:
    f = {
        "assistant": ident,
        "titre": "Assistant d'essai",
        "sources": [{"id": s, "type": "collection", "regime": "toujours", "rang": i + 1} for i, s in enumerate(sources)],
        "consignes": [{"id": "defaut", "quand": "toujours"}, {"id": "ciblee", "quand": "une question ciblée", "chercher": [{"source": s} for s in sources]}],
    }
    f.update(modifs)
    return f


def _url(ident: str, suite: str = "") -> str:
    return f"/api/assistants/{ident}{suite}"


def test_le_gestionnaire_cree_lit_et_publie(client, en_tant_que, cols, ident_assistant):
    en_tant_que(ALICE)
    r = client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"]))
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["mes_droits"] == {"ecrire": True} and corps["version"] is None and corps["sources_masquees"] == 0
    assert "cree_par_hash" not in corps["assistant"] and corps["fiche"]["sources"][0]["id"] == cols["a"]
    p = client.post(_url(ident_assistant, "/publier"))
    assert p.status_code == 200 and p.json()["version"] == 1 and p.json()["nouvelle"] is True
    assert client.post(_url(ident_assistant, "/publier")).json()["nouvelle"] is False
    assert client.get(_url(ident_assistant)).json()["version"] == 1
    assert [v["numero"] for v in client.get(_url(ident_assistant, "/versions")).json()["versions"]] == [1]


def test_un_lecteur_voit_sans_modifier_et_un_tiers_ne_voit_rien(client, en_tant_que, cols, ident_assistant):
    en_tant_que(ALICE)
    assert client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"])).status_code == 200
    en_tant_que(LECTEUR)
    r = client.get(_url(ident_assistant))
    assert r.status_code == 200 and r.json()["mes_droits"] == {"ecrire": False}
    assert ident_assistant in {a["id"] for a in client.get("/api/assistants").json()["assistants"]}
    assert client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"], titre="Repris")).status_code == 403
    assert client.post(_url(ident_assistant, "/publier")).status_code == 403
    en_tant_que(DEHORS)
    assert client.get(_url(ident_assistant)).status_code == 404
    assert client.get(_url(ident_assistant, "/versions")).status_code == 404
    assert ident_assistant not in {a["id"] for a in client.get("/api/assistants").json()["assistants"]}


def test_assembler_demande_de_gerer_chaque_collection(client, en_tant_que, cols, ident_assistant):
    en_tant_que(ALICE)
    r = client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"], cols["b"]))
    assert r.status_code == 403, "Alice ne gère pas la collection de Bob"
    en_tant_que(BOB)
    assert client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"])).status_code == 403
    en_tant_que(SUPERADMIN)
    assert client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"], cols["b"])).status_code == 200


def test_une_collection_illisible_n_est_pas_montree(client, en_tant_que, cols, ident_assistant):
    en_tant_que(SUPERADMIN)
    assert client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"], cols["b"])).status_code == 200
    en_tant_que(LECTEUR)
    corps = client.get(_url(ident_assistant)).json()
    assert [s["id"] for s in corps["fiche"]["sources"]] == [cols["a"]] and corps["sources_masquees"] == 1
    assert cols["b"] not in str(corps), "le nom d'une collection illisible ne sort jamais"
    assert corps["fiche"]["consignes"][1]["chercher"] == [{"source": cols["a"], "avec": None}]
    liste = {a["id"]: a for a in client.get("/api/assistants").json()["assistants"]}
    assert liste[ident_assistant]["sources_masquees"] == 1 and cols["b"] not in str(liste[ident_assistant])
    # Alice gère `a` mais pas `b` : elle voit l'assistant, ne le modifie pas, et ne voit pas `b`.
    en_tant_que(ALICE)
    corps = client.get(_url(ident_assistant)).json()
    assert corps["mes_droits"] == {"ecrire": False} and corps["sources_masquees"] == 1


def test_on_ne_reprend_pas_un_assistant_en_changeant_ses_sources(client, en_tant_que, cols, ident_assistant):
    en_tant_que(BOB)
    assert client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["b"])).status_code == 200
    en_tant_que(ALICE)
    r = client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"]))
    assert r.status_code == 404, "l'assistant de Bob (collection privée) n'existe pas pour Alice"


@pytest.mark.parametrize(
    "modif, statut",
    [
        (lambda f, c: f.update(assistant="autre-id"), 422),
        (lambda f, c: f["sources"].append({"id": "inconnue-xyz", "type": "collection"}), 422),
        (lambda f, c: f.update(sources=[]), 422),
        (lambda f, c: f["consignes"][1]["chercher"].append({"source": "pas-une-source"}), 422),
        (lambda f, c: f.update(titre=""), 422),
    ],
)
def test_une_fiche_invalide_est_refusee(client, en_tant_que, cols, ident_assistant, modif, statut):
    en_tant_que(ALICE)
    f = copy.deepcopy(_fiche(ident_assistant, cols["a"]))
    modif(f, cols)
    assert client.put(_url(ident_assistant), json=f).status_code == statut


def test_un_assistant_sans_collection_est_a_son_createur(client, en_tant_que, ident_assistant):
    en_tant_que(ALICE)
    fiche = {"assistant": ident_assistant, "titre": "Connecteur seul", "sources": [{"id": "referentiel-eligibilite", "type": "connecteur", "regime": "toujours"}]}
    assert client.put(_url(ident_assistant), json=fiche).status_code == 200
    assert client.get(_url(ident_assistant)).json()["mes_droits"] == {"ecrire": True}
    en_tant_que(LECTEUR)
    assert client.get(_url(ident_assistant)).status_code == 404, "une source connecteur n'ouvre aucun droit"
    en_tant_que(SUPERADMIN)
    assert client.get(_url(ident_assistant)).status_code == 200


def test_drapeau_faux_tout_est_404(client, en_tant_que, cols, ident_assistant, capacites):
    en_tant_que(ALICE)
    assert client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"])).status_code == 200
    capacites(assistants=False)
    for methode, url in (("get", "/api/assistants"), ("get", _url(ident_assistant)), ("get", _url(ident_assistant, "/versions")), ("post", _url(ident_assistant, "/publier"))):
        r = getattr(client, methode)(url)
        assert r.status_code == 404 and "Fonction désactivée" in r.text, (methode, url)
    assert client.put(_url(ident_assistant), json=_fiche(ident_assistant, cols["a"])).status_code == 404
