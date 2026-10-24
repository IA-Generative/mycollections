"""La conversion des formats bureautiques en PDF (#146) : un service à part (Gotenberg), appelé
seulement s'il est configuré ; un fichier converti part en PDF, un échec l'écarte avec sa raison, et
un document écarté pour son format est retenté quand le service arrive."""

from __future__ import annotations

import httpx
import pytest

from app.routers import sources_resana
from app.services import conversion
from tests.unit._faux_resana import DocFaux
from tests.unit._pdf_fictif import PDF_TEXTE
from tests.unit.test_resana_routes import CREATEUR, ENTETE, _importer, faux, privee  # noqa: F401 — fixtures

URL = "http://conversion.fake-domain.name:3000"


def test_noms_et_formats():
    assert conversion.nom_pdf("budget.ods") == "budget (ods).pdf"
    assert conversion.nom_pdf("Présentation.odp") == "Présentation (odp).pdf"
    assert conversion.convertible("tableau.XLSX") and conversion.convertible("note.odt")
    assert not conversion.convertible("note.pdf") and not conversion.convertible("outil.exe")


@pytest.mark.asyncio
async def test_le_service_rend_le_pdf_ou_dit_pourquoi(monkeypatch):
    monkeypatch.setattr(conversion.settings, "conversion_url", "")
    with pytest.raises(conversion.ConversionImpossible):
        await conversion.en_pdf("a.odt", b"PK")

    recus: list[httpx.Request] = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        recus.append(requete)
        return httpx.Response(200, content=PDF_TEXTE) if b"bon.odt" in requete.content else httpx.Response(503)

    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(conversion.httpx, "AsyncClient", lambda **kw: vrai_client(transport=httpx.MockTransport(repondre), **kw))
    monkeypatch.setattr(conversion.settings, "conversion_url", URL + "/")
    assert (await conversion.en_pdf("bon.odt", b"PK\x03\x04")).startswith(b"%PDF")
    assert str(recus[0].url) == URL + "/forms/libreoffice/convert"
    with pytest.raises(conversion.ConversionImpossible, match="503"):
        await conversion.en_pdf("mauvais.odt", b"PK\x03\x04")


def _resana_avec_tableur(faux):
    faux.documents[:] = [
        DocFaux(id="t", titre="Tableau fictif", nom_fichier="suivi.ods", contenu=b"PK\x03\x04 tableur fictif", mime="application/vnd.oasis.opendocument.spreadsheet"),
        DocFaux(id="x", titre="Outil fictif", nom_fichier="outil.exe", contenu=b"MZ\x90\x00", mime="application/octet-stream"),
    ]


def test_sans_service_le_tableur_est_ecarte_avec_son_extension_puis_retente(client, en_tant_que, faux, privee, monkeypatch):
    _resana_avec_tableur(faux)
    monkeypatch.setattr(conversion.settings, "conversion_url", "")
    en_tant_que(CREATEUR)
    assert _importer(client, privee).status_code == 200
    assert faux.envois.await_count == 0
    ecartes = client.get(f"/api/sources/resana/status/{privee}").json()["travail"]["documents_ecartes"]
    assert {e["titre"] for e in ecartes} == {"Tableau fictif", "Outil fictif"}

    # Le service arrive : le tableur, écarté pour son format, est retenté et part en PDF ; l'exécutable non.
    monkeypatch.setattr(conversion.settings, "conversion_url", URL)

    async def en_pdf(nom, contenu):
        return PDF_TEXTE

    monkeypatch.setattr(conversion, "en_pdf", en_pdf)
    client.post(f"/api/sources/resana/sync/{privee}", headers=ENTETE)
    (appel,) = faux.envois.await_args_list
    assert appel.args[1] == "suivi (ods).pdf" and appel.args[2].startswith(b"%PDF")
    assert appel.kwargs["metadata"]["converti_depuis"] == ".ods"


def test_une_conversion_impossible_ecarte_le_document_avec_la_raison(client, en_tant_que, faux, privee, monkeypatch):
    _resana_avec_tableur(faux)
    monkeypatch.setattr(conversion.settings, "conversion_url", URL)

    async def en_pdf(nom, contenu):
        raise conversion.ConversionImpossible("le service a répondu 503")

    monkeypatch.setattr(conversion, "en_pdf", en_pdf)
    en_tant_que(CREATEUR)
    _importer(client, privee)
    raisons = {e["titre"]: e["raison"] for e in client.get(f"/api/sources/resana/status/{privee}").json()["travail"]["documents_ecartes"]}
    assert raisons["Tableau fictif"] == "conversion en PDF impossible (le service a répondu 503)"
    assert sources_resana._convertible_desormais({"raison": "format non pris en charge", "extension": ".exe"}) is False


def test_un_depot_bureautique_part_converti(client, en_tant_que, creer_collection, nom, monkeypatch):
    import time
    from unittest.mock import AsyncMock, patch

    from app.services.openrag_client import EnvoiDocument, EtatTache, ResultatPartition
    from tests.conftest import personne

    async def en_pdf(nom_fichier, contenu):
        return PDF_TEXTE

    monkeypatch.setattr(conversion.settings, "conversion_url", URL)
    monkeypatch.setattr(conversion, "en_pdf", en_pdf)
    creer_collection(nom)
    en_tant_que(personne("createur"))
    openrag = AsyncMock()
    openrag.create_partition = AsyncMock(return_value=ResultatPartition(status="ok"))
    openrag.upload_document = AsyncMock(return_value=EnvoiDocument(file_id="f1", task_id="t1"))
    openrag.task_state = AsyncMock(return_value=EtatTache(task_state="COMPLETED"))
    with patch("app.routers.ingest.OpenRAGClient", return_value=openrag):
        r = client.post(f"/api/ingest/{nom}", files={"file": ("note.odt", b"PK\x03\x04 texte fictif", "application/vnd.oasis.opendocument.text")})
        assert r.status_code == 200, r.text
        for _ in range(100):
            if client.get(f"/api/ingest/jobs/{r.json()['job_id']}").json()["status"].startswith("done"):
                break
            time.sleep(0.02)
    _, fichier, contenu, mime = openrag.upload_document.await_args.args
    assert (fichier, mime) == ("note (odt).pdf", "application/pdf") and contenu == PDF_TEXTE
