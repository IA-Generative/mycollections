"""Les réglages se lisent sous le nom de l'application, MYCOLLECTIONS_*, et sous l'ancien MYRAG_*."""

from app.config import Settings


def test_le_nouveau_nom_est_lu(monkeypatch):
    monkeypatch.delenv("MYRAG_SUPERADMIN_GROUPES", raising=False)
    monkeypatch.setenv("MYCOLLECTIONS_SUPERADMIN_GROUPES", "/g/mirai-beta-testeurs-admin")
    assert Settings().myrag_superadmin_groupes == "/g/mirai-beta-testeurs-admin"


def test_l_ancien_nom_reste_lu(monkeypatch):
    monkeypatch.delenv("MYCOLLECTIONS_GROUPE_EXIGE", raising=False)
    monkeypatch.setenv("MYRAG_GROUPE_EXIGE", "/g/mirai-beta-testeurs")
    assert Settings().myrag_groupe_exige == "/g/mirai-beta-testeurs"


def test_le_nouveau_nom_l_emporte(monkeypatch):
    monkeypatch.setenv("MYRAG_PSEUDO_SEL", "ancien")
    monkeypatch.setenv("MYCOLLECTIONS_PSEUDO_SEL", "nouveau")
    assert Settings().myrag_pseudo_sel == "nouveau"
