"""L'auteur d'une demande, et la boucle de satisfaction (décision PO du 2026-09-21).

- l'auteur tient d'office le rôle « demandeur » : il n'est pas compté parmi les soutiens ;
- quand la collection de la demande est publiée à tous, la demande passe « à confirmer » et
  l'auteur est sollicité ; oui → réalisée ; non → retour en chantier, motif, garant prévenu ;
- sans réponse sous CONFIRMATION_JOURS (5), elle est réalisée « sans réponse » ;
- quand la demande se termine, le courriel de l'auteur est effacé.
"""

import os
import sqlite3
from datetime import timedelta

import pytest

from app.models.db import utcnow
from app.services import relais
from tests.conftest import SUPERADMIN, personne
from tests.unit.test_regle1_usage_frequence import DEMANDE

AUTEUR, GARANT, AUTRE = personne("auteur"), personne("garant"), personne("autre")


@pytest.fixture
def cloche(monkeypatch):
    """Ce que le relais aurait porté à la cloche : (destinataires, texte)."""
    envois: list[tuple[list[str], str]] = []
    monkeypatch.setattr(relais, "planifier", lambda dest, corps, app="mescollections": envois.append((list(dest), corps)))
    return envois


def _sql(requete: str, params=()):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        lignes = con.execute(requete, params).fetchall()
        con.commit()
        return lignes
    finally:
        con.close()


def _hash(qui):
    from app.services.pseudo import condenser
    return condenser(qui.sub)


def _deposer(client, en_tant_que):
    en_tant_que(AUTEUR)
    r = client.post("/api/demandes", json={**DEMANDE, "titre": "Jurisprudence des CAA", "contact": "auteur@interieur.gouv.fr"})
    assert r.status_code == 201, r.text
    return r.json()["demande"]


def _publier_a_tous(client, en_tant_que, creer_collection, nom, ident):
    """La collection de la demande franchit « publiée à tous » (par l'administration, forcée)."""
    creer_collection(nom)
    _sql("UPDATE collections SET demande_id = ? WHERE name = ?", (ident, nom))
    en_tant_que(SUPERADMIN)
    r = client.post(f"/api/collections/{nom}/etat", json={"cible": "publiee_tous", "forcer": True, "motif": "essai"})
    assert r.status_code == 200, r.text


# ─── Le rôle « demandeur » ──────────────────────────────────────────────────────────────────

def test_l_auteur_est_demandeur_d_office_sans_compter_parmi_les_soutiens(client, en_tant_que):
    d = _deposer(client, en_tant_que)
    assert d["je_suis_demandeur"] is True and d["nb_soutiens"] == 0 and d["roles"] == {"demandeur": 1}
    en_tant_que(AUTRE)
    vue = client.get(f"/api/demandes/{d['id']}").json()["demande"]
    assert vue["je_suis_demandeur"] is False and vue["roles"] == {"demandeur": 1}
    client.post(f"/api/demandes/{d['id']}/soutenir", json={"role": "soutien"})
    vue = client.get(f"/api/demandes/{d['id']}").json()["demande"]
    assert vue["nb_soutiens"] == 1 and vue["roles"] == {"demandeur": 1, "soutien": 1}


def test_demandeur_n_est_pas_un_role_que_l_on_prend(client, en_tant_que):
    d = _deposer(client, en_tant_que)
    en_tant_que(AUTRE)
    assert client.post(f"/api/demandes/{d['id']}/soutenir", json={"role": "demandeur"}).status_code == 422


# ─── La boucle de satisfaction ──────────────────────────────────────────────────────────────

def test_publiee_a_tous_la_demande_attend_l_avis_de_son_auteur(client, en_tant_que, creer_collection, nom, cloche):
    d = _deposer(client, en_tant_que)
    _publier_a_tous(client, en_tant_que, creer_collection, nom, d["id"])
    en_tant_que(AUTEUR)
    vue = client.get(f"/api/demandes/{d['id']}").json()["demande"]
    assert vue["etat"] == "a_confirmer" and vue["collection_name"] == nom and vue["confirmation_avant"]
    sollicite = [e for e in cloche if _hash(AUTEUR) in e[0] and "Répond-elle à votre besoin" in e[1]]
    assert sollicite and "5 jours" in sollicite[0][1]
    assert sollicite[0][0] == [_hash(AUTEUR)]   # à l'auteur seul


def test_oui_la_demande_est_realisee_et_le_courriel_efface(client, en_tant_que, creer_collection, nom, cloche):
    d = _deposer(client, en_tant_que)
    _publier_a_tous(client, en_tant_que, creer_collection, nom, d["id"])
    en_tant_que(AUTEUR)
    r = client.post(f"/api/demandes/{d['id']}/satisfaction", json={"satisfait": True})
    assert r.status_code == 200, r.text
    assert (r.json()["demande"]["etat"], r.json()["demande"]["satisfaction"]) == ("realisee", "oui")
    assert _sql("SELECT contact FROM demande WHERE id = ?", (d["id"],)) == [(None,)]


def test_non_la_demande_redevient_un_chantier_et_le_garant_est_prevenu(client, en_tant_que, creer_collection, nom, cloche):
    d = _deposer(client, en_tant_que)
    en_tant_que(GARANT)
    client.post(f"/api/demandes/{d['id']}/soutenir", json={"role": "garant"})
    _publier_a_tous(client, en_tant_que, creer_collection, nom, d["id"])
    en_tant_que(AUTEUR)
    assert client.post(f"/api/demandes/{d['id']}/satisfaction", json={"satisfait": False}).status_code == 422   # le motif est dû
    r = client.post(f"/api/demandes/{d['id']}/satisfaction", json={"satisfait": False, "motif": "Il manque les arrêts de 2025."})
    assert r.status_code == 200, r.text
    vue = r.json()["demande"]
    assert (vue["etat"], vue["satisfaction"], vue["motif_insatisfaction"]) == ("chantier", "non", "Il manque les arrêts de 2025.")
    assert vue["confirmation_avant"] is None
    prevenu = [e for e in cloche if e[0] == [_hash(GARANT)]]
    assert prevenu and "Il manque les arrêts de 2025." in prevenu[0][1]
    assert _sql("SELECT contact FROM demande WHERE id = ?", (d["id"],)) == [("auteur@interieur.gouv.fr",)]   # la demande continue


def test_seul_l_auteur_ou_l_administration_repond(client, en_tant_que, creer_collection, nom, cloche):
    d = _deposer(client, en_tant_que)
    _publier_a_tous(client, en_tant_que, creer_collection, nom, d["id"])
    en_tant_que(AUTRE)
    assert client.post(f"/api/demandes/{d['id']}/satisfaction", json={"satisfait": True}).status_code == 403
    en_tant_que(SUPERADMIN)
    assert client.post(f"/api/demandes/{d['id']}/satisfaction", json={"satisfait": True}).status_code == 200


def test_on_ne_confirme_pas_une_demande_qui_n_attend_rien(client, en_tant_que):
    d = _deposer(client, en_tant_que)
    r = client.post(f"/api/demandes/{d['id']}/satisfaction", json={"satisfait": True})
    assert r.status_code == 409 and "n'attend pas" in r.text


def test_sans_reponse_sous_5_jours_elle_est_realisee_sans_reponse(client, en_tant_que, creer_collection, nom, cloche):
    d = _deposer(client, en_tant_que)
    _publier_a_tous(client, en_tant_que, creer_collection, nom, d["id"])
    il_y_a = lambda jours: (utcnow() - timedelta(days=jours)).strftime("%Y-%m-%d %H:%M:%S.%f")  # noqa: E731
    _sql("UPDATE demande SET confirmation_demandee_le = ? WHERE id = ?", (il_y_a(4), d["id"]))
    en_tant_que(AUTRE)
    assert client.get(f"/api/demandes/{d['id']}").json()["demande"]["etat"] == "a_confirmer"   # 4 jours : on attend
    _sql("UPDATE demande SET confirmation_demandee_le = ? WHERE id = ?", (il_y_a(6), d["id"]))
    liste = {x["id"]: x for x in client.get("/api/demandes").json()["demandes"]}
    assert (liste[d["id"]]["etat"], liste[d["id"]]["satisfaction"]) == ("realisee", "sans_reponse")
    assert _sql("SELECT contact FROM demande WHERE id = ?", (d["id"],)) == [(None,)]
    fil = client.get(f"/api/demandes/{d['id']}/journal").json()["evenements"]
    assert any(e["type"] == "demande.etat" and (e.get("detail") or {}).get("satisfaction") == "sans_reponse" for e in fil)


def test_clore_une_demande_efface_le_courriel(client, en_tant_que):
    d = _deposer(client, en_tant_que)
    assert client.post(f"/api/demandes/{d['id']}/clore", json={"motif": "doublon oublié"}).status_code == 200
    assert _sql("SELECT contact FROM demande WHERE id = ?", (d["id"],)) == [(None,)]


def test_la_cloche_de_l_auteur_porte_la_demande_a_confirmer(client, en_tant_que, creer_collection, nom, cloche):
    from app.services import collectif_store as store
    import asyncio
    d = _deposer(client, en_tant_que)
    _publier_a_tous(client, en_tant_que, creer_collection, nom, d["id"])
    suivi = asyncio.run(store.suivi_pour(_hash(AUTEUR)))
    mienne = next(x for x in suivi["demandes"] if x["id"] == d["id"])
    assert mienne["etat"] == "a_confirmer" and mienne["je_suis_demandeur"] is True and mienne["confirmation_avant"]


def test_regle_pure_de_l_echeance():
    from app.services.etats import confirmation_echue
    maintenant = utcnow()
    assert confirmation_echue("a_confirmer", maintenant - timedelta(days=6), maintenant, 5) is True
    assert confirmation_echue("a_confirmer", maintenant - timedelta(days=4), maintenant, 5) is False
    assert confirmation_echue("chantier", maintenant - timedelta(days=60), maintenant, 5) is False
    assert confirmation_echue("a_confirmer", None, maintenant, 5) is False
