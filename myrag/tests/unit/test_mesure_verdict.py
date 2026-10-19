"""Verdicts de la mesure de qualité, sans réseau."""

from app.services.mesure import verdict as v


def test_hors_sujet_refus_explicite_seulement_sans_repli_fichiers():
    assert v.verdict_hors_sujet("Je ne dispose pas d'information sur ce sujet.", "aucun")[0] == "refus_ok"
    assert v.verdict_hors_sujet("Les documents ne mentionnent pas l’âge du capitaine.", "recherche")[0] == "refus_ok"
    assert v.verdict_hors_sujet("La collection contient des notes sur les titres de séjour.", "fichiers")[0] == "refus_ko"
    assert v.verdict_hors_sujet("Le capitaine a 42 ans.", "aucun")[0] == "refus_ko"


def test_mots_attendus_plafonnent_a_partiel():
    assert v.plafonner("conforme", "Article L313-1 du CESEDA", ["L313-1", "CESEDA"]) == ("conforme", None)
    verdict, raison = v.plafonner("conforme", "Selon le code…", ["L313-1", "CESEDA", "titre"])
    assert verdict == "partiel" and raison is not None and "L313-1" in raison
    assert v.plafonner("non_conforme", "", ["x"])[0] == "non_conforme"


def test_similarite_de_repli():
    assert v.verdict_similarite("Le délai est de deux mois.", "Le délai est de deux mois.")[0] == "conforme"
    assert v.verdict_similarite("Le délai est de deux mois.", "Il faut une photo d'identité récente.")[0] == "non_conforme"
    assert v.verdict_similarite("Passeport, justificatif de domicile et timbre fiscal.", "Il faut un passeport et un timbre.")[0] == "partiel"
    assert v.verdict_similarite("Deux mois.", "")[0] == "non_conforme"


def test_score_global_et_appreciation():
    assert v.score_global(["conforme", "partiel", "non_conforme", "refus_ok", "erreur"]) == 62.5
    assert v.score_global(["erreur"]) is None
    assert v.appreciation(85) == "très bonne" and v.appreciation(62.5) == "satisfaisante" and v.appreciation(None) == "non mesurée"
