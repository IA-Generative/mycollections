"""Le client du service d'export Résana, contre un faux service (aucun appel réseau)."""

from __future__ import annotations

import httpx
import pytest

from app.services.connectors import resana
from app.services.connectors.resana import ClientExportResana, DocumentResana, ErreurResana, nom_depuis_disposition, nom_unique, noms_uniques
from tests.unit._faux_resana import BASE, SECRET, TEMOIN, DocFaux, FauxResana

pytestmark = pytest.mark.asyncio


def _client(faux: FauxResana, *, secret: str = SECRET) -> ClientExportResana:
    return ClientExportResana(BASE, secret, TEMOIN, transport=faux.transport())


def _docs(n: int) -> list[DocFaux]:
    return [DocFaux(id=f"i{k}", titre=f"Note fictive {k}", nom_fichier=f"note-{k}.md", contenu=f"# Note {k}\n\nTexte fictif {k}.".encode()) for k in range(n)]


async def test_les_deux_entetes_partent_et_aucune_adresse():
    faux = FauxResana()
    espaces = await _client(faux).espaces()
    assert [e.nom for e in espaces] == ["Zêta fictif", "Alpha fictif"]
    req = faux.requetes[0]
    assert req.url.path == "/export/v1/espaces"
    assert req.headers["x-internal-token"] == SECRET
    assert req.headers["authorization"] == f"Bearer {TEMOIN}"
    assert "@" not in str(req.url) and not req.url.params


def test_non_configure_ou_sans_jeton():
    with pytest.raises(ErreurResana) as e:
        ClientExportResana("", SECRET, TEMOIN)
    assert e.value.statut == 503
    with pytest.raises(ErreurResana) as e:
        ClientExportResana(BASE, SECRET, "")
    assert e.value.code == "jeton_invalide"


async def test_un_mauvais_secret_est_un_appelant_inconnu():
    with pytest.raises(ErreurResana) as e:
        await _client(FauxResana(), secret="autre").espaces()
    assert (e.value.statut, e.value.code) == (401, "appelant_inconnu")


async def test_les_pages_se_suivent_jusqu_au_bout():
    faux = FauxResana(documents=_docs(5), page=2)
    docs = await _client(faux).documents("e-1", "d-1")
    assert [d.id for d in docs] == ["i0", "i1", "i2", "i3", "i4"]
    assert all(r.url.params["recursif"] == "true" and r.url.params["dossier"] == "d-1" for r in faux.requetes)
    assert docs[0].url_consultation.startswith("https://") and docs[0].version_fichier and docs[0].taille_approx_mo is not None


async def test_un_curseur_perime_relance_une_fois_depuis_le_debut():
    faux = FauxResana(documents=_docs(5), page=2, curseurs_perimes=1)
    assert len(await _client(faux).documents("e-1", "d-1")) == 5
    faux = FauxResana(documents=_docs(5), page=2, curseurs_perimes=2)
    with pytest.raises(ErreurResana) as e:
        await _client(faux).documents("e-1", "d-1")
    assert e.value.code == "curseur_perime"


async def test_trop_de_documents(monkeypatch):
    monkeypatch.setattr(resana, "DOCUMENTS_MAX", 3)
    with pytest.raises(ErreurResana) as e:
        await _client(FauxResana(documents=_docs(5), page=10)).documents("e-1", "d-1")
    assert (e.value.statut, e.value.code) == (413, "trop_de_documents")


async def test_session_absente_porte_son_lien_seulement_en_https():
    faux = FauxResana(
        pannes={"/espaces": (409, {"code": "session_absente", "message": "x", "reessayable": False, "url_connexion": "https://monassistant.fake-domain.name/resana/connexion"})}
    )
    with pytest.raises(ErreurResana) as e:
        await _client(faux).espaces()
    assert e.value.detail()["url_connexion"].startswith("https://")
    assert "Connectez-vous" in e.value.detail()["message"]
    faux = FauxResana(pannes={"/espaces": (409, {"code": "session_absente", "url_connexion": "javascript:alert(1)"})})
    with pytest.raises(ErreurResana) as e:
        await _client(faux).espaces()
    assert "url_connexion" not in e.value.detail()


async def test_une_panne_sans_corps_lisible_est_reessayable():
    with pytest.raises(ErreurResana) as e:
        await _client(FauxResana(pannes={"/espaces": (502, b"<html>bad gateway</html>")})).espaces()
    assert e.value.code == "resana_indisponible" and e.value.reessayable


async def test_le_fichier_arrive_avec_son_nom_et_son_condensat():
    import hashlib

    doc = DocFaux(id="i1", titre="Compte rendu fictif", nom_fichier="compte rendu é.md", contenu=b"# CR\n\nFictif.")
    f = await _client(FauxResana(documents=[doc])).fichier("i1", "e-1")
    assert f.nom == "compte rendu é.md"
    assert f.sha256 == hashlib.sha256(doc.contenu).hexdigest()


async def test_un_fichier_trop_gros_est_coupe(monkeypatch):
    monkeypatch.setattr(resana, "OCTETS_MAX_FICHIER", 10)
    doc = DocFaux(id="i1", titre="Gros", nom_fichier="gros.md", contenu=b"x" * 100)
    with pytest.raises(ErreurResana) as e:
        await _client(FauxResana(documents=[doc])).fichier("i1", "e-1")
    assert (e.value.statut, e.value.code) == (413, "trop_volumineux")


async def test_un_flux_tronque_est_jete():
    def tronque(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"abc", headers={"content-length": "10"})

    client = ClientExportResana(BASE, SECRET, TEMOIN, transport=httpx.MockTransport(tronque))
    with pytest.raises(ErreurResana) as e:
        await client.fichier("i1", "e-1")
    assert e.value.code == "resana_indisponible"


def test_noms():
    assert nom_depuis_disposition("attachment; filename*=UTF-8''note%20%C3%A9t%C3%A9.pdf", "repli") == "note été.pdf"
    assert nom_depuis_disposition('attachment; filename="../../etc/passwd"', "repli") == ".._.._etc_passwd"
    assert nom_depuis_disposition(None, "repli.md") == "repli.md"
    pris: set[str] = set()
    assert nom_unique("Note.md", "a1", pris) == "Note.md"
    assert nom_unique("note.MD", "a/2", pris) == "note (a2).MD"
    d = [DocumentResana(id=i, titre="T", nom_fichier="t.md", mime="", dossier_id=None, chemin="", url_consultation="") for i in ("x", "y")]
    assert noms_uniques(d) == {"x": "t.md", "y": "t (y).md"}
