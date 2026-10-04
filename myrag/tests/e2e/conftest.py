"""Suite de bout en bout de Mes collections : un navigateur sans écran, une cible RÉELLE.

Rien ici ne connaît la cible. Adresses et comptes viennent de l'environnement (README.md) :
sans `E2E_BASE_URL`, toute la suite est ignorée avec un motif clair, et `pytest tests/unit`
reste ce qu'il était. Les tests sont numérotés dans l'ordre de la séquence d'usage, et
partagent une seule session de testeur : ce qu'un test crée, le suivant le trouve.

Convention : un test écrit le comportement ATTENDU. Là où l'application échoue aujourd'hui,
il porte `xfail(strict=True, reason=…)` : la suite reste verte, le défaut est documenté par
un test, et il casse le jour où le correctif arrive, ce qui oblige à retirer la marque.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import re
import tempfile
import time

import pytest

from tests.e2e._sso import connexion, jeton_de_session

ICI = pathlib.Path(__file__).resolve().parent
TEMOIN = "QUETZAL-9031"
QUESTION_TEMOIN = "Quel est le code de contrôle de la suite de bout en bout ?"
DOCUMENT_TEMOIN = ICI / "fixtures" / "note-de-controle.md"


def _env(nom: str, defaut: str = "") -> str:
    return os.environ.get(nom, defaut).strip()


BASE = _env("E2E_BASE_URL").rstrip("/")


# --- collecte : tout marquer e2e, tout ignorer sans cible ----------------------------------

def pytest_collection_modifyitems(config, items):
    for item in items:
        if ICI not in pathlib.Path(str(item.fspath)).resolve().parents:
            continue
        item.add_marker(pytest.mark.e2e)
        if not BASE:
            item.add_marker(pytest.mark.skip(
                reason="E2E_BASE_URL absent : suite de bout en bout ignorée (tests/e2e/README.md)"))
        elif item.get_closest_marker("captures") and not _env("E2E_CAPTURES"):
            item.add_marker(pytest.mark.skip(reason="E2E_CAPTURES absent : pas de captures"))


# --- la cible et le navigateur ------------------------------------------------------------

@pytest.fixture(scope="session")
def cible() -> dict:
    return {
        "base": BASE,
        "sso": _env("E2E_SSO_HOST"),
        "assistant": _env("E2E_ASSISTANT_URL").rstrip("/"),
    }


@pytest.fixture(scope="session")
def navigateur():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=_env("E2E_HEADED") != "1")
        yield nav
        nav.close()


# --- une session : un contexte connecté, et l'API vue comme l'interface la voit -----------

class Session:
    """Un compte entré dans l'application : sa page, son jeton (relu à chaque appel, il suit
    le renouvellement silencieux) et des appels d'API faits comme l'interface les fait."""

    def __init__(self, contexte, page, jeton: str, cible: dict):
        self.contexte, self.page, self._jeton, self.cible = contexte, page, jeton, cible
        self.base = cible["base"]

    @property
    def jeton(self) -> str:
        return jeton_de_session(self.page) or self._jeton

    def _entetes(self, json_: bool = False) -> dict:
        entetes = {"Authorization": f"Bearer {self.jeton}"}
        if json_:
            entetes["Content-Type"] = "application/json"
        return entetes

    def get(self, chemin: str, **kw):
        return self.page.request.get(self.base + chemin, headers=self._entetes(), **kw)

    def delete(self, chemin: str, **kw):
        return self.page.request.delete(self.base + chemin, headers=self._entetes(), **kw)

    def _envoyer(self, methode: str, chemin: str, corps, **kw):
        appel = getattr(self.page.request, methode)
        if corps is None:
            return appel(self.base + chemin, headers=self._entetes(), **kw)
        return appel(self.base + chemin, headers=self._entetes(True),
                     data=json.dumps(corps), **kw)

    def post(self, chemin: str, corps=None, **kw):
        return self._envoyer("post", chemin, corps, **kw)

    def put(self, chemin: str, corps=None, **kw):
        return self._envoyer("put", chemin, corps, **kw)

    def patch(self, chemin: str, corps=None, **kw):
        return self._envoyer("patch", chemin, corps, **kw)

    def aller(self, chemin: str, attendre: str = "networkidle"):
        self.page.goto(self.base + chemin, wait_until=attendre, timeout=45_000)
        return self.page

    def texte(self) -> str:
        """Le texte visible de la page, espaces repliés : ce qu'une personne lit."""
        return re.sub(r"[ \t]+", " ", self.page.locator("body").inner_text())

    def groupes(self) -> list[str]:
        """Les groupes portés par le jeton (lecture sans vérification : l'API, elle, vérifie)."""
        import base64
        try:
            charge = self.jeton.split(".")[1]
            charge += "=" * (-len(charge) % 4)
            return list(json.loads(base64.urlsafe_b64decode(charge)).get("groups") or [])
        except Exception:
            return []


def _compte(prefixe: str):
    identifiant, motdepasse = _env(f"{prefixe}_USERNAME"), _env(f"{prefixe}_PASSWORD")
    return (identifiant, motdepasse) if identifiant and motdepasse else None


def _ouvrir(navigateur, cible, prefixe: str, obligatoire: bool, chemin: str = "/"):
    compte = _compte(prefixe)
    if not compte:
        if obligatoire:
            pytest.fail(f"{prefixe}_USERNAME / {prefixe}_PASSWORD absents de l'environnement")
        pytest.skip(f"{prefixe}_USERNAME / {prefixe}_PASSWORD absents : parcours ignoré")
    issue, detail, contexte = connexion(navigateur, cible["base"], cible["sso"], *compte, chemin=chemin)
    if issue == "poste-sous-vpn":
        contexte.close()
        pytest.skip(detail)
    return issue, detail, contexte


@pytest.fixture(scope="session")
def session_testeur(navigateur, cible) -> Session:
    """Le compte membre du groupe requis. Toute la séquence d'usage se joue avec lui."""
    issue, detail, contexte = _ouvrir(navigateur, cible, "E2E_TESTEUR", obligatoire=True)
    if issue != "entre":
        contexte.close()
        pytest.fail(f"le compte testeur n'entre pas : {issue} : {detail}")
    yield Session(contexte, contexte.pages[0], detail, cible)
    contexte.close()


@pytest.fixture(scope="session")
def session_admin(navigateur, cible) -> Session:
    """Un compte superadmin ; les tests qui le demandent sont ignorés s'il n'est pas fourni."""
    issue, detail, contexte = _ouvrir(navigateur, cible, "E2E_ADMIN", obligatoire=False)
    if issue != "entre":
        contexte.close()
        pytest.fail(f"le compte administrateur n'entre pas : {issue} : {detail}")
    session = Session(contexte, contexte.pages[0], detail, cible)
    if not any(g.endswith("/superadmin") for g in session.groupes()):
        contexte.close()
        pytest.skip("E2E_ADMIN n'est pas superadmin (aucun groupe …/superadmin dans le jeton)")
    yield session
    contexte.close()


@pytest.fixture(scope="session")
def verdict_hors_groupe(navigateur, cible) -> tuple[str, str]:
    """Ce que l'application fait d'un compte valide mais hors du groupe requis."""
    issue, detail, contexte = _ouvrir(navigateur, cible, "E2E_HORS_GROUPE", obligatoire=False)
    contexte.close()
    return issue, detail if issue != "entre" else "le compte est entré"


# --- données d'essai : une collection, nettoyée avant et après ------------------------------

def _menage(session: Session, nom: str) -> None:
    """Efface la collection, quoi qu'il soit arrivé avant (dépublier, archiver, purger)."""
    for appel in (lambda: session.post(f"/api/collections/{nom}/unpublish", {}),
                  lambda: session.post(f"/api/collections/{nom}/archive", {}),
                  lambda: session.delete(f"/api/collections/{nom}")):
        try:
            appel()
        except Exception:
            pass


@pytest.fixture(scope="session")
def collection_essai(session_testeur) -> str:
    """Le nom de la collection que la séquence crée. Les orphelines `e2e-*` d'une campagne
    interrompue sont purgées d'abord ; la collection l'est à la fin, même en cas d'échec."""
    nom = "e2e-" + _dt.date.today().strftime("%Y%m%d")
    try:
        reponse = session_testeur.get("/api/collections?include_archived=true")
        for c in reponse.json() if reponse.status == 200 else []:
            if str(c.get("name", "")).startswith("e2e-"):
                _menage(session_testeur, c["name"])
    except Exception:
        pass
    yield nom
    _menage(session_testeur, nom)


@pytest.fixture(scope="session")
def collection_publiee(session_testeur) -> dict:
    """Une collection déjà publiée à tous sur la cible, et une question qui la concerne :
    ce que l'accueil propose à un nouveau venu."""
    reponse = session_testeur.get("/api/accueil/exemple")
    exemple = (reponse.json() or {}).get("exemple") if reponse.status == 200 else None
    if not exemple or not exemple.get("name"):
        pytest.skip("aucune collection publiée à tous sur la cible : l'accueil n'a pas d'exemple")
    return exemple


# --- captures : l'instrument du rapport d'ergonomie ------------------------------------------

class Captures:
    def __init__(self, dossier: pathlib.Path | None):
        self.dossier = dossier

    def prendre(self, page, nom: str, mobile: bool = True) -> None:
        """Une image de la page entière, son texte visible, et la même page à 390 px."""
        if not self.dossier:
            return
        self.dossier.mkdir(parents=True, exist_ok=True)
        page.wait_for_timeout(300)
        page.screenshot(path=str(self.dossier / f"{nom}.png"), full_page=True)
        (self.dossier / f"{nom}.txt").write_text(
            re.sub(r"[ \t]+", " ", page.locator("body").inner_text()), encoding="utf-8")
        if mobile:
            taille = page.viewport_size or {"width": 1280, "height": 800}
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(400)
            page.screenshot(path=str(self.dossier / f"{nom}-mobile.png"), full_page=True)
            page.set_viewport_size(taille)
            page.wait_for_timeout(200)


@pytest.fixture(scope="session")
def captures() -> Captures:
    dossier = _env("E2E_CAPTURES")
    return Captures(pathlib.Path(dossier) if dossier else None)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """À l'échec d'un test e2e, une image de la page du testeur, pour comprendre sans rejouer."""
    issue = yield
    rapport = issue.get_result()
    if rapport.when != "call" or not rapport.failed or not BASE:
        return
    session = next((v for v in item.funcargs.values() if isinstance(v, Session)), None)
    if session is None:
        return
    dossier = pathlib.Path(_env("E2E_CAPTURES") or tempfile.gettempdir()) / "_echecs"
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"{re.sub(r'[^a-zA-Z0-9_-]+', '_', item.name)}.png"
        session.page.screenshot(path=str(chemin), full_page=True)
        rapport.sections.append(("capture à l'échec", str(chemin)))
    except Exception:
        pass


# --- attentes utilitaires -------------------------------------------------------------------

def attendre(condition, delai: float = 60.0, pas: float = 2.0, motif: str = "condition"):
    """Attend qu'une condition rende vrai, plutôt que de supposer un délai."""
    fin = time.time() + delai
    while time.time() < fin:
        valeur = condition()
        if valeur:
            return valeur
        time.sleep(pas)
    raise AssertionError(f"{motif} : rien après {delai:.0f} s")
