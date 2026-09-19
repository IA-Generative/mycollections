"""L'accueil : dire à celui qui partage ce que son travail a rendu possible — sans jamais
garder ce que ses collègues ont demandé — et offrir une collection à essayer."""

import asyncio
import os
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import SUPERADMIN, personne


def _sql(requete, params=()):
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    try:
        lignes = con.execute(requete, params).fetchall()
        con.commit()
        return lignes
    finally:
        con.close()


def _demander(client, en_tant_que, qui, nom, question="Que dit le texte ?"):
    en_tant_que(qui)
    with patch("app.routers.playground.OpenRAGClient") as cls:
        cls.return_value.health_check = AsyncMock(return_value=True)
        cls.return_value.chat = AsyncMock(return_value={"choices": [{"message": {"content": "Réponse."}}], "extra": ""})
        r = client.post(f"/api/playground/{nom}/chat", json={"question": question})
    assert r.status_code == 200, r.text


def test_la_mesure_ne_garde_jamais_le_texte_de_la_question(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    _demander(client, en_tant_que, personne(2), nom, "Ma question très personnelle sur mon dossier")
    colonnes = {r[1] for r in _sql("PRAGMA table_info(usage_question)")}
    assert colonnes == {"id", "collection_name", "auteur_hash", "canal", "cree_le"}
    ligne = _sql("SELECT auteur_hash, canal FROM usage_question WHERE collection_name = ?", (nom,))[0]
    assert ligne[1] == "bac-a-sable" and ligne[0] and "personne-2" not in ligne[0], "un condensé, jamais le sub"


def test_mes_essais_ne_comptent_pas_ceux_des_collegues_oui(client, en_tant_que, creer_collection, nom):
    moi = personne("createur")
    creer_collection(nom, moi, titre="Codes de test")
    _demander(client, en_tant_que, moi, nom)                      # mon propre essai
    for n in (2, 2, 3, 4):                                        # 4 questions de 3 collègues
        _demander(client, en_tant_que, personne(n), nom)
    en_tant_que(moi)
    r = client.get("/api/accueil/mes-collections").json()
    ligne = next(l for l in r["collections"] if l["name"] == nom)
    assert ligne["titre"] == "Codes de test" and ligne["questions"] == 4
    assert r["questions"] >= 4 and r["personnes"] is not None and r["personnes"] >= 3
    assert r["fenetre_jours"] == 30


def test_sous_le_seuil_on_ne_dit_pas_combien_de_personnes(client, en_tant_que, creer_collection, nom):
    moi = personne("seul-" + nom[-6:])
    creer_collection(nom, moi)
    _demander(client, en_tant_que, personne(2), nom)
    _demander(client, en_tant_que, personne(3), nom)
    en_tant_que(moi)
    r = client.get("/api/accueil/mes-collections").json()
    assert r["questions"] == 2 and r["personnes"] is None


def test_une_question_ancienne_sort_de_la_fenetre(client, en_tant_que, creer_collection, nom):
    moi = personne("vieux-" + nom[-6:])
    creer_collection(nom, moi)
    _demander(client, en_tant_que, personne(2), nom)
    _sql("UPDATE usage_question SET cree_le = datetime('now', '-45 days') WHERE collection_name = ?", (nom,))
    en_tant_que(moi)
    assert client.get("/api/accueil/mes-collections").json()["questions"] == 0


def test_qui_ne_gere_rien_recoit_une_liste_vide_pas_un_reproche(client, en_tant_que):
    en_tant_que(personne("nouveau-venu"))
    r = client.get("/api/accueil/mes-collections").json()
    assert r["collections"] == [] and r["actives"] == 0 and r["personnes"] is None


def test_les_signalements_ouverts_me_sont_rappeles(client, en_tant_que, creer_collection, nom):
    moi = personne("garant-" + nom[-6:])
    creer_collection(nom, moi)
    en_tant_que(personne(2))
    assert client.post(f"/api/collections/{nom}/signalements", json={"motif": "obsolete", "texte": "Le barème cité date de 2022."}).status_code in (200, 201)
    en_tant_que(moi)
    r = client.get("/api/accueil/mes-collections").json()
    assert r["signalements_ouverts"] == 1


def _jeu(nom, questions):
    from app.database import async_session
    from app.models.db import EvalDataset
    import json

    async def _f():
        async with async_session() as s:
            s.add(EvalDataset(collection_name=nom, name=f"{nom}-evaluation", description="", questions_json=json.dumps(questions)))
            await s.commit()
    asyncio.run(_f())


def test_l_exemple_vient_du_jeu_d_evaluation_d_une_collection_publiee_a_tous(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, titre="Codes de test")
    _jeu(nom, [{"id": "q1", "question": "Quel texte réprime le vol ?"},
               {"id": "q2", "question": "Hors sujet ?", "out_of_scope": True}])
    en_tant_que(personne(5))
    assert all((e or {}).get("name") != nom for e in [client.get("/api/accueil/exemple").json()["exemple"]]), \
        "une collection en cours de vérification ne s'offre pas en exemple"
    _sql("UPDATE collections SET etat_collab = 'publiee_tous', scope = 'public', categorie = 'securite-delinquance' WHERE name = ?", (nom,))
    vus = {client.get("/api/accueil/exemple").json()["exemple"]["name"] for _ in range(40)}
    assert nom in vus
    for _ in range(40):
        e = client.get("/api/accueil/exemple").json()["exemple"]
        if e["name"] == nom:
            assert e == {"name": nom, "titre": "Codes de test", "categorie": "securite-delinquance",
                         "categorie_libelle": "Sécurité et délinquance", "question": "Quel texte réprime le vol ?",
                         "autres": e["autres"]}
            break


def test_une_question_d_utilisateur_ne_s_affiche_jamais_a_l_accueil(client, en_tant_que, creer_collection, nom):
    """Les avis négatifs alimentent la banque du bac à sable ; pas la page d'accueil."""
    creer_collection(nom)
    _sql("UPDATE collections SET etat_collab = 'publiee_tous', scope = 'public' WHERE name = ?", (nom,))
    en_tant_que(personne(2))
    client.post("/api/feedback/ingest", json={"collection": nom, "question": "Mon cas personnel ?", "response": "…", "rating": -1})
    en_tant_que(personne(5))
    for _ in range(30):
        e = client.get("/api/accueil/exemple").json()["exemple"]
        assert e is None or (e["name"] != nom and e["question"] != "Mon cas personnel ?")


def test_une_collection_que_je_ne_peux_pas_lire_ne_m_est_pas_offerte(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)                                  # portée : le groupe des testeurs
    _jeu(nom, [{"id": "q1", "question": "Réservée ?"}])
    _sql("UPDATE collections SET etat_collab = 'publiee_tous' WHERE name = ?", (nom,))
    from app.auth import CurrentUser
    en_tant_que(CurrentUser(sub="hors-groupe", username="x", groups=["/g/ailleurs"]))
    for _ in range(30):
        e = client.get("/api/accueil/exemple").json()["exemple"]
        assert e is None or e["name"] != nom


def test_la_purge_emporte_la_mesure(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    _demander(client, en_tant_que, personne(2), nom)
    assert _sql("SELECT COUNT(*) FROM usage_question WHERE collection_name = ?", (nom,))[0][0] == 1
    en_tant_que(SUPERADMIN)
    client.post(f"/api/collections/{nom}/archive")
    with patch("app.routers.collections.OpenRAGClient") as cls:
        cls.return_value.delete_partition = AsyncMock(return_value={})
        assert client.delete(f"/api/collections/{nom}").status_code == 200
    assert _sql("SELECT COUNT(*) FROM usage_question WHERE collection_name = ?", (nom,))[0][0] == 0
