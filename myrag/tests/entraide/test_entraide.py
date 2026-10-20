"""Le réseau d'entraide (lot G1) : appels, brouillon puis publication, réponses, demandes en référence."""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.conftest import SUPERADMIN, personne
from tests.unit.test_regle1_usage_frequence import DEMANDE

APPEL = {"type": "cherche", "titre": "Qui connaît la base Sirene ?", "texte": "Je cherche un collègue qui l'a déjà exploitée."}


def _creer(client, en_tant_que, auteur="auteur", **champs):
    en_tant_que(personne(auteur))
    r = client.post("/api/entraide/appels", json={**APPEL, **champs})
    assert r.status_code == 201, r.text
    return r.json()["appel"]


def test_un_appel_naît_brouillon_puis_se_publie(client, en_tant_que):
    appel = _creer(client, en_tant_que)
    assert appel["etat"] == "brouillon" and appel["est_mon_appel"] is True
    # Un brouillon n'est visible que de son auteur.
    en_tant_que(personne("autre"))
    assert client.get(f"/api/entraide/appels/{appel['id']}").status_code == 404
    assert appel["id"] not in [a["id"] for a in client.get("/api/entraide").json()["appels"]]
    en_tant_que(personne("auteur"))
    assert appel["id"] in [a["id"] for a in client.get("/api/entraide").json()["appels"]]
    publie = client.post(f"/api/entraide/appels/{appel['id']}/publier")
    assert publie.status_code == 200 and publie.json()["appel"]["etat"] == "publie"
    assert client.post(f"/api/entraide/appels/{appel['id']}/publier").status_code == 409
    en_tant_que(personne("autre"))
    lu = client.get(f"/api/entraide/appels/{appel['id']}").json()["appel"]
    assert lu["etat"] == "publie" and lu["est_mon_appel"] is False


@pytest.mark.parametrize("type_", ["cherche", "propose"])
def test_les_types_rediges(client, en_tant_que, type_):
    assert _creer(client, en_tant_que, type=type_)["type"] == type_


def test_le_type_donnee_se_demande_sur_les_demandes(client, en_tant_que):
    en_tant_que(personne("auteur"))
    assert client.post("/api/entraide/appels", json={**APPEL, "type": "donnee"}).status_code == 422
    assert client.post("/api/entraide/appels", json={**APPEL, "etat": "publie"}).status_code == 422
    assert client.post("/api/entraide/appels", json={**APPEL, "titre": "  "}).status_code == 422


def test_les_demandes_apparaissent_par_reference(client, en_tant_que):
    en_tant_que(personne("demandeur"))
    demande = client.post("/api/demandes", json=DEMANDE).json()["demande"]
    en_tant_que(personne("lecteur"))
    appels = client.get("/api/entraide", params={"type": "donnee"}).json()["appels"]
    ligne = next(a for a in appels if a["demande_id"] == demande["id"])
    assert ligne["type"] == "donnee" and ligne["par_reference"] is True and ligne["id"] == f"demande:{demande['id']}"
    lu = client.get(f"/api/entraide/appels/{ligne['id']}").json()["appel"]
    assert lu["titre"] == demande["titre"]
    # La demande n'est pas copiée : aucune ligne entraide_appel, et on n'y répond pas ici.
    assert client.post(f"/api/entraide/appels/{ligne['id']}/reponses", json={"texte": "x"}).status_code == 409
    assert all(a["par_reference"] is False for a in client.get("/api/entraide", params={"type": "cherche"}).json()["appels"])


def test_repondre_clore(client, en_tant_que):
    appel = _creer(client, en_tant_que)
    ident = appel["id"]
    en_tant_que(personne("repondant"))
    assert client.post(f"/api/entraide/appels/{ident}/reponses", json={"texte": "Je connais."}).status_code == 404  # brouillon d'autrui
    en_tant_que(personne("auteur"))
    client.post(f"/api/entraide/appels/{ident}/publier")
    en_tant_que(personne("repondant"))
    r = client.post(f"/api/entraide/appels/{ident}/reponses", json={"texte": "Je connais."})
    assert r.status_code == 201 and r.json()["reponse"]["de_moi"] is True
    assert client.post(f"/api/entraide/appels/{ident}/reponses", json={"texte": " "}).status_code == 422
    # Clore : l'auteur ou l'administration, pas un tiers.
    assert client.post(f"/api/entraide/appels/{ident}/clore").status_code == 403
    en_tant_que(personne("auteur"))
    lu = client.get(f"/api/entraide/appels/{ident}").json()["appel"]
    assert [x["texte"] for x in lu["reponses"]] == ["Je connais."] and lu["reponses"][0]["de_moi"] is False
    assert client.post(f"/api/entraide/appels/{ident}/clore").json()["appel"]["etat"] == "clos"
    assert client.post(f"/api/entraide/appels/{ident}/clore").status_code == 409
    assert client.post(f"/api/entraide/appels/{ident}/reponses", json={"texte": "Trop tard"}).status_code == 409


def test_l_administration_peut_clore(client, en_tant_que):
    appel = _creer(client, en_tant_que)
    en_tant_que(personne("auteur"))
    client.post(f"/api/entraide/appels/{appel['id']}/publier")
    en_tant_que(SUPERADMIN)
    assert client.post(f"/api/entraide/appels/{appel['id']}/clore").json()["appel"]["etat"] == "clos"


def test_lier_une_demande(client, en_tant_que):
    en_tant_que(personne("demandeur"))
    demande = client.post("/api/demandes", json=DEMANDE).json()["demande"]
    appel = _creer(client, en_tant_que)
    r = client.post(f"/api/entraide/appels/{appel['id']}/liens", json={"demande_id": demande["id"]})
    assert r.json()["demandes_liees"] == [demande["id"]]
    assert client.post(f"/api/entraide/appels/{appel['id']}/liens", json={"demande_id": "inconnue"}).status_code == 404


def test_drapeau_faux_404_sur_tout_le_prefixe(client, en_tant_que, capacites):
    appel = _creer(client, en_tant_que)
    capacites(entraide=False)
    for methode, chemin in [
        ("get", "/api/entraide"),
        ("post", "/api/entraide/appels"),
        ("get", f"/api/entraide/appels/{appel['id']}"),
        ("post", f"/api/entraide/appels/{appel['id']}/publier"),
        ("post", f"/api/entraide/appels/{appel['id']}/clore"),
        ("post", f"/api/entraide/appels/{appel['id']}/reponses"),
    ]:
        assert getattr(client, methode)(chemin).status_code == 404, chemin


def test_le_routeur_n_est_importe_que_par_main():
    app = pathlib.Path(__file__).resolve().parents[2] / "app"
    importeurs = set()
    for fichier in app.rglob("*.py"):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            noms = []
            if isinstance(noeud, ast.ImportFrom):
                noms = [noeud.module or ""] + [f"{noeud.module}.{a.name}" for a in noeud.names]
            elif isinstance(noeud, ast.Import):
                noms = [a.name for a in noeud.names]
            if "app.routers.entraide" in noms:
                importeurs.add(fichier.name)
        if fichier.name != "entraide.py" and "app.routers import entraide" in fichier.read_text(encoding="utf-8"):
            importeurs.add(fichier.name)
    assert importeurs == {"main.py"}


# ── G2 : recommander avant de publier ────────────────────────────────────────────────────────


@pytest.fixture
def existant(creer_collection, purger, ident_assistant, client, en_tant_que):
    """Une collection lisible, une collection privée de quelqu'un d'autre, un assistant publié."""
    import uuid

    n = uuid.uuid4().hex[:6]
    lisible, privee = f"t-reco-{n}-a", f"t-reco-{n}-b"
    creer_collection(lisible, personne("gestionnaire"), titre="Registre Sirene des entreprises", description="Base Sirene : établissements et entreprises")
    creer_collection(privee, personne("gestionnaire"), scope="private", scope_groups=[], titre="Sirene confidentielle", description="Base Sirene interne")
    en_tant_que(personne("gestionnaire"))
    fiche = {
        "assistant": ident_assistant,
        "titre": "Assistant Sirene",
        "description": "Répond sur la base Sirene",
        "sources": [{"id": lisible, "type": "collection", "regime": "toujours", "rang": 1}],
        "consignes": [{"id": "defaut", "quand": "toujours"}],
    }
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche).status_code == 200
    assert client.post(f"/api/assistants/{ident_assistant}/publier").status_code == 200
    yield {"lisible": lisible, "privee": privee, "assistant": ident_assistant}
    purger(lisible)
    purger(privee)


def test_les_recommandations_montrent_ce_que_la_personne_peut_lire(client, en_tant_que, existant):
    appel = _creer(client, en_tant_que, auteur="chercheur")
    r = client.get(f"/api/entraide/appels/{appel['id']}/recommandations")
    assert r.status_code == 200, r.text
    corps = r.json()
    assert existant["lisible"] in [c["id"] for c in corps["collections"]]
    assert existant["privee"] not in [c["id"] for c in corps["collections"]]
    assert existant["assistant"] in [a["id"] for a in corps["assistants"]]
    # L'appel est toujours un brouillon : les recommandations précèdent la publication.
    assert client.get(f"/api/entraide/appels/{appel['id']}").json()["appel"]["etat"] == "brouillon"


def test_les_recommandations_reviennent_a_l_auteur(client, en_tant_que, existant):
    appel = _creer(client, en_tant_que)
    en_tant_que(personne("autre"))
    assert client.get(f"/api/entraide/appels/{appel['id']}/recommandations").status_code == 404  # brouillon d'autrui
    en_tant_que(personne("auteur"))
    client.post(f"/api/entraide/appels/{appel['id']}/publier")
    en_tant_que(personne("autre"))
    assert client.get(f"/api/entraide/appels/{appel['id']}/recommandations").status_code == 403


def test_les_roles_anonymes_des_soutiens_d_une_demande_voisine(client, en_tant_que):
    en_tant_que(personne("demandeur"))
    demande = client.post("/api/demandes", json=DEMANDE).json()["demande"]
    en_tant_que(personne("fournisseur"))
    client.post(f"/api/demandes/{demande['id']}/soutenir", json={"role": "fournisseur"})
    appel = _creer(client, en_tant_que, auteur="chercheur", titre=demande["titre"], texte=demande["usage"])
    corps = client.get(f"/api/entraide/appels/{appel['id']}/recommandations").json()
    voisine = next(d for d in corps["demandes_voisines"] if d["demande_id"] == demande["id"])
    assert voisine["roles"].get("fournisseur") == 1
    assert "sub_hash" not in str(corps) and "hash" not in " ".join(voisine)


def test_recommandations_drapeau_faux(client, en_tant_que, capacites):
    appel = _creer(client, en_tant_que)
    capacites(entraide=False)
    assert client.get(f"/api/entraide/appels/{appel['id']}/recommandations").status_code == 404
