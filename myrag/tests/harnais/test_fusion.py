"""La fusion RRF : calculée à la main, commutative, avec poids et quota."""

from __future__ import annotations

import pytest

from app.harnais.fusion import K_RRF, fusionner
from tests.harnais.conftest import passage


def _ids(passages):
    return [(p.source, p.document) for p in passages]


def test_un_cas_calcule_a_la_main():
    # Étape 1 (poids 1) : A, B. Étape 2 (poids 0,5) : B, C.
    # A = 1/61 = 0,016393 ; B = 1/62 + 0,5/61 = 0,024326 ; C = 0,5/62 = 0,008065.
    e1 = [passage("s1", "A", 1, etape=1), passage("s1", "B", 1, etape=1, ident="B-1")]
    e2 = [passage("s1", "B", 1, etape=2, ident="B-1"), passage("s2", "C", 1, etape=2)]
    sortie = fusionner({1: e1, 2: e2}, {1: 1.0, 2: 0.5})
    assert [p.document for p in sortie] == ["B", "A", "C"]
    assert [p.score for p in sortie] == [pytest.approx(0.024326, abs=1e-6), pytest.approx(0.016393, abs=1e-6), pytest.approx(0.008065, abs=1e-6)]
    assert [p.rang for p in sortie] == [1, 2, 3]
    assert K_RRF == 60


def test_un_poids_nul_retire_l_etape():
    e1 = [passage("s1", "A", 1, etape=1)]
    e2 = [passage("s2", "Z", 1, etape=2)]
    assert _ids(fusionner({1: e1, 2: e2}, {1: 1.0, 2: 0.0})) == [("s1", "A")]
    assert _ids(fusionner({1: e1, 2: e2}, {1: 1.0})) == [("s1", "A")]  # sans poids : absente


def test_une_seule_source_conserve_l_ordre():
    e1 = [passage("s1", f"d{i}", 1, ident=f"m{i}") for i in range(8)]
    assert _ids(fusionner({1: e1}, {1: 0.4})) == _ids(e1)


def test_commutative_quel_que_soit_l_ordre_des_etapes():
    e1 = [passage("s1", "A", 1, etape=1), passage("s1", "B", 1, etape=1)]
    e2 = [passage("s2", "C", 1, etape=2), passage("s2", "D", 1, etape=2)]  # à égalité de rang avec e1 : départage stable
    e3 = [passage("s1", "B", 1, etape=3), passage("s3", "E", 1, etape=3)]
    poids = {1: 1.0, 2: 1.0, 3: 0.7}
    a = fusionner({1: e1, 2: e2, 3: e3}, poids)
    b = fusionner({3: e3, 1: e1, 2: e2}, poids)
    c = fusionner({2: e2, 3: e3, 1: e1}, poids)
    assert _ids(a) == _ids(b) == _ids(c)
    assert [p.score for p in a] == [p.score for p in b] == [p.score for p in c]


def test_un_meme_morceau_vu_deux_fois_ne_compte_qu_une_fois_par_etape():
    doublon = [passage("s1", "A", 1, ident="m1"), passage("s1", "A", 1, ident="m1")]
    sortie = fusionner({1: doublon}, {1: 1.0})
    assert len(sortie) == 1 and sortie[0].score == pytest.approx(1 / 61, abs=1e-6)


def test_le_quota_garde_une_source_toujours_dans_la_selection():
    forte = [passage("forte", f"f{i}", 1, ident=f"f{i}") for i in range(10)]
    faible = [passage("toujours", f"t{i}", 1, ident=f"t{i}") for i in range(3)]
    # Sans quota, `toujours` est loin derrière : rien dans les 5 premiers.
    sans = fusionner({1: forte, 2: faible}, {1: 1.0, 2: 0.05}, limite=5)
    assert all(p.source == "forte" for p in sans)
    avec = fusionner({1: forte, 2: faible}, {1: 1.0, 2: 0.05}, toujours={"toujours"}, quota=2, limite=5)
    assert len(avec) == 5
    assert [p.document for p in avec if p.source == "toujours"] == ["t0", "t1"]  # ses deux meilleurs
    # Le reste de la sélection est l'ordre de fusion, sans trou.
    assert [p.document for p in avec if p.source == "forte"] == ["f0", "f1", "f2"]


def test_le_quota_ne_depasse_pas_la_limite():
    a = [passage("t1", "a", 1), passage("t1", "b", 1, ident="b1")]
    b = [passage("t2", "c", 1)]
    sortie = fusionner({1: a, 2: b}, {1: 1.0, 2: 1.0}, toujours={"t1", "t2"}, quota=5, limite=2)
    assert len(sortie) == 2
