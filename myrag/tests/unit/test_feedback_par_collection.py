"""Les avis comptés pour plusieurs collections d'un coup (catalogue) suivent la même formule
que ceux d'une seule (fiche, page Qualité)."""

import asyncio

from app.services import feedback_store


def _semer(nom: str, avis: list[tuple[int, str]]) -> None:
    async def _f():
        for i, (note, statut) in enumerate(avis):
            fb = await feedback_store.ingest_feedback(nom, f"Question {i} ?", "Réponse.", note)
            if statut != "pending":
                await feedback_store.review_feedback(fb["id"], status=statut)

    asyncio.run(_f())


def test_les_stats_groupees_egalent_celles_d_une_collection(purger):
    noms = ["t-avis-groupes-a", "t-avis-groupes-b", "t-avis-groupes-c"]
    for n in noms:
        purger(n)
    _semer(noms[0], [(1, "pending"), (1, "reviewed"), (-1, "pending")])
    _semer(noms[1], [(-1, "promoted"), (0, "pending")])
    _semer(noms[2], [(1, "reviewed")] * 4)
    try:
        groupees = asyncio.run(feedback_store.stats_par_collection(noms))
        for n in noms:
            assert groupees[n].to_dict() == asyncio.run(feedback_store.feedback_stats(n)), n
        a = groupees[noms[0]]
        assert (a.total, a.positive, a.negative, a.pending_review) == (3, 2, 1, 2)
        assert groupees[noms[1]].promoted == 1 and groupees[noms[1]].satisfaction_rate == 0
        assert groupees[noms[2]].satisfaction_rate == 1
    finally:
        for n in noms:
            purger(n)


def test_une_collection_sans_avis_n_a_pas_de_taux(purger):
    purger("t-avis-aucun")
    stats = asyncio.run(feedback_store.stats_par_collection(["t-avis-aucun"]))["t-avis-aucun"]
    assert stats.total == 0 and stats.satisfaction_rate is None
    assert stats.to_dict()["satisfaction_rate"] is None
    # La route historique, elle, garde son zéro (ses écrans multiplient par 100).
    assert asyncio.run(feedback_store.feedback_stats("t-avis-aucun"))["satisfaction_rate"] == 0


def test_aucun_nom_aucune_requete():
    assert asyncio.run(feedback_store.stats_par_collection([])) == {}
