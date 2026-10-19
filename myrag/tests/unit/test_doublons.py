from app.models.collectif import DemandeFiche
from app.services.doublons import candidats, similarite


def _fiche(**surcharge) -> DemandeFiche:
    fiche = DemandeFiche(
        id="d",
        titre="",
        usage="ponctuel",
        frequence="jamais",
        service="",
        acces_actuel="",
        etat="depot",
        seuil=5,
        amorce_id=None,
        collection_name=None,
        doublon_de=None,
        motif_cloture=None,
        satisfaction=None,
        motif_insatisfaction=None,
        confirmation_demandee_le=None,
        cree_le="",
        maj_le="",
        nb_soutiens=0,
        garant=False,
        roles={},
        temps_declare_min=0,
        soutenue_par_moi=False,
        mon_role=None,
        abonne=False,
        sommeil=False,
        seuil_atteint=False,
        je_suis_demandeur=False,
        confirmation_avant=None,
    )
    return fiche.model_copy(update=surcharge) if surcharge else fiche


def test_les_titres_proches_se_reconnaissent():
    assert similarite("Fichier des élus", "Répertoire national des élus") >= 0.45
    assert similarite("Fichier des élus", "Codes NATINF") < 0.45


def test_candidats_tries_par_proximite():
    demandes = [_fiche(id="1", titre="Codes NATINF"), _fiche(id="2", titre="Répertoire national des élus"), _fiche(id="3", titre="Élus municipaux")]
    ids = [d.id for d in candidats("Répertoire des élus municipaux", demandes)]
    assert ids and "1" not in ids and ids[0] in ("2", "3")
    assert all(hasattr(d, "similarite") for d in candidats("élus", demandes))
