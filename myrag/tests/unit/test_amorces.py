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
        assert a["garant_pressenti"] and a["grille"]["source_licence"] and a["etat_import"] == "jamais"


def test_l_import_est_reserve_aux_administrateurs(client, en_tant_que):
    en_tant_que(personne(1))
    assert client.post("/api/amorces/natinf/import").status_code == 403


def test_l_import_est_idempotent_et_nomme_le_connecteur_manquant(client, en_tant_que, purger):
    purger("amorce-natinf")
    en_tant_que(SUPERADMIN)
    r1 = client.post("/api/amorces/natinf/import")
    r2 = client.post("/api/amorces/natinf/import")
    assert r1.status_code == 501 and r2.status_code == 501
    assert "natinf" in r1.json()["detail"]
    fiche = client.get("/api/collections/amorce-natinf").json()
    assert fiche["etat_collab"] == "amorcee" and fiche["garant_pressenti"]
    grille = client.get("/api/collections/amorce-natinf/grille").json()["grille"]
    assert grille["source_licence"]
    amorce = next(a for a in client.get("/api/amorces").json()["amorces"] if a["id"] == "natinf")
    assert amorce["etat_import"] == "echec" and amorce["collection_name"] == "amorce-natinf"
    assert client.get("/api/collections").json()["collections"].count(fiche) <= 1
    purger("amorce-natinf")
