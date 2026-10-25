"""Les tableurs lus par l'indexeur lui-même (lecteur `spreadsheet`, IA-Generative/openrag#15) : une
fois `indexeur_lit_tableurs` allumé, ils partent tels quels au lieu d'être convertis en PDF (où
LibreOffice coupe le texte des cellules à la largeur de la colonne, mesuré le 2026-10-25)."""

from __future__ import annotations

import pytest

from app.routers import sources_resana
from app.services import conversion, formats
from tests.unit._faux_resana import DocFaux
from tests.unit.test_resana_routes import CREATEUR, ENTETE, _importer, faux, privee  # noqa: F401 — fixtures

XLSX = b"PK\x03\x04 classeur fictif"
XLS = b"\xd0\xcf\x11\xe0 classeur fictif"


@pytest.fixture
def lit_tableurs(monkeypatch):
    monkeypatch.setattr(formats.settings, "indexeur_lit_tableurs", True)


def test_eteint_les_tableurs_restent_a_convertir():
    assert formats.nature("budget.xlsx", XLSX) is None
    assert conversion.convertible("budget.xlsx") and conversion.convertible("note.odt")


def test_allume_les_tableurs_sont_des_documents(lit_tableurs):
    for nom, contenu in (("budget.xlsx", XLSX), ("macro.XLSM", XLSX), ("ancien.xls", XLS), ("suivi.ods", XLSX)):
        assert formats.nature(nom, contenu) is formats.Nature.DOCUMENT, nom
    assert formats.type_mime("budget.xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert formats.nature("budget.xlsx", b"<html>pas un classeur") is None  # l'extension ment
    assert not conversion.convertible("budget.xlsx") and not conversion.convertible("suivi.ods")
    assert conversion.convertible("note.odt") and conversion.convertible("vieux.ppt")  # le reste passe par Gotenberg


def test_un_tableur_resana_part_tel_quel(client, en_tant_que, faux, privee, monkeypatch, lit_tableurs):
    monkeypatch.setattr(conversion.settings, "conversion_url", "http://conversion.fake-domain.name:3000")

    async def interdit(nom, contenu):
        raise AssertionError("un tableur ne doit plus passer par la conversion")

    monkeypatch.setattr(conversion, "en_pdf", interdit)
    faux.documents[:] = [DocFaux(id="t", titre="Tableau fictif", nom_fichier="suivi.xlsx", contenu=XLSX, mime="application/octet-stream")]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    (appel,) = faux.envois.await_args_list
    assert appel.args[1] == "suivi.xlsx" and appel.args[2] == XLSX
    assert appel.args[3] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_un_tableur_ecarte_avant_est_retente_meme_sans_conversion(client, en_tant_que, faux, privee, monkeypatch):
    monkeypatch.setattr(conversion.settings, "conversion_url", "")
    faux.documents[:] = [DocFaux(id="t", titre="Tableau fictif", nom_fichier="suivi.xlsx", contenu=XLSX, mime="application/octet-stream")]
    en_tant_que(CREATEUR)
    _importer(client, privee)
    assert faux.envois.await_count == 0  # écarté : ni lu ni convertible
    monkeypatch.setattr(formats.settings, "indexeur_lit_tableurs", True)
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    (appel,) = faux.envois.await_args_list
    assert appel.args[1] == "suivi.xlsx"
    assert sources_resana._lisible_desormais({"raison": "format non pris en charge", "extension": ".zip"}) is False
