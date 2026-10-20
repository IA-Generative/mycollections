"""L'usage d'UNE collection (fiche) : combien de questions, combien de collègues — sous le seuil,
on ne dit pas combien de personnes, et jamais ce qu'elles ont demandé."""

import json
import os
import sqlite3
from unittest.mock import AsyncMock, patch

from app.services import accueil
from app.services.openrag_client import ReponseChat
from tests.conftest import personne


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
        cls.return_value.chat = AsyncMock(return_value=ReponseChat.model_validate({"choices": [{"message": {"content": "Réponse."}}], "extra": ""}))
        r = client.post(f"/api/playground/{nom}/chat", json={"question": question})
    assert r.status_code == 200, r.text


def _usage(client, en_tant_que, qui, nom):
    en_tant_que(qui)
    return client.get(f"/api/collections/{nom}/usage")


def test_le_seuil_est_celui_de_l_accueil():
    assert accueil.personnes_publiables(accueil.SEUIL_PERSONNES - 1) is None
    assert accueil.personnes_publiables(accueil.SEUIL_PERSONNES) == accueil.SEUIL_PERSONNES


def test_personnes_null_a_deux_entier_a_trois(client, en_tant_que, creer_collection, nom):
    createur = personne("createur-usage")
    creer_collection(nom, createur)
    for n in (2, 2, 3):
        _demander(client, en_tant_que, personne(n), nom)
    r = _usage(client, en_tant_que, personne(9), nom)
    assert r.status_code == 200, r.text
    assert r.json() == {"fenetre_jours": 30, "questions": 3, "personnes": None}
    _demander(client, en_tant_que, personne(4), nom)
    assert _usage(client, en_tant_que, personne(9), nom).json() == {"fenetre_jours": 30, "questions": 4, "personnes": 3}


def test_les_essais_du_createur_ne_comptent_pas(client, en_tant_que, creer_collection, nom):
    createur = personne("createur-essais-usage")
    creer_collection(nom, createur)
    for _ in range(3):
        _demander(client, en_tant_que, createur, nom)
    _demander(client, en_tant_que, personne(2), nom)
    # Le même chiffre, quel que soit le lecteur — le créateur compris.
    assert _usage(client, en_tant_que, createur, nom).json()["questions"] == 1
    assert _usage(client, en_tant_que, personne(7), nom).json()["questions"] == 1


def test_seules_les_questions_de_la_fenetre_comptent(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, personne("createur-fenetre"))
    _demander(client, en_tant_que, personne(2), nom)
    _sql("UPDATE usage_question SET cree_le = datetime('now', '-45 days') WHERE collection_name = ?", (nom,))
    _demander(client, en_tant_que, personne(3), nom)
    assert _usage(client, en_tant_que, personne(2), nom).json()["questions"] == 1


def test_jamais_le_texte_d_une_question(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, personne("createur-texte"))
    for n in (2, 3, 4):
        _demander(client, en_tant_que, personne(n), nom, "Ma question très personnelle sur mon dossier")
    corps = json.dumps(_usage(client, en_tant_que, personne(2), nom).json(), ensure_ascii=False)
    assert "personnelle" not in corps and "personne-" not in corps


def test_qui_ne_lit_pas_la_collection_recoit_404(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, personne("createur-prive"))
    _sql("UPDATE collections SET scope = 'group', scope_groups_json = '[\"/g/un-autre-groupe\"]' WHERE name = ?", (nom,))
    from app.auth import CurrentUser

    etranger = CurrentUser(sub="etranger", username="etranger", groups=["/g/ailleurs"])
    assert _usage(client, en_tant_que, etranger, nom).status_code == 404
    assert _usage(client, en_tant_que, etranger, "t-n-existe-pas-du-tout").status_code == 404
