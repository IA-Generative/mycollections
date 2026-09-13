"""Les amorces : un catalogue versionné, un import idempotent, un connecteur nommé."""

from tests.conftest import SUPERADMIN, personne


def test_le_catalogue_est_lisible(client, en_tant_que):
    en_tant_que(personne(1))
    r = client.get("/api/amorces")
    assert r.status_code == 200
    amorces = r.json()["amorces"]
    ids = {a["id"] for a in amorces}
    assert {"natinf", "ssmsi-delinquance", "ta-caa-ceseda", "rne-elus", "sdis-interventions", "baac"} <= ids
    for a in amorces:
        assert a["garant_pressenti"] and a["grille"]["source_licence"] and a["nb_questions"] == 20
        assert "questions" not in a, "les questions ne sont pas servies par le catalogue"


def test_l_import_est_reserve_aux_administrateurs(client, en_tant_que):
    en_tant_que(personne(1))
    assert client.post("/api/amorces/natinf/import").status_code == 403


def test_un_connecteur_manquant_est_nomme(client, en_tant_que, purger, monkeypatch):
    from app.routers import amorces as routeur
    monkeypatch.delitem(routeur.CONNECTEURS, "natinfo")
    purger("amorce-natinf")
    en_tant_que(SUPERADMIN)
    r1 = client.post("/api/amorces/natinf/import")
    r2 = client.post("/api/amorces/natinf/import")
    assert r1.status_code == 501 and r2.status_code == 501 and "natinfo" in r1.json()["detail"]
    fiche = client.get("/api/collections/amorce-natinf").json()
    assert fiche["etat_collab"] == "amorcee" and fiche["garant_pressenti"]
    assert client.get("/api/collections/amorce-natinf/grille").json()["grille"]["source_licence"]
    amorce = next(a for a in client.get("/api/amorces").json()["amorces"] if a["id"] == "natinf")
    assert amorce["etat_import"] == "echec" and amorce["collection_name"] == "amorce-natinf"
    purger("amorce-natinf")


def test_vingt_questions_en_banque_et_couverture_dans_la_grille(client, en_tant_que, purger, monkeypatch):
    """L'import prépare tout : collection amorcée, grille pré-remplie, 20 questions, couverture constatée."""
    from app.routers import amorces as routeur

    async def faux(collection, entree, **k):
        return {"documents": 3, "lignes_importees": 42, "couverture": {"departements": 3, "annees": ["2019", "2024"]}}
    monkeypatch.setitem(routeur.CONNECTEURS, "sdis-interventions", faux)
    purger("amorce-sdis-interventions")
    en_tant_que(SUPERADMIN)
    r = client.post("/api/amorces/sdis-interventions/import?synchrone=true")
    assert r.status_code == 200, r.text
    assert r.json()["resultat"]["lignes_importees"] == 42
    banque = client.get("/api/collections/amorce-sdis-interventions/bank").json() if False else client.get("/api/playground/amorce-sdis-interventions/bank").json()
    assert banque["stats"]["imported"] == 20
    grille = client.get("/api/collections/amorce-sdis-interventions/grille").json()["grille"]
    assert grille["couverture"]["annees"] == ["2019", "2024"] and grille["source_licence"]
    journal = client.get("/api/collections/amorce-sdis-interventions/journal").json()["evenements"]
    assert any(e["type"] == "import.termine" and e["par"] == "robot:amorce:sdis-interventions" for e in journal)
    r2 = client.post("/api/amorces/sdis-interventions/import?synchrone=true")
    assert r2.status_code == 200
    assert client.get("/api/playground/amorce-sdis-interventions/bank").json()["stats"]["imported"] == 20, "rejouer ne double pas la banque"
    purger("amorce-sdis-interventions")


def test_un_import_qui_echoue_le_dit(client, en_tant_que, purger, monkeypatch):
    from app.routers import amorces as routeur

    async def casse(collection, entree, **k):
        raise RuntimeError("la source ne répond pas")
    monkeypatch.setitem(routeur.CONNECTEURS, "baac", casse)
    purger("amorce-baac")
    en_tant_que(SUPERADMIN)
    r = client.post("/api/amorces/baac/import?synchrone=true")
    assert r.status_code == 502 and "ne répond pas" in r.text
    amorce = next(a for a in client.get("/api/amorces").json()["amorces"] if a["id"] == "baac")
    assert amorce["etat_import"] == "echec" and "ne répond pas" in amorce["erreur"]
    purger("amorce-baac")


def test_le_critere_d_ouverture_compte_les_amorces_en_controle(client, en_tant_que, purger, monkeypatch):
    from app.routers import amorces as routeur

    async def rien(collection, entree, **k):
        return {"documents": 0}
    en_tant_que(SUPERADMIN)
    ids = ["natinf", "ssmsi-delinquance", "rne-elus"]
    for i in ids:
        monkeypatch.setitem(routeur.CONNECTEURS, next(e["connecteur"] for e in __import__("app.amorces", fromlist=["charger_catalogue"]).charger_catalogue() if e["id"] == i), rien)
        purger(f"amorce-{i}")
        client.post(f"/api/amorces/{i}/import?synchrone=true")
    ouverture = client.get("/api/amorces").json()["ouverture"]
    assert ouverture["requis"] == 3 and ouverture["en_controle"] == 0 and ouverture["ouverte"] is False
    for i in ids:
        assert client.post(f"/api/collections/amorce-{i}/etat", json={"cible": "en_controle", "forcer": True, "motif": "test"}).status_code == 200
    ouverture = client.get("/api/amorces").json()["ouverture"]
    assert ouverture["en_controle"] == 3 and ouverture["ouverte"] is True
    for i in ids:
        purger(f"amorce-{i}")
