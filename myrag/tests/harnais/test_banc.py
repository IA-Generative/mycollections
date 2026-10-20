"""Le banc des assistants : `regles` face à `toutes_les_sources`, sans réseau ni base."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import banc

pytestmark = pytest.mark.banc

FIXTURES = Path(__file__).parent / "fixtures" / "banc"
SEUILS = banc.charger_seuils(FIXTURES / "seuils.json")


@pytest.fixture(scope="module")
def sejour() -> banc.Jeu:
    return banc.charger_jeu(FIXTURES / "sejour-des-etrangers.json")


@pytest.fixture(scope="module")
def une_source() -> banc.Jeu:
    return banc.charger_jeu(FIXTURES / "une-source.json")


@pytest.mark.asyncio
async def test_sur_une_source_regles_donne_le_meme_resultat_que_toutes_les_sources(une_source):
    toutes = await banc.jouer_jeu(une_source, "toutes_les_sources")
    regles = await banc.jouer_jeu(une_source, "regles")
    assert len(regles.resultats) == 3
    # Même verdict, même rang du témoin, mêmes passages dans le même ordre, mêmes sources contactées.
    pour_comparer = lambda r: [(x.id, x.verdict, x.rang_temoin, x.sources_contactees, x.passages) for x in r.resultats]  # noqa: E731
    assert pour_comparer(regles) == pour_comparer(toutes)
    assert regles.score == toutes.score


@pytest.mark.asyncio
async def test_a_plusieurs_sources_regles_contacte_la_moitie_au_plus_sans_perdre_de_score(sejour):
    toutes = await banc.jouer_jeu(sejour, "toutes_les_sources")
    regles = await banc.jouer_jeu(sejour, "regles")
    assert toutes.sources_contactees_pct == 100.0  # la ligne de base cherche partout
    assert regles.sources_contactees_pct <= 50
    assert regles.score - toutes.score >= -1
    assert banc.verifier(regles, SEUILS, toutes) == []


@pytest.mark.asyncio
async def test_le_rappel_de_regles_tient_les_seuils_et_bat_la_ligne_de_base_au_rang_1(sejour):
    toutes = await banc.jouer_jeu(sejour, "toutes_les_sources")
    regles = await banc.jouer_jeu(sejour, "regles")
    assert regles.rappel(1) >= SEUILS["rappel@1"]["min"] and regles.rappel(5) >= SEUILS["rappel@5"]["min"]
    assert regles.rappel(1) > toutes.rappel(1)  # chercher partout noie le témoin parmi les premiers de chaque source


@pytest.mark.parametrize("nom", banc.PLANIFICATEURS)
@pytest.mark.asyncio
async def test_zero_incident_de_droits(sejour, nom):
    rapport = await banc.jouer_jeu(sejour, nom)
    assert rapport.incidents_droits == 0
    assert any(r.identite == "dehors" for r in rapport.resultats)  # les questions de droits ont bien été posées


@pytest.mark.parametrize("nom", banc.PLANIFICATEURS)
@pytest.mark.asyncio
async def test_temoin_negatif_droits_neutralises_le_banc_compte_des_incidents(sejour, nom):
    rapport = await banc.jouer_jeu(sejour, nom, droits=False)
    assert rapport.incidents_droits > 0
    assert banc.verifier(rapport, SEUILS) != []  # et le seuil `incidents_droits` le dit


@pytest.mark.asyncio
async def test_un_seuil_non_tenu_est_signale(sejour):
    toutes = await banc.jouer_jeu(sejour, "toutes_les_sources")
    manques = banc.verifier(toutes, SEUILS, toutes)
    assert any(m.startswith("rappel@1") for m in manques) and any(m.startswith("sources_contactees_pct") for m in manques)


@pytest.mark.asyncio
async def test_le_juge_doublure_distingue_conforme_partiel_et_non_conforme(sejour):
    juge = banc.juge_doublure(sejour.temoins)
    q = next(x for x in sejour.questions if x.source == "asile")
    rapport = await banc.jouer_jeu(sejour, "regles")
    assert all(r.verdict == "conforme" for r in rapport.notees)

    def passage(source: str, document: str):
        from app.harnais.contrat import Passage

        return Passage(source=source, etape=1, rang=1, document=document, texte="x")

    assert juge(q, [passage("asile", sejour.temoins["asile"])]) == "conforme"
    assert juge(q, [passage("eloignement", sejour.temoins["eloignement"])]) == "partiel"
    assert juge(q, [passage("asile", "as-cnda")]) == "non_conforme"


def test_le_juge_reel_n_est_pas_branche():
    with pytest.raises(NotImplementedError):
        banc.juge_reel()


def test_la_ligne_de_commande_rend_un_rapport_json(capsys, sejour):
    import json

    code = banc.main([str(FIXTURES / "sejour-des-etrangers.json"), "--juge", "doublure", "--planificateur", "regles", "--rapport", "json"])
    sortie = json.loads(capsys.readouterr().out)
    assert code == 0 and sortie["planificateur"] == "regles" and sortie["seuils_manques"] == []
    assert sortie["mesures"]["incidents_droits"] == 0 and "ecart_score_vs_toutes" in sortie["mesures"]
