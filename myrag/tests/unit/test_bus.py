"""Ce que le bus de la bêta peut faire POUR un testeur — sous secret, avec le même
condensé que le chemin par jeton — et ce que Mes collections lui relaie en retour."""

import base64

import pytest

from app.services import relais
from tests.conftest import personne
from tests.unit.test_regle1_usage_frequence import DEMANDE

SECRET = "secret-de-test-du-bus"
ENTETE = {"X-Bus-Secret": SECRET}


@pytest.fixture
def bus(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "bus_secret", SECRET)
    monkeypatch.setattr(settings, "bus_url", "http://bus.test")
    envois: list[tuple[list[str], str]] = []

    async def faux_envoyer(destinataires, corps, app="mescollections"):
        envois.append((list(destinataires), corps))
        return True
    monkeypatch.setattr(relais, "envoyer", faux_envoyer)
    return envois


def test_sans_secret_configure_le_bus_est_refuse_en_503(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "bus_secret", "")
    assert client.get("/api/bus/demandes?visiteur=x", headers=ENTETE).status_code == 503


def test_un_mauvais_secret_est_refuse(client, bus):
    assert client.get("/api/bus/demandes?visiteur=x", headers={"X-Bus-Secret": "faux"}).status_code == 401
    assert client.get("/api/bus/demandes?visiteur=x").status_code == 401


def test_le_bus_depose_et_soutient_avec_le_meme_condense(client, bus, en_tant_que):
    r = client.post("/api/bus/demandes", json={**DEMANDE, "visiteur": "personne-bus", "app": "monassistant"}, headers=ENTETE)
    assert r.status_code == 201, r.text
    ident = r.json()["demande"]["id"]
    assert r.json()["url"].endswith(f"/demandes/{ident}")
    # Le même sub par le chemin du jeton : c'est bien MA demande, je la suis déjà.
    en_tant_que(personne("bus"))
    fiche = client.get(f"/api/demandes/{ident}").json()["demande"]
    assert fiche["abonne"] is True and fiche["nb_soutiens"] == 0
    r = client.post(f"/api/bus/demandes/{ident}/soutenir", json={"visiteur": "personne-bus"}, headers=ENTETE)
    assert r.status_code == 200 and r.json()["demande"]["nb_soutiens"] == 1
    assert client.get(f"/api/demandes/{ident}").json()["demande"]["soutenue_par_moi"] is True


def test_le_bus_dedoublonne_en_tapant(client, bus):
    client.post("/api/bus/demandes", json={**DEMANDE, "titre": "Répertoire national des élus", "visiteur": "a"}, headers=ENTETE)
    r = client.get("/api/bus/demandes?visiteur=a&q=fichier%20des%20elus", headers=ENTETE)
    assert r.status_code == 200 and any("élus" in d["titre"] for d in r.json()["demandes"])
    assert all("similarite" in d for d in r.json()["demandes"])


def test_le_suivi_pour_la_cloche(client, bus, en_tant_que):
    ident = client.post("/api/bus/demandes", json={**DEMANDE, "titre": "Interventions SDIS", "visiteur": "auteur"}, headers=ENTETE).json()["demande"]["id"]
    for n in range(4):
        client.post(f"/api/bus/demandes/{ident}/soutenir", json={"visiteur": f"s{n}"}, headers=ENTETE)
    s = client.get("/api/bus/suivi?visiteur=auteur", headers=ENTETE).json()
    assert [d["id"] for d in s["demandes"]] == [ident] and s["seuil_chantier"] == 5
    s2 = client.get("/api/bus/suivi?visiteur=quelqu-un-d-autre", headers=ENTETE).json()
    assert s2["demandes"] == [] and [d["id"] for d in s2["presque_au_seuil"]] == [ident], "à un soutien du seuil"


def test_le_seuil_atteint_est_relaye_aux_abonnes(client, bus, en_tant_que):
    ident = client.post("/api/bus/demandes", json={**DEMANDE, "visiteur": "auteur"}, headers=ENTETE).json()["demande"]["id"]
    for n in range(5):
        client.post(f"/api/bus/demandes/{ident}/soutenir", json={"visiteur": f"s{n}"}, headers=ENTETE)
    assert client.post(f"/api/bus/demandes/{ident}/soutenir", json={"visiteur": "g", "role": "garant"}, headers=ENTETE).json()["demande"]["etat"] == "chantier"
    assert bus, "un relais est parti"
    destinataires, corps = bus[-1]
    from app.services.pseudo import condenser
    assert condenser("auteur") in destinataires and condenser("s0") in destinataires and "chantier" in corps
    assert "auteur" not in " ".join(destinataires), "des condensés, jamais le visiteur"


def test_le_signalement_d_un_document_avec_version(client, bus, en_tant_que, creer_collection, nom, monkeypatch):
    creer_collection(nom, personne("garant"))
    en_tant_que(personne("garant"))
    assert client.post(f"/api/collections/{nom}/etat", json={"cible": "en_controle"}).status_code == 200
    corps = {"visiteur": "lectrice", "collection": nom, "document": "CAA-24LY00001-2024-01-10.md",
             "texte": "Annulé par le CE le 2 juin 2025.", "version": {"nom": "arret-v2.md", "contenu_base64": base64.b64encode(b"# v2").decode()}}
    assert client.post("/api/bus/signalements", json=corps, headers=ENTETE).status_code == 404, "non publiée à tous : on ne dit rien"
    from app.services import collectif_store as store
    import asyncio
    from tests.conftest import SUPERADMIN
    en_tant_que(SUPERADMIN)
    assert client.post(f"/api/collections/{nom}/etat", json={"cible": "publiee_tous", "forcer": True, "motif": "test"}).status_code == 200
    r = client.post("/api/bus/signalements", json=corps, headers=ENTETE)
    assert r.status_code == 201, r.text
    assert r.json()["signalement"]["motif"] == "obsolete" and "Document cité" in r.json()["signalement"]["texte"]
    p = r.json()["proposition"]
    assert p["cible_type"] == "fichier" and p["avant"] == "CAA-24LY00001-2024-01-10.md" and p["apres"].endswith("arret-v2.md")
    en_tant_que(personne("garant"))
    assert len(client.get(f"/api/collections/{nom}/propositions").json()["propositions"]) == 1
    trop = {**corps, "version": {"nom": "x.bin", "contenu_base64": base64.b64encode(b"0" * (5 * 1024 * 1024 + 1)).decode()}}
    assert client.post("/api/bus/signalements", json=trop, headers=ENTETE).status_code == 413


def test_les_capacites_tiennent_aussi_le_bus(client, bus, capacites):
    capacites(demandes=False)
    assert client.get("/api/bus/demandes?visiteur=x", headers=ENTETE).status_code == 404
