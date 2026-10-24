"""Les doublons dans une collection Résana : un contenu identique n'est indexé qu'une fois, sans
bloquer personne ; le choix reste stable d'une passe à l'autre ; rien ne se perd quand l'original
disparaît. (Vérification de l'algorithme de `_comparer_et_appliquer`.)"""

from __future__ import annotations

from tests.unit.test_resana_routes import CREATEUR, ENTETE, _doc, _importer, _sources, faux, privee  # noqa: F401 — fixtures


def _fichiers_telecharges(faux) -> list[str]:
    return sorted(q.url.path.split("/")[-2] for q in faux.requetes if q.url.path.endswith("/fichier"))


def test_un_doublon_est_ecarte_avec_sa_raison(client, en_tant_que, faux, privee):
    faux.documents = [_doc("x", "# Note\n\nMême texte fictif."), _doc("y", "# Note\n\nMême texte fictif.")]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert _sources(privee) == ["note-x.md"] and travail["ecartes"] == 1
    assert "même contenu" in travail["documents_ecartes"][0]["raison"]


def test_le_choix_reste_stable_quand_l_ordre_change(client, en_tant_que, faux, privee):
    faux.documents = [_doc("x", "# Note\n\nMême texte fictif."), _doc("y", "# Note\n\nMême texte fictif.")]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    faux.documents.reverse()  # Résana rend la liste dans un autre ordre
    faux.envois.reset_mock()
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert _sources(privee) == ["note-x.md"]
    assert not faux.envois.await_count and not faux.openrag.delete_file.await_count


def test_un_doublon_ecarte_n_est_pas_retelecharge_a_chaque_passe(client, en_tant_que, faux, privee):
    faux.documents = [_doc("x", "# Note\n\nMême texte fictif."), _doc("y", "# Note\n\nMême texte fictif.")]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    faux.requetes.clear()
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert _fichiers_telecharges(faux) == [], "même version annoncée : ni l'original ni son doublon ne sont relus"


def test_quand_l_original_disparait_le_doublon_prend_le_relais(client, en_tant_que, faux, privee):
    faux.documents = [_doc("x", "# Note\n\nMême texte fictif."), _doc("y", "# Note\n\nMême texte fictif.")]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    faux.documents = [_doc("y", "# Note\n\nMême texte fictif.")]  # l'original est supprimé dans Résana
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert _sources(privee) == ["note-y.md"], "le contenu reste dans l'index, porté par le doublon"


def test_un_document_existant_garde_la_place_face_a_un_nouveau_doublon(client, en_tant_que, faux, privee):
    faux.documents = [_doc("x", "# Note\n\nTexte fictif.")]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    # Un nouveau document au contenu identique arrive EN TÊTE de liste.
    faux.documents = [_doc("a", "# Note\n\nTexte fictif."), _doc("x", "# Note\n\nTexte fictif.")]
    faux.envois.reset_mock()
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert _sources(privee) == ["note-x.md"] and not faux.envois.await_count


def test_un_doublon_qui_change_redevient_un_document(client, en_tant_que, faux, privee):
    faux.documents = [_doc("x", "# Note\n\nMême texte fictif."), _doc("y", "# Note\n\nMême texte fictif.")]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    faux.documents = [_doc("x", "# Note\n\nMême texte fictif."), _doc("y", "# Note\n\nTexte fictif désormais différent.")]
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert _sources(privee) == ["note-x.md", "note-y.md"]


def test_un_format_refuse_n_est_pas_retelecharge_tant_qu_il_ne_change_pas(client, en_tant_que, faux, privee):
    from tests.unit._faux_resana import DocFaux

    faux.documents.append(DocFaux(id="z", titre="Binaire fictif", nom_fichier="outil.exe", contenu=b"MZ\x90\x00", mime="application/octet-stream"))
    en_tant_que(CREATEUR)
    _importer(client, privee)
    faux.requetes.clear()
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert _fichiers_telecharges(faux) == []
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert travail["etat"] == "a_jour" and travail["ecartes"] == 1  # toujours signalé, sans être relu


def _lecture_echouee(faux, message):
    """OpenRAG reçoit le document mais n'arrive pas à le lire (tâche suivie jusqu'au bout)."""
    from unittest.mock import AsyncMock

    from app.services.openrag_client import EnvoiDocument, EtatTache

    faux.openrag.upload_document.side_effect = lambda partition, nom, contenu, mime, metadata=None, file_id=None: EnvoiDocument(file_id=file_id or nom, task_id="t-1")
    faux.openrag.task_state = AsyncMock(return_value=EtatTache(task_state="FAILED"))
    faux.openrag.task_error = AsyncMock(return_value=message)


def test_une_lecture_ratee_pour_de_bon_n_est_pas_renvoyee_a_chaque_passe(client, en_tant_que, faux, privee):
    _lecture_echouee(faux, "NoIndexableContentError")
    en_tant_que(CREATEUR)
    _importer(client, privee)
    faux.envois.reset_mock()
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert not faux.envois.await_count


def test_une_lecture_ratee_par_delai_est_retentee(client, en_tant_que, faux, privee, monkeypatch):
    from app.routers import ingest

    monkeypatch.setattr(ingest, "SUIVI_DOCUMENT_MAX_S", -1)  # « pas fini de lire » aussitôt
    _lecture_echouee(faux, "")
    from unittest.mock import AsyncMock

    from app.services.openrag_client import EtatTache

    faux.openrag.task_state = AsyncMock(return_value=EtatTache(task_state="RUNNING"))
    en_tant_que(CREATEUR)
    _importer(client, privee)
    assert client.get(f"/api/sources/resana/status/{privee}").json()["travail"]["en_erreur"] == 2
    faux.envois.reset_mock()
    faux.openrag.delete_file.reset_mock()
    faux.openrag.task_state = AsyncMock(return_value=EtatTache(task_state="SUCCESS"))
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert faux.envois.await_count == 2 and faux.openrag.delete_file.await_count == 2  # l'essai raté sort, le nouveau entre
    assert client.get(f"/api/sources/resana/status/{privee}").json()["travail"]["en_erreur"] == 0
