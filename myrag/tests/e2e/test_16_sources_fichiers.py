"""Parcours 16 — la source Fichiers (Drive de La Suite) : d'un dossier Drive à une collection qui répond.

Le testeur dépose un petit corpus dans SON Drive (un dossier `e2e-fichiers-<date>-<heure>`), l'importe
dans une collection, puis vérifie ce que Mes collections en a fait : ce qui est indexé, ce qui est
écarté et pourquoi, la portée privée, le plafond de sensibilité, la mise à jour après des changements
dans Drive, et une réponse qui cite le témoin du corpus. Le dossier Drive et la collection sont
effacés à la fin, même en cas d'échec.

Ignoré si la capacité `fichiers` est éteinte ou si le testeur ne voit aucune instance. Le fichier
de test antivirus (EICAR) n'est déposé que si `E2E_FICHIERS_EICAR=1` : il déclenche l'alerte
antivirus de l'instance, à n'activer qu'avec l'accord de son exploitant.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import os
import time
import zipfile

import pytest

from tests.e2e.conftest import _menage, attendre, prefixe_de_la_cible

TEMOIN = "ORCHIDEE-5172"
QUESTION = "Quel est le code de contrôle du corpus Fichiers de la suite de bout en bout ?"
NOTE_TEMOIN = f"# Note de contrôle Fichiers\n\nLe code de contrôle du corpus Fichiers de la suite de bout en bout est {TEMOIN}.\n".encode()
NOTE_B = "# Note B\n\nUn texte fictif sur la gestion des archives courantes.\n".encode()
NOTE_C = "# Note C\n\nUn texte fictif sur la conservation des dossiers.\n".encode()
NOTE_D = "# Note D\n\nUn texte fictif ajouté après l'import.\n".encode()
#: Le fichier de test antivirus standard (EICAR) : inoffensif, reconnu par tout antivirus.
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
FIN_DE_TRAVAIL = {"termine", "a_jour", "partiel", "echec", "interrompu"}


def _zip() -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("dedans.txt", "texte fictif")
    return tampon.getvalue()


class Drive:
    """Les gestes du testeur dans son Drive, par l'API que l'interface de Drive utilise, avec son
    jeton de Mes collections (Drive le vérifie auprès du même SSO)."""

    def __init__(self, session, hote: str):
        self.session = session
        self.api = f"https://{hote}/api/v1.0"

    def _entetes(self, json_: bool = True) -> dict:
        e = {"Authorization": f"Bearer {self.session.jeton}"}
        if json_:
            e["Content-Type"] = "application/json"
        return e

    def _post(self, chemin: str, corps: dict | None = None):
        r = self.session.page.request.post(self.api + chemin, headers=self._entetes(), data=json.dumps(corps or {}))
        assert r.status in (200, 201), f"Drive {chemin} → {r.status} {r.text()[:200]}"
        return r.json() if r.text() else {}

    def dossier(self, titre: str, parent: str | None = None) -> str:
        chemin = f"/items/{parent}/children/" if parent else "/items/"
        return self._post(chemin, {"type": "folder", "title": titre})["id"]

    def deposer(self, parent: str, nom: str, octets: bytes) -> str:
        """Le dépôt en trois temps : l'élément, les octets au stockage (adresse signée), la fin d'envoi."""
        item = self._post(f"/items/{parent}/children/", {"type": "file", "filename": nom, "size": len(octets)})
        r = self.session.page.request.put(item["policy"], data=octets, headers={"X-amz-acl": "private"})
        assert r.status in (200, 204), f"stockage → {r.status} {r.text()[:200]}"
        self._post(f"/items/{item['id']}/upload-ended/")
        return item["id"]

    def supprimer(self, ident: str) -> None:
        self.session.page.request.delete(f"{self.api}/items/{ident}/", headers=self._entetes(False))

    def etat(self, ident: str) -> str:
        r = self.session.page.request.get(f"{self.api}/items/{ident}/", headers=self._entetes(False))
        return str((r.json() or {}).get("upload_state") or "") if r.status == 200 else f"http-{r.status}"


@pytest.fixture(scope="module")
def instance(session_testeur) -> dict:
    r = session_testeur.get("/api/sources/fichiers/instances")
    if r.status == 404:
        pytest.skip("capacité `fichiers` éteinte sur la cible")
    assert r.status == 200, r.text()[:200]
    instances = (r.json() or {}).get("instances") or []
    if not instances:
        pytest.skip("le testeur ne voit aucune instance Fichiers")
    return instances[0]


@pytest.fixture(scope="module")
def corpus(session_testeur, instance):
    """Le dossier d'essai dans le Drive du testeur, effacé à la fin."""
    drive = Drive(session_testeur, instance["hote"])
    titre = "e2e-fichiers-" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    racine = drive.dossier(titre)
    ids = {"racine": racine, "titre": titre}
    try:
        ids["temoin"] = drive.deposer(racine, "note-temoin.md", NOTE_TEMOIN)
        ids["b"] = drive.deposer(racine, "note-b.md", NOTE_B)
        ids["vide"] = drive.deposer(racine, "vide.md", b"")
        ids["zip"] = drive.deposer(racine, "archive.zip", _zip())
        sous = drive.dossier("sous-dossier", racine)
        ids["sous"] = sous
        ids["c"] = drive.deposer(sous, "note-c.md", NOTE_C)
        ids["copie"] = drive.deposer(sous, "copie-de-c.md", NOTE_C)
        if os.environ.get("E2E_FICHIERS_EICAR") == "1":
            ids["eicar"] = drive.deposer(racine, "eicar.txt", EICAR)
        yield drive, ids
    finally:
        drive.supprimer(racine)


def _statut(session, nom: str) -> dict:
    r = session.get(f"/api/sources/fichiers/status/{nom}")
    return r.json() if r.status == 200 else {}


def _travail_fini(session, nom: str, delai: float = 300.0) -> dict:
    return attendre(
        lambda: (lambda s: s if (s.get("travail") or {}).get("etat") in FIN_DE_TRAVAIL else None)(_statut(session, nom)),
        delai=delai,
        pas=3,
        motif="la fin de l'import ou de la mise à jour",
    )


@pytest.fixture(scope="module")
def collection(session_testeur, instance, corpus) -> str:
    _drive, ids = corpus
    # Drive analyse chaque fichier reçu (antivirus) avant de le servir : on laisse finir.
    attendre(
        lambda: all(_drive.etat(ids[k]) not in ("pending", "analyzing") for k in ("temoin", "b", "c", "copie", "zip")),
        delai=120,
        pas=3,
        motif="la fin de l'analyse antivirus de Drive",
    )
    r = session_testeur.post(
        "/api/sources/fichiers/collections",
        {
            "espace_id": instance["id"],
            "dossiers": [{"id": ids["racine"], "chemin": ids["titre"]}],
            "titre": f"Corpus Fichiers {ids['titre']}",
        },
    )
    assert r.status == 200, f"création → {r.status} {r.text()[:300]}"
    nom = (r.json() or {}).get("collection") or (r.json() or {}).get("name")
    assert nom and nom.startswith(prefixe_de_la_cible(session_testeur) + "fichiers-"), r.text()[:200]
    try:
        _travail_fini(session_testeur, nom)
        yield nom
    finally:
        _menage(session_testeur, nom)


def test_les_instances_disent_leur_hote_et_leur_plafond(instance):
    assert instance["hote"] and "://" not in instance["hote"]
    assert instance["sensibilite_max"] and instance["niveaux_permis"]
    assert instance["sensibilite_max"] in instance["niveaux_permis"]


def test_le_dossier_d_essai_est_vu_et_compte(session_testeur, instance, corpus):
    _drive, ids = corpus
    r = session_testeur.get(f"/api/sources/fichiers/espaces/{instance['id']}/dossiers", params={"recherche": ids["titre"]})
    assert r.status == 200 and any(d["id"] == ids["racine"] for d in r.json()["dossiers"])
    r = session_testeur.get(f"/api/sources/fichiers/espaces/{instance['id']}/apercu", params={"dossier": ids["racine"]})
    assert r.status == 200, r.text()[:200]
    assert (r.json() or {}).get("total", 0) >= 6, r.text()[:200]


def test_l_import_indexe_le_lisible_et_explique_chaque_ecart(session_testeur, collection, corpus):
    _drive, ids = corpus
    s = _statut(session_testeur, collection)
    t = s["travail"]
    assert t["etat"] in ("termine", "a_jour"), t
    codes = {e["id"]: e["code"] for e in t.get("documents_ecartes") or []}
    indexes = s["documents"]
    assert indexes == 3, f"attendu : témoin, B, C (vide, zip et copie écartés) ; vu {indexes}, écarts {codes}"
    assert codes.get(ids["zip"]) == "format", codes
    assert codes.get(ids["copie"]) == "doublon" or codes.get(ids["c"]) == "doublon", codes
    assert ids["vide"] in codes, codes


@pytest.mark.xfail(strict=True, reason="Un document vide dans Fichiers est rangé « autre » : le code document_vide n'a pas d'explication (correctif : ecarts « vide »)")
def test_un_document_vide_est_explique_comme_tel(session_testeur, collection, corpus):
    _drive, ids = corpus
    codes = {e["id"]: e["code"] for e in (_statut(session_testeur, collection)["travail"].get("documents_ecartes") or [])}
    assert codes.get(ids["vide"]) == "vide", codes.get(ids["vide"])


def test_la_collection_nait_privee(session_testeur, collection):
    r = session_testeur.get(f"/api/collections/{collection}")
    assert r.status == 200
    assert (r.json() or {}).get("scope") == "private"


def test_une_sensibilite_sous_le_plafond_est_refusee(session_testeur, instance, corpus):
    if instance["sensibilite_max"] == "public":
        pytest.skip("plafond « public » : rien en dessous")
    _drive, ids = corpus
    r = session_testeur.post(
        "/api/sources/fichiers/collections",
        {
            "espace_id": instance["id"],
            "dossiers": [{"id": ids["racine"], "chemin": ids["titre"]}],
            "titre": "refusée",
            "suffixe": "refus",
            "sensibilite": "public",
        },
    )
    assert r.status == 409 and (r.json().get("detail") or {}).get("code") == "sensibilite_incompatible", r.text()[:300]


def test_une_question_trouve_le_temoin(session_testeur, collection):
    """L'indexation est asynchrone : on repose la question tant que le témoin n'est pas dans la réponse."""

    def repondre():
        r = session_testeur.post(f"/api/playground/{collection}/chat", {"question": QUESTION}, timeout=180_000)
        return r.json().get("response", "") if r.status == 200 and TEMOIN in r.text() else None

    reponse = attendre(repondre, delai=420, pas=20, motif=f"le témoin « {TEMOIN} » dans une réponse")
    assert TEMOIN in reponse


def test_la_mise_a_jour_suit_les_changements_de_drive(session_testeur, collection, corpus):
    drive, ids = corpus
    drive.supprimer(ids["b"])
    ids["d"] = drive.deposer(ids["racine"], "note-d.md", NOTE_D)
    attendre(lambda: drive.etat(ids["d"]) not in ("pending", "analyzing"), delai=120, pas=3, motif="l'analyse de note-d")
    r = session_testeur.post(f"/api/sources/fichiers/sync/{collection}", {})
    assert r.status in (200, 202), r.text()[:300]
    time.sleep(2)
    t = _travail_fini(session_testeur, collection)["travail"]
    assert (t.get("ajoutes"), t.get("retires")) == (1, 1), t
    assert _statut(session_testeur, collection)["documents"] == 3


def test_un_fichier_tout_juste_depose_est_lu_ou_attend_sans_erreur(session_testeur, collection, corpus):
    """Juste après le dépôt, Drive peut encore analyser le fichier : il est alors écarté pour la passe
    (« en cours d'analyse ») et repris à la suivante. Jamais une erreur."""
    drive, ids = corpus
    ids["e"] = drive.deposer(ids["racine"], "note-e.md", "# Note E\n\nTexte fictif tout juste déposé.\n".encode())
    etat_au_depot = drive.etat(ids["e"])
    session_testeur.post(f"/api/sources/fichiers/sync/{collection}", {})
    time.sleep(2)
    s = _travail_fini(session_testeur, collection)
    codes = {e["id"]: e["code"] for e in s["travail"].get("documents_ecartes") or []}
    assert s["travail"]["etat"] in ("termine", "a_jour"), s["travail"]
    assert codes.get(ids["e"]) in (None, "en_cours_d_analyse", "en_cours_d_envoi"), (etat_au_depot, codes.get(ids["e"]))
    print(f"\nnote-e : état Drive au dépôt « {etat_au_depot} », à la mise à jour : {codes.get(ids['e']) or 'indexée'}")


def test_un_fichier_signale_par_l_antivirus_n_est_pas_indexe(session_testeur, collection, corpus):
    drive, ids = corpus
    if "eicar" not in ids:
        pytest.skip("E2E_FICHIERS_EICAR=1 absent : pas de fichier de test antivirus")
    etat = attendre(lambda: (lambda e: e if e not in ("pending", "analyzing") else None)(drive.etat(ids["eicar"])), delai=180, pas=5, motif="le verdict de l'antivirus")
    s = _statut(session_testeur, collection)
    assert etat == "suspicious", f"l'antivirus de Drive n'a pas signalé le fichier EICAR : {etat}"
    codes = {e["id"]: e["code"] for e in s["travail"].get("documents_ecartes") or []}
    assert ids["eicar"] not in codes, "un fichier suspect sort de la liste, il n'est pas un écart"
