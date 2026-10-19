"""L'étape 4 de l'assistant (test technique) : trois questions suggérées, tirées du jeu de la
collection ou des titres de ses documents — jamais d'une question posée par un usager."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.routers.playground import questions_depuis_documents, questions_depuis_intertitres, titre_lisible
from app.services.openrag_client import FichierOpenRAG, MorceauOpenRAG
from tests.conftest import personne


def _fichiers(*noms):
    return [FichierOpenRAG(file_id=f"f{i}", filename=n) for i, n in enumerate(noms)]


def _suggestions(client, nom, fichiers=(), panne=False, passages=()):
    with patch("app.routers.playground.OpenRAGClient") as cls:
        if panne:
            cls.return_value.list_files = AsyncMock(side_effect=RuntimeError("OpenRAG absent"))
            cls.return_value.partition_chunks = AsyncMock(side_effect=RuntimeError("OpenRAG absent"))
        else:
            cls.return_value.list_files = AsyncMock(return_value=list(fichiers))
            cls.return_value.partition_chunks = AsyncMock(return_value=[MorceauOpenRAG(content=c) for c in passages])
        return client.get(f"/api/playground/{nom}/suggestions")


def test_un_titre_de_fichier_se_lit():
    assert titre_lisible("circulaire-peines_2026.pdf") == "circulaire peines 2026"
    assert titre_lisible("  note.md ") == "note"


def test_une_question_par_document_trois_au_plus_sans_doublon():
    qs = questions_depuis_documents(["guide-a.pdf", "guide_a.docx", "faq.md", "barème.pdf", "annexe.pdf"])
    assert qs == ["Que dit le document « guide a » ?", "Que dit le document « faq » ?", "Que dit le document « barème » ?"]
    assert questions_depuis_documents(["x.md", ""]) == []


def test_sans_jeu_les_titres_des_documents(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne(3))
    r = _suggestions(client, nom, _fichiers("note-de-controle.md", "faq-exemple.md"))
    assert r.status_code == 200, r.text
    assert r.json() == {"questions": ["Que dit le document « note de controle » ?", "Que dit le document « faq exemple » ?"], "origine": "documents"}


def test_le_jeu_passe_d_abord_jamais_une_question_d_usager(client, en_tant_que, creer_collection, nom):
    from app.services import questions_store

    createur = personne("createur-suggestions")
    creer_collection(nom, createur)
    asyncio.run(
        questions_store.importer_questions(nom, [{"id": "q1", "question": "Quel délai pour contester ?"}, {"id": "q2", "question": "Hors sujet ?", "out_of_scope": True}], None)
    )
    # Un avis d'usager promu en question : il ne doit jamais être suggéré.
    en_tant_que(personne("usager"))
    assert client.post("/api/feedback/ingest", json={"collection": nom, "question": "Ma question privée sur mon dossier ?", "response": "R.", "rating": -1}).status_code == 200
    en_tant_que(createur)
    avis = client.get(f"/api/feedback/{nom}").json()["feedback"][0]
    assert client.post(f"/api/feedback/{nom}/{avis['id']}/promote", json={"promote_to": "eval"}).status_code == 200
    r = _suggestions(client, nom, _fichiers("annexe.pdf", "guide.pdf"))
    corps = r.json()
    assert corps["origine"] == "jeu"
    assert corps["questions"][0] == "Quel délai pour contester ?"
    assert "Hors sujet ?" not in corps["questions"]
    assert all("privée" not in q for q in corps["questions"]), "une question d'usager ne se suggère pas"
    assert len(corps["questions"]) == 3


def test_openrag_injoignable_rend_ce_qu_on_a(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne(3))
    r = _suggestions(client, nom, panne=True)
    assert r.status_code == 200 and r.json() == {"questions": [], "origine": None}


def test_lecture_requise(client, en_tant_que, creer_collection, nom):
    from app.auth import CurrentUser

    creer_collection(nom)
    en_tant_que(CurrentUser(sub="etranger-suggestions", username="e", groups=["/g/ailleurs"]))
    assert _suggestions(client, nom).status_code == 404


def test_un_intertitre_donne_une_question_lisible():
    contenus = ["# Code de contrôle\n\nLe code est…", "Texte sans titre.", "## **Délais** :\nDeux mois.", "# Code de contrôle\nDoublon."]
    assert questions_depuis_intertitres(contenus) == ["Que dit le texte sur « Code de contrôle » ?", "Que dit le texte sur « Délais » ?"]


def test_les_intertitres_passent_avant_les_noms_de_fichiers(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne(3))
    r = _suggestions(client, nom, _fichiers("section-le-code-de-contr-le.md"), passages=["## Code de contrôle\nLe code…"])
    assert r.json()["questions"] == ["Que dit le texte sur « Code de contrôle » ?", "Que dit le document « section le code de contr le » ?"]
