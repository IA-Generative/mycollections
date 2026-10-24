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
