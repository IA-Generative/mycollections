from app.services.doublons import candidats, similarite


def test_les_titres_proches_se_reconnaissent():
    assert similarite("Fichier des élus", "Répertoire national des élus") >= 0.45
    assert similarite("Fichier des élus", "Codes NATINF") < 0.45


def test_candidats_tries_par_proximite():
    demandes = [{"id": 1, "titre": "Codes NATINF"}, {"id": 2, "titre": "Répertoire national des élus"}, {"id": 3, "titre": "Élus municipaux"}]
    ids = [d["id"] for d in candidats("Répertoire des élus municipaux", demandes)]
    assert ids and 1 not in ids and ids[0] in (2, 3)
    assert all("similarite" in d for d in candidats("élus", demandes))
