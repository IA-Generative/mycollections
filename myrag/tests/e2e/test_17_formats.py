"""Parcours 17 — chaque format de fichier, de Drive jusqu'au texte de l'index.

Un fichier par format (`fixtures/formats/`, régénérables par `_generer.py`), chacun portant son
propre code témoin `FMT-<EXT>-<n>`, est déposé dans le Drive du testeur puis importé dans une
collection. Pour chaque format, le test dit ce que Mes collections en a fait, et le vérifie :

- **indexé** : le document est dans l'index ET son texte, tel que l'indexeur l'a lu, contient le
  témoin (la lecture a réussi, pas seulement l'envoi) ;
- **écarté** : le document est écarté avec la bonne raison, et n'est pas dans l'index.

Les formats bureautiques que l'indexeur ne lit pas lui-même (LibreOffice, anciens Office, tableurs)
passent par le service de conversion en PDF : ce parcours le prouve aussi. Le dossier Drive et la
collection sont effacés à la fin.
"""

from __future__ import annotations

import datetime as _dt
import pathlib

import pytest

from tests.e2e.conftest import _menage, attendre
from tests.e2e.test_16_sources_fichiers import Drive, _statut, _travail_fini

FORMATS = pathlib.Path(__file__).parent / "fixtures" / "formats"


def _octets(fichier: str) -> bytes:
    """Le fichier d'essai ; un gros fichier est rangé compressé (`.gz`, la limite de taille du dépôt)."""
    chemin = FORMATS / fichier
    if chemin.exists():
        return chemin.read_bytes()
    import gzip

    return gzip.decompress((FORMATS / f"{fichier}.gz").read_bytes())


def _plie(texte: str) -> str:
    """Le texte sans espaces ni ponctuation : une diapositive convertie coupe « FMT-PPT-1302 » en
    « FMT » / « PPT-1302 » ; c'est le texte qui compte, pas sa mise en page."""
    return "".join(c for c in texte.upper() if c.isalnum())


#: Rempli au dépôt : les fichiers que Drive refuse (son instance a une liste d'extensions permises).
REFUSES_PAR_DRIVE: dict[str, str] = {}

#: fichier → (ce qu'on attend, témoin). « indexe » : dans l'index avec son texte lu.
ATTENDU = {
    "format.txt": ("indexe", "FMT-TXT-1101"),
    "format.md": ("indexe", "FMT-MD-1102"),
    "format.csv": ("indexe", "FMT-CSV-1103"),
    "format.html": ("indexe", "FMT-HTML-1104"),
    "format.json": ("indexe", "FMT-JSON-1105"),
    "format.docx": ("indexe", "FMT-DOCX-1201"),
    "format.doc": ("indexe", "FMT-DOC-1202"),
    "format.odt": ("indexe", "FMT-ODT-1203"),
    "format.rtf": ("indexe", "FMT-RTF-1204"),
    "format.pdf": ("indexe", "FMT-PDF-1205"),
    "format.pptx": ("indexe", "FMT-PPTX-1301"),
    "format.ppt": ("indexe", "FMT-PPT-1302"),
    "format.odp": ("indexe", "FMT-ODP-1303"),
    "format.xlsx": ("indexe", "FMT-XLSX-1401"),
    "format.xls": ("indexe", "FMT-XLS-1402"),
    "format.ods": ("indexe", "FMT-ODS-1403"),
    "format.eml": ("indexe", "FMT-EML-1501"),
    "format.png": ("indexe", "FMT-PNG-1601"),
    "format.jpg": ("indexe", "FMT-JPG-1602"),
    "format-scan.pdf": ("indexe", "FMT-PDF-SCAN-1603"),
    "format.gif": ("format", None),
    "format.zip": ("format", None),
}


@pytest.fixture(scope="module")
def instance(session_testeur) -> dict:
    r = session_testeur.get("/api/sources/fichiers/instances")
    if r.status == 404 or not (r.json() or {}).get("instances"):
        pytest.skip("pas de source Fichiers sur la cible")
    return r.json()["instances"][0]


@pytest.fixture(scope="module")
def import_formats(session_testeur, instance):
    """Le dossier des formats dans Drive, importé ; rend (collection, ids Drive par fichier, statut)."""
    drive = Drive(session_testeur, instance["hote"])
    titre = "e2e-formats-" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    racine = drive.dossier(titre)
    nom = None
    try:
        ids, refuses = {}, {}
        for f in ATTENDU:
            try:
                ids[f] = drive.deposer(racine, f, _octets(f))
            except AssertionError as e:
                # Drive refuse lui-même certaines extensions : elles n'arrivent jamais à Mes collections.
                code = next((c for c in ("item_create_file_extension_not_allowed", "file_type_not_allowed") if c in str(e)), None)
                if not code:
                    raise
                refuses[f] = f"refusé par Drive ({code})"
        REFUSES_PAR_DRIVE.update(refuses)
        attendre(lambda: all(drive.etat(i) not in ("pending", "analyzing") for i in ids.values()), delai=180, pas=5, motif="la fin de l'analyse antivirus de Drive")
        r = session_testeur.post("/api/sources/fichiers/collections", {"espace_id": instance["id"], "dossiers": [{"id": racine, "chemin": titre}], "titre": f"Formats {titre}"})
        assert r.status == 200, f"création → {r.status} {r.text()[:300]}"
        nom = r.json()["collection"]
        statut = _travail_fini(session_testeur, nom, delai=900)
        yield nom, ids, statut
    finally:
        if nom:
            _menage(session_testeur, nom)
        drive.supprimer(racine)


def _textes(session, collection: str) -> dict[str, str]:
    """Le texte de chaque document indexé, tel que l'indexeur l'a lu (document entier, ou passages)."""
    r = session.get(f"/api/collections/{collection}/documents", params={"par_page": 100})
    textes = {}
    for d in (r.json() or {}).get("documents", []) if r.status == 200 else []:
        rr = session.get(f"/api/collections/{collection}/documents/{d['file_id']}")
        if rr.status == 200:
            corps = rr.json() or {}
            textes[d["file_id"]] = corps.get("markdown") or "\n".join(m.get("texte", "") for m in corps.get("morceaux") or [])
    return textes


@pytest.fixture(scope="module")
def textes_indexes(session_testeur, import_formats) -> dict[str, str]:
    """Les textes de l'index, une fois que tous les témoins attendus y sont, ou au bout de 10 min :
    l'indexeur lit en arrière-plan (conversion, OCR, vision). Un témoin absent est jugé par son test."""
    collection, _ids, _statut_ = import_formats
    attendus = {temoin for f, (a, temoin) in ATTENDU.items() if a == "indexe" and f not in REFUSES_PAR_DRIVE}
    dernier: dict = {}

    def tous_la():
        dernier.clear()
        dernier.update(_textes(session_testeur, collection))
        tout = "\n".join(dernier.values())
        return all(t in tout for t in attendus)

    try:
        attendre(tous_la, delai=600, pas=20, motif="tous les témoins dans l'index")
    except AssertionError:
        pass
    return dict(dernier)


#: Constats (`xfail(strict=True)`) : ce qui échoue aujourd'hui, et casse le jour où c'est corrigé.
CONSTATS = {
    "format.csv": "un .csv part vers l'indexeur sous son nom, qui le refuse : correctif #186",
    "format.json": "un .json part vers l'indexeur sous son nom, qui le refuse : correctif #186",
}


@pytest.mark.parametrize("fichier", [pytest.param(f, marks=pytest.mark.xfail(strict=True, reason=CONSTATS[f])) if f in CONSTATS else f for f in ATTENDU])
def test_chaque_format(import_formats, textes_indexes, fichier):
    _collection, ids, statut = import_formats
    if fichier in REFUSES_PAR_DRIVE:
        pytest.skip(f"{fichier} : {REFUSES_PAR_DRIVE[fichier]}")
    attendu, temoin = ATTENDU[fichier]
    ecarts = {e["id"]: e for e in (statut["travail"].get("documents_ecartes") or [])}
    ecart = ecarts.get(ids[fichier])
    if attendu != "indexe":
        assert ecart and ecart["code"] == attendu, f"attendu : écarté « {attendu} » ; vu : {ecart}"
        return
    assert not ecart, f"écarté au lieu d'être indexé : {ecart.get('code')} — {ecart.get('raison')}"
    assert any(_plie(temoin) in _plie(texte) for texte in textes_indexes.values()), f"{fichier} est indexé, mais son texte lu ne contient pas {temoin}"


def test_le_bilan_de_l_import(session_testeur, import_formats):
    collection, _ids, statut = import_formats
    t = statut["travail"]
    assert t["etat"] in ("termine", "a_jour"), t
    indexables = sum(1 for f, (a, _) in ATTENDU.items() if a == "indexe" and f not in REFUSES_PAR_DRIVE)
    # Les constats sont reçus mais refusés par l'indexeur : hors de l'index, comptés en erreur.
    documents = _statut(session_testeur, collection)["documents"]
    assert indexables - len(CONSTATS) <= documents <= indexables, (documents, indexables)
    assert t.get("en_erreur", 0) <= len(CONSTATS), t
