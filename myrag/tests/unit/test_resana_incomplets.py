"""La qualité de chaque document Résana (#144) : notée à l'indexation, comptée dans l'état de la
collection, et « Ré-indexer les documents incomplets » renvoie ceux-là seuls, même inchangés."""

from __future__ import annotations

from app.routers import sources_resana
from tests.unit.test_resana_routes import CREATEUR, ENTETE, _doc, _importer, faux, privee  # noqa: F401 — fixtures

#: Ce que l'indexeur rend pour chaque document, par nom de fichier.
QUALITES = {
    "note-a.md": {"etat": "complet", "passages": 3, "sans_contexte": 0},
    "note-b.md": {"etat": "sans_contexte", "passages": 10, "sans_contexte": 4, "etapes": ["contextualize"]},
    "note-c.md": {"etat": "sans_texte"},
}


def _indexeur_qui_note(envoyes: list[str], qualites: dict[str, dict]):
    async def indexer(job_id, collection, nom, contenu, metadata=None, file_id=None):
        envoyes.append(nom)
        q = qualites.get(nom)
        erreur = "OpenRAG n'a pas pu lire : NO_INDEXABLE_CONTENT" if q and q["etat"] == "sans_texte" else None
        return file_id, erreur, q

    return indexer


def test_la_qualite_est_notee_comptee_et_les_incomplets_se_reindexent(client, en_tant_que, faux, privee, monkeypatch):
    faux.documents = [_doc("a", "# A\n\nTexte fictif a."), _doc("b", "# B\n\nTexte fictif b."), _doc("c", "# C\n\nTexte fictif c.")]
    envoyes: list[str] = []
    monkeypatch.setattr(sources_resana.depot, "_indexer_document_background", _indexeur_qui_note(envoyes, QUALITES))
    en_tant_que(CREATEUR)
    assert _importer(client, privee).status_code == 200
    assert sorted(envoyes) == ["note-a.md", "note-b.md", "note-c.md"]

    qualite = client.get(f"/api/sources/resana/status/{privee}").json()["qualite"]
    assert qualite["par_etat"] == {"complet": 1, "sans_contexte": 1, "sans_texte": 1}
    assert qualite["a_reprendre"] == 2
    assert (qualite["passages"], qualite["passages_sans_contexte"]) == (13, 4)

    # Une mise à jour ordinaire ne renvoie rien : rien n'a changé dans Résana.
    envoyes.clear()
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    assert envoyes == []

    # « Ré-indexer les documents incomplets » : b et c repartent (le quota est revenu, l'OCR est là),
    # a reste en place.
    envoyes.clear()
    retablies = {"note-b.md": {"etat": "complet", "passages": 10, "sans_contexte": 0}, "note-c.md": {"etat": "complet", "passages": 2, "sans_contexte": 0}}
    monkeypatch.setattr(sources_resana.depot, "_indexer_document_background", _indexeur_qui_note(envoyes, retablies))
    r = client.post(f"/api/sources/resana/sync/{privee}", json={"incomplets": True}, headers=ENTETE)
    assert r.status_code == 200 and r.json()["a_reprendre"] == 2
    assert sorted(envoyes) == ["note-b.md", "note-c.md"]
    statut = client.get(f"/api/sources/resana/status/{privee}").json()
    assert statut["qualite"]["par_etat"] == {"complet": 3} and statut["qualite"]["a_reprendre"] == 0
    assert statut["travail"]["action"] == "reindexation"


def test_la_reindexation_est_dite_des_le_depart(client, en_tant_que, faux, privee, monkeypatch):
    """Pendant le travail, l'état dit « reindexation », pas « synchronisation » (bêta, 2026-10-27) :
    l'écran l'affiche, et la reprise après « Se connecter à Résana » ou un redémarrage s'y fie."""
    faux.documents = [_doc("a", "# A\n\nTexte fictif a."), _doc("c", "# C\n\nTexte fictif c.")]
    monkeypatch.setattr(sources_resana.depot, "_indexer_document_background", _indexeur_qui_note([], QUALITES))
    en_tant_que(CREATEUR)
    assert _importer(client, privee).status_code == 200

    async def sans_executer(_collection, travail):
        travail.close()  # le travail reste « en cours », tel que l'écran le lit au départ

    monkeypatch.setattr(sources_resana, "_demarrer", sans_executer)
    assert client.post(f"/api/sources/resana/sync/{privee}", json={"incomplets": True}, headers=ENTETE).json()["a_reprendre"] == 1
    travail = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]
    assert (travail["action"], travail["total"]) == ("reindexation", 2)


def test_une_erreur_notee_avant_la_qualite_compte_quand_meme():
    # Les collections importées avant #144 : l'erreur de lecture gardée dit « sans texte ».
    cfg = {
        "documents": {
            "1": {"file_id": "f1", "erreur": "OpenRAG n'a pas pu lire « s.pdf » : NoIndexableContentError: NO_INDEXABLE_CONTENT"},
            "2": {"file_id": "f2"},
            "3": {"file_id": "f3", "erreur": "OpenRAG a refusé « x.exe » (format ou taille)."},
        }
    }
    assert sources_resana.bilan_qualite(cfg) == {"par_etat": {"sans_texte": 1, "inconnue": 1, "echec": 1}, "a_reprendre": 1}
    assert sources_resana.a_reprendre(cfg) == {"1"}


def test_le_bilan_se_relit_aupres_de_l_indexeur_sans_session_resana(client, en_tant_que, faux, privee, monkeypatch):
    """Après une ré-indexation faite côté indexeur (ou une collection d'avant le suivi), « Relire
    le bilan » pose la qualité que l'indexeur garde, sans rien renvoyer. Un scan noté sans texte
    le reste tant que l'indexeur ne dit pas l'avoir lu par OCR."""
    from unittest.mock import AsyncMock

    from app.routers import ingest
    from app.services.openrag_client import FichierOpenRAG

    faux.documents = [_doc("a", "# A\n\nTexte fictif a."), _doc("b", "# B\n\nTexte fictif b."), _doc("c", "# C\n\nTexte fictif c.")]
    envoyes: list[str] = []
    monkeypatch.setattr(sources_resana.depot, "_indexer_document_background", _indexeur_qui_note(envoyes, {"note-c.md": {"etat": "sans_texte"}}))
    en_tant_que(CREATEUR)
    _importer(client, privee)
    # c est un scan noté comme tel ; a et b n'ont pas de qualité (indexés « avant »).
    cfg = _fiche(privee)
    ids = {f["fichier"]: f["file_id"] for f in cfg["documents"].values()}
    _marquer_scan(privee, ids["note-c.md"])

    listing = [
        FichierOpenRAG(file_id=ids["note-a.md"], degraded_stages=[], contextualization={"total": 3, "failed": 0}),
        FichierOpenRAG(file_id=ids["note-b.md"], degraded_stages=["contextualize"], contextualization={"total": 5, "failed": 2}),
        FichierOpenRAG(file_id=ids["note-c.md"], degraded_stages=[]),  # son vieux passage vide : pas une lecture
    ]
    indexeur = ingest._indexeur()
    indexeur.client.list_files = AsyncMock(return_value=listing)
    monkeypatch.setattr(ingest, "_indexeur", lambda timeout=300.0: indexeur)
    envoyes.clear()
    r = client.post(f"/api/sources/resana/qualite/{privee}")
    assert r.status_code == 200, r.text
    assert envoyes == []  # rien n'est renvoyé
    assert r.json()["qualite"]["par_etat"] == {"complet": 1, "sans_contexte": 1, "sans_texte": 1}


def _fiche(collection: str) -> dict:
    import asyncio

    from app.services.collection_store import get_source_config

    return asyncio.run(get_source_config(collection))


def _marquer_scan(collection: str, file_id: str) -> None:
    import asyncio
    import json

    from app.services.collection_store import get_source_config, update_collection

    async def faire():
        cfg = await get_source_config(collection)
        for d in cfg["documents"].values():
            if d.get("file_id") == file_id:
                d["scan"] = True
        await update_collection(collection, {"source_config_json": json.dumps(cfg)})

    asyncio.run(faire())


def test_appliquer_qualites_garde_un_scan_sans_texte_tant_qu_il_n_est_pas_lu_par_ocr():
    documents = {"1": {"file_id": "f1", "scan": True, "qualite": {"etat": "sans_texte"}}, "2": {"file_id": "f2"}}
    assert sources_resana.appliquer_qualites(documents, {"f1": {"etat": "complet"}, "f2": {"etat": "complet"}}) == 1
    assert documents["1"]["qualite"] == {"etat": "sans_texte"}
    assert sources_resana.appliquer_qualites(documents, {"f1": {"etat": "complet", "ocr": True}}) == 1
    assert documents["1"]["qualite"] == {"etat": "complet", "ocr": True}
