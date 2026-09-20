"""Consulter le corpus : la liste paginée des documents d'une collection, et le texte de l'un d'eux.

Les formes d'OpenRAG reprises ici sont celles MESURÉES sur la bêta : `/partition/<p>` rend
`{"files": [...]}`, `/partition/<p>/file/<id>` rend des métadonnées (vecteur compris) et des
liens `/extract/<id>`, et un morceau relu porte ses balises techniques.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services import corpus
from tests.conftest import SUPERADMIN, personne

FICHIERS = [
    {"file_id": "LEGIARTI1-p10", "title": "CESEDA, art. Annexe 10 (partie 10/12)", "mimetype": "text/markdown",
     "url": "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI1", "partition": "p"},
    {"file_id": "LEGIARTI1-p2", "title": "CESEDA, art. Annexe 10 (partie 2/12)", "mimetype": "text/markdown", "partition": "p"},
    {"file_id": "uuid-1", "filename": "1_dire_ce_qui_manque_001.md", "original_filename": "1-dire-ce-qui-manque--001.md",
     "file_size": "308.00 B", "source": "/app/data/1789_secret.md", "content_sha256": "c3f2", "partition": "p"},
    {"file_id": "uuid-2", "original_filename": "Séjour des étudiants.pdf", "mimetype": "application/pdf",
     "url": "javascript:alert(1)", "partition": "p"},
    {"title": "sans identifiant"},
    "pas un dictionnaire",
]


@pytest.fixture(autouse=True)
def _cache_vide():
    corpus.oublier()
    yield
    corpus.oublier()


# ─── La logique pure ────────────────────────────────────────────────────────────

def test_un_fichier_ne_montre_rien_d_interne():
    d = corpus.resumer_fichier(FICHIERS[2])
    assert d == {"file_id": "uuid-1", "titre": "1-dire-ce-qui-manque--001.md", "fichier": "1-dire-ce-qui-manque--001.md",
                 "type": "", "taille": "308.00 B", "url_source": ""}
    assert "source" not in d and "content_sha256" not in d


def test_une_adresse_qui_n_est_pas_du_web_est_ecartee():
    assert corpus.resumer_fichier(FICHIERS[3])["url_source"] == ""
    assert corpus.resumer_fichier(FICHIERS[0])["url_source"].startswith("https://www.legifrance")


def test_la_liste_ecarte_ce_qui_n_a_pas_d_identifiant_et_trie_en_nombres():
    r = corpus.chercher_et_paginer(FICHIERS)
    assert r["total"] == 4 and r["pages"] == 1
    titres = [d["titre"] for d in r["documents"]]
    assert titres.index("CESEDA, art. Annexe 10 (partie 2/12)") < titres.index("CESEDA, art. Annexe 10 (partie 10/12)")


def test_la_recherche_ignore_accents_et_casse_et_exige_tous_les_mots():
    assert [d["file_id"] for d in corpus.chercher_et_paginer(FICHIERS, q="SEJOUR etudiants")["documents"]] == ["uuid-2"]
    assert corpus.chercher_et_paginer(FICHIERS, q="annexe")["total"] == 2
    assert corpus.chercher_et_paginer(FICHIERS, q="annexe introuvable")["total"] == 0
    assert corpus.chercher_et_paginer(FICHIERS, q="legiarti1-p2")["total"] == 1  # l'identifiant se cherche aussi


def test_la_pagination_borne_la_page_et_la_taille():
    beaucoup = [{"file_id": f"f{i}", "title": f"Doc {i}"} for i in range(1, 121)]
    p1 = corpus.chercher_et_paginer(beaucoup, par_page=50)
    assert (p1["total"], p1["pages"], len(p1["documents"])) == (120, 3, 50)
    assert p1["documents"][1]["titre"] == "Doc 2"  # tri naturel : 2 avant 10
    p3 = corpus.chercher_et_paginer(beaucoup, page=3, par_page=50)
    assert len(p3["documents"]) == 20
    assert corpus.chercher_et_paginer(beaucoup, page=99, par_page=50)["page"] == 3       # au-delà : la dernière
    assert corpus.chercher_et_paginer(beaucoup, par_page=10_000)["par_page"] == corpus.PAR_PAGE_MAX
    assert corpus.chercher_et_paginer([], page=5) == {"total": 0, "page": 1, "pages": 1, "par_page": 50, "documents": []}


def test_les_morceaux_se_lisent_dans_les_liens_dans_l_ordre_sans_doublon():
    detail = {"documents": [{"link": "https://x/extract/30"}, {"link": "https://x/extract/10?a=1"},
                            {"link": "https://x/extract/30"}, {"link": "ailleurs"}, "n'importe quoi"]}
    assert corpus.identifiants_des_morceaux(detail) == ["30", "10"]
    assert corpus.identifiants_des_morceaux({}) == [] and corpus.identifiants_des_morceaux(None) == []


# ─── Les routes ─────────────────────────────────────────────────────────────────

RELU = "[CONTEXT]\n\nRésumé du document.\n\n* filename: x.md\n\n[CHUNK_START]\n\nLe texte du morceau {n}.\n\n[CHUNK_END]"


def _openrag(fichiers=FICHIERS, detail=None, morceaux=None):
    """Un OpenRAG de remplacement, posé à l'endroit où la route le construit."""
    p = patch("app.routers.corpus.OpenRAGClient")
    cls = p.start()
    c = cls.return_value
    c.list_files = AsyncMock(return_value=fichiers)
    c.file_detail = AsyncMock(return_value=detail)
    c.extract = AsyncMock(side_effect=lambda cid: (morceaux or {}).get(cid))
    return p, c


def test_la_liste_est_servie_a_qui_peut_lire_la_collection(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    p, c = _openrag()
    try:
        r = client.get(f"/api/collections/{nom}/documents", params={"q": "annexe", "par_page": 1})
        assert r.status_code == 200, r.text
        assert (r.json()["total"], r.json()["pages"], len(r.json()["documents"])) == (2, 2, 1)
        client.get(f"/api/collections/{nom}/documents", params={"page": 2, "par_page": 1})
        assert c.list_files.await_count == 1  # feuilleter ne redemande pas 4,6 Mo à OpenRAG
    finally:
        p.stop()


def test_qui_ne_peut_pas_lire_la_collection_ne_voit_ni_la_liste_ni_un_document(client, en_tant_que, creer_collection, nom):
    creer_collection(nom, scope="group", scope_groups=["/g/un-autre-groupe"])
    from app.auth import CurrentUser
    en_tant_que(CurrentUser(sub="etranger", username="e", groups=["/g/rien-a-voir"]))
    p, c = _openrag(detail={"metadata": {"partition": nom}, "documents": []})
    try:
        assert client.get(f"/api/collections/{nom}/documents").status_code == 404
        assert client.get(f"/api/collections/{nom}/documents/uuid-1").status_code == 404
        c.list_files.assert_not_awaited()
        c.file_detail.assert_not_awaited()  # OpenRAG n'est même pas interrogé
    finally:
        p.stop()


def test_une_collection_inconnue_rend_404(client, en_tant_que):
    en_tant_que(SUPERADMIN)
    p, _ = _openrag()
    try:
        assert client.get("/api/collections/cette-collection-n-existe-pas/documents").status_code == 404
    finally:
        p.stop()


def test_un_document_rend_son_texte_sans_balises_ni_vecteur(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    detail = {"metadata": {"partition": nom, "file_id": "uuid-1", "original_filename": "guide.md", "vector": [0.1, 0.2],
                           "source": "/app/data/interne.md"},
              "documents": [{"link": "https://o/extract/1"}, {"link": "https://o/extract/2"}, {"link": "https://o/extract/3"}]}
    morceaux = {"1": {"page_content": RELU.format(n=1), "metadata": {"page": 1}}, "2": {"page_content": RELU.format(n=2)}, "3": None}
    p, _ = _openrag(detail=detail, morceaux=morceaux)
    try:
        r = client.get(f"/api/collections/{nom}/documents/uuid-1")
        assert r.status_code == 200, r.text
        d = r.json()
        assert [m["texte"] for m in d["morceaux"]] == ["Le texte du morceau 1.", "Le texte du morceau 2."]
        assert d["morceaux"][0]["page"] == 1 and d["morceaux"][1]["page"] is None
        assert d["contexte"] == "Résumé du document." and d["titre"] == "guide.md"
        assert (d["total_morceaux"], d["illisibles"], d["tronque"]) == (3, 1, False)
        brut = r.text
        for interdit in ("[CHUNK_START]", "[CONTEXT]", "vector", "/app/data", "filename:"):
            assert interdit not in brut
    finally:
        p.stop()


def test_un_document_d_une_autre_partition_n_est_pas_servi(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    p, c = _openrag(detail={"metadata": {"partition": "collection-du-voisin"}, "documents": [{"link": "https://o/extract/1"}]})
    try:
        assert client.get(f"/api/collections/{nom}/documents/uuid-1").status_code == 404
        c.extract.assert_not_awaited()
    finally:
        p.stop()


def test_un_document_inconnu_ou_un_identifiant_douteux(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    p, c = _openrag(detail=None)
    try:
        assert client.get(f"/api/collections/{nom}/documents/inconnu").status_code == 404
        assert client.get(f"/api/collections/{nom}/documents/a/../../secret").status_code in (400, 404)
        assert all(".." not in str(a) for a in c.file_detail.await_args_list)
    finally:
        p.stop()


def test_un_long_document_est_tronque_et_le_dit(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    n = corpus.MORCEAUX_MAX + 5
    detail = {"metadata": {"partition": nom}, "documents": [{"link": f"https://o/extract/{i}"} for i in range(n)]}
    p, c = _openrag(detail=detail, morceaux={str(i): {"page_content": f"texte {i}"} for i in range(n)})
    try:
        d = client.get(f"/api/collections/{nom}/documents/gros").json()
        assert (len(d["morceaux"]), d["total_morceaux"], d["tronque"]) == (corpus.MORCEAUX_MAX, n, True)
        assert c.extract.await_count == corpus.MORCEAUX_MAX
    finally:
        p.stop()


def test_openrag_en_panne_donne_un_502_lisible(client, en_tant_que, creer_collection, nom):
    creer_collection(nom)
    en_tant_que(personne("lecteur"))
    p, c = _openrag()
    c.list_files = AsyncMock(side_effect=RuntimeError("connexion refusée"))
    try:
        r = client.get(f"/api/collections/{nom}/documents")
        assert r.status_code == 502 and "OpenRAG" in r.json()["detail"] and "connexion refusée" not in r.text
    finally:
        p.stop()
