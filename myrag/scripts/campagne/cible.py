"""Le client de la cible de la campagne, et celui de la passerelle de modèles.

La cible : Mes collections, vue par un compte de test. Le jeton s'obtient une fois par la
connexion de la suite de bout en bout (`tests/e2e/_sso.connexion`, navigateur fermé aussitôt :
on lit dans `sessionStorage` ce que l'application y range, jeton d'accès et de renouvellement).
Ensuite :
- le jeton se renouvelle par `grant_type=refresh_token` avant son expiration (client public,
  sans secret) ;
- si le renouvellement est refusé — la session SSO a expiré, typiquement après une demi-heure
  d'inactivité —, on se reconnecte par le navigateur, une fois par refus, sans intervention ;
- chaque route a son seau (cadence), `Retry-After` est respecté ;
- `Garde` applique les règles d'arrêt : un incident de droits arrête tout, plus de 20 % de 5xx
  sur les 50 derniers appels arrête la nuit, une rafale de 429 divise la cadence par deux, une
  seconde rafale arrête la nuit.

La passerelle : un fournisseur OpenAI-compatible, appelé avec la clef DÉDIÉE à la campagne
(`CAMPAGNE_GATEWAY_TOKEN`). Jamais la clef du chat de tous (`MIRAI_GATEWAY_TOKEN`) : son quota
est celui des personnes. Chaque appel est compté contre un budget.

Ni adresse ni compte ici : tout vient des arguments et de l'environnement.
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

DELAI_S = 120.0
#: On renouvelle le jeton d'accès quand il lui reste moins que cela.
MARGE_S = 60
#: Les routes et leur cadence par défaut (appels par minute). Les assistants (`plan`, `executer`)
#: et le `/mcp` partagent le même quota côté serveur (30 par minute et par personne) : un seul seau.
CADENCES = {"assistants": 20.0, "recherche": 40.0, "liens": 30.0, "admin": 10.0}
ESSAIS_429 = 3
RAFALE_429 = 3
FENETRE_5XX = 50
PART_5XX_MAX = 0.20
RECONNEXIONS_MAX = 10


class Usage(Exception):
    """Un réglage manque ou ne va pas : rien n'a été appelé."""


class Arret(Exception):
    """Une règle d'arrêt a joué. `immediat` : la campagne entière s'arrête (incident de droits)."""

    def __init__(self, motif: str, detail: str = "", *, immediat: bool = False):
        super().__init__(f"{motif} : {detail}" if detail else motif)
        self.motif, self.detail, self.immediat = motif, detail, immediat


class SessionPerdue(Arret):
    """Ni renouvellement ni reconnexion : on ne peut plus parler à la cible au nom du compte."""

    def __init__(self, detail: str):
        super().__init__("session-perdue", detail)


class BudgetEpuise(Exception):
    """Le budget d'appels de la nuit est consommé : la phase s'arrête proprement."""


class ErreurMcp(Exception):
    def __init__(self, message: str, statut: int | None = None):
        super().__init__(message)
        self.statut = statut


def origine(url: str, nom: str = "--cible") -> str:
    """Une origine https, sauf sur le poste (http vers localhost) : un jeton ne circule pas en clair."""
    u = urlsplit((url or "").strip().rstrip("/"))
    if u.hostname and (u.scheme == "https" or (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1"))):
        return f"{u.scheme}://{u.netloc}"
    raise Usage(f"{nom} doit être une adresse https (http seulement vers localhost) : {url!r}")


# ─── Le jeton ────────────────────────────────────────────────────────────────────────────────


@dataclass
class Jeton:
    access_token: str
    refresh_token: str | None
    expires_at: float
    #: L'émetteur (`{sso}/realms/{realm}`) et le client public, lus dans la clé de session.
    autorite: str
    client_id: str
    refresh_expires_at: float | None = None

    def __repr__(self) -> str:  # jamais un jeton dans une trace
        return f"Jeton(client_id={self.client_id!r}, expires_at={self.expires_at})"


_SESSION_JS = """() => {
    for (let i = 0; i < sessionStorage.length; i++) {
        const cle = sessionStorage.key(i);
        if (!cle.startsWith('oidc.user:')) continue;
        const u = JSON.parse(sessionStorage.getItem(cle));
        return {cle: cle, access_token: u.access_token, refresh_token: u.refresh_token || null, expires_at: u.expires_at};
    }
    return null;
}"""


def jeton_de_session(info: dict | None) -> Jeton:
    """Le jeton tel que l'application le range : clé `oidc.user:<autorité>:<client>`."""
    if not info or not info.get("access_token") or not str(info.get("cle", "")).startswith("oidc.user:"):
        raise SessionPerdue("aucun jeton en session après la connexion")
    autorite, client = info["cle"].split(":", 1)[1].rsplit(":", 1)
    return Jeton(info["access_token"], info.get("refresh_token"), float(info.get("expires_at") or 0), autorite.rstrip("/"), client)


Connexion = Callable[[], Jeton]


def connexion_navigateur(base: str, sso_host: str, compte: str = "KC_TEST_IN") -> Connexion:
    """La connexion par le navigateur sans écran, comme la suite de bout en bout. Identifiant et
    mot de passe dans `<compte>_USERNAME` / `<compte>_PASSWORD`. Playwright n'est chargé qu'ici."""

    def connecter() -> Jeton:
        identifiant = os.environ.get(f"{compte}_USERNAME", "").strip()
        motdepasse = os.environ.get(f"{compte}_PASSWORD", "")
        if not identifiant or not motdepasse:
            raise Usage(f"{compte}_USERNAME et {compte}_PASSWORD sont requis pour la connexion")
        if not sso_host:
            raise Usage("CAMPAGNE_SSO_HOST est requis (l'hôte du SSO, pour reconnaître sa page)")
        from playwright.sync_api import sync_playwright  # ty: ignore[unresolved-import]

        from tests.e2e._sso import ARGS_NAVIGATEUR, connexion

        with sync_playwright() as p:
            nav = p.chromium.launch(args=ARGS_NAVIGATEUR)
            try:
                issue, detail, contexte = connexion(nav, base, sso_host, identifiant, motdepasse)
                try:
                    if issue != "entre":
                        raise SessionPerdue(f"connexion {issue} : {detail}")
                    info = contexte.pages[0].evaluate(_SESSION_JS)
                finally:
                    contexte.close()
            finally:
                nav.close()
        return jeton_de_session(info)

    return connecter


# ─── Cadence et règles d'arrêt ───────────────────────────────────────────────────────────────


class Seau:
    """Un appel au plus tous les `60 / par_minute` secondes ; `Retry-After` repousse le suivant."""

    def __init__(self, par_minute: float, horloge: Callable[[], float], dormir: Callable[[float], None]):
        self.intervalle = 60.0 / par_minute if par_minute > 0 else 0.0
        self._horloge, self._dormir, self._prochain = horloge, dormir, 0.0

    def attendre(self) -> None:
        maintenant = self._horloge()
        if maintenant < self._prochain:
            self._dormir(self._prochain - maintenant)
            maintenant = self._prochain
        self._prochain = maintenant + self.intervalle

    def repousser(self, secondes: float) -> None:
        self._prochain = max(self._prochain, self._horloge() + secondes)

    def ralentir(self) -> None:
        self.intervalle = self.intervalle * 2 if self.intervalle else 6.0

    @property
    def par_minute(self) -> float:
        return round(60.0 / self.intervalle, 2) if self.intervalle else 0.0


#: La route de vérification des liens cités : comptée, mais hors de la règle des 5xx.
ROUTE_LIENS = "liens"


class Garde:
    """Les règles d'arrêt d'une nuit (docs/campagne-recherche.md, « Règles d'arrêt »)."""

    def __init__(self) -> None:
        self.derniers: deque[bool] = deque(maxlen=FENETRE_5XX)  # vrai : 5xx ou injoignable
        self.suite_429: dict[str, int] = {}
        self.ralenties: set[str] = set()
        self.incidents: list[str] = []

    def noter(self, route: str, statut: int, seau: Seau) -> None:
        """`statut` 0 : la cible n'a pas répondu (compté comme un 5xx)."""
        if statut == 429:
            n = self.suite_429[route] = self.suite_429.get(route, 0) + 1
            if n >= RAFALE_429:
                if route in self.ralenties:
                    raise Arret("rafale-429", f"route {route} : seconde rafale malgré la cadence divisée par deux")
                self.ralenties.add(route)
                self.suite_429[route] = 0
                seau.ralentir()
            return
        self.suite_429[route] = 0
        if route == ROUTE_LIENS:
            return  # un lien cité qui casse est une mesure (rapport), pas une cible qui flanche
        self.derniers.append(statut == 0 or statut >= 500)
        if len(self.derniers) == FENETRE_5XX and sum(self.derniers) > PART_5XX_MAX * FENETRE_5XX:
            raise Arret("5xx", f"{sum(self.derniers)} erreurs serveur sur les {FENETRE_5XX} derniers appels")

    def incident(self, detail: str) -> None:
        """Un passage d'une source que le compte ne lit pas : tout s'arrête, sans attendre."""
        self.incidents.append(detail)
        raise Arret("incident-droits", detail, immediat=True)


# ─── La cible ────────────────────────────────────────────────────────────────────────────────


def lire_message_mcp(r: httpx.Response) -> dict:
    """La réponse JSON-RPC, en JSON ou en flux SSE (`data: {…}`) : le dernier message porteur d'un `id`."""
    if "text/event-stream" not in r.headers.get("content-type", ""):
        return r.json()
    message: dict = {}
    for ligne in r.text.splitlines():
        if ligne.startswith("data:"):
            try:
                d = json.loads(ligne[5:].strip())
            except ValueError:
                continue
            if isinstance(d, dict) and "id" in d:
                message = d
    if not message:
        raise ErreurMcp("flux SSE sans message JSON-RPC")
    return message


class Cible:
    """Mes collections vue par un compte. `connecter` rend un jeton (le navigateur, ou un faux en test)."""

    def __init__(
        self,
        base: str,
        connecter: Connexion,
        *,
        client: httpx.Client | None = None,
        cadences: dict[str, float] | None = None,
        horloge: Callable[[], float] = time.time,
        dormir: Callable[[float], None] = time.sleep,
        garde: Garde | None = None,
        journal: Callable[[dict], None] | None = None,
        origines_liens: tuple[str, ...] = (),
    ):
        self.base = origine(base)
        self._connecter = connecter
        self._client = client or httpx.Client(timeout=DELAI_S)
        self.horloge, self.dormir = horloge, dormir
        self.seaux = {route: Seau(n, horloge, dormir) for route, n in {**CADENCES, **(cadences or {})}.items()}
        self.garde = garde or Garde()
        self._journal = journal
        self._jeton: Jeton | None = None
        self.reconnexions = 0
        self.renouvellements = 0
        self.compteurs: dict[str, dict[str, int]] = {}
        self.origines_liens = {self.base, *(origine(o, "origine des liens") for o in origines_liens)}
        self._rpc = 0

    # Le jeton

    def jeton(self) -> str:
        if self._jeton is None:
            self._reconnecter(premiere=True)
        elif self._jeton.expires_at - self.horloge() < MARGE_S:
            self._renouveler()
        assert self._jeton is not None
        return self._jeton.access_token

    def _renouveler(self) -> None:
        j = self._jeton
        assert j is not None
        maintenant = self.horloge()
        if j.refresh_token and (j.refresh_expires_at is None or j.refresh_expires_at > maintenant + 5):
            try:
                r = self._client.post(
                    f"{origine(j.autorite, 'autorité du jeton')}{urlsplit(j.autorite).path}/protocol/openid-connect/token",
                    data={"grant_type": "refresh_token", "client_id": j.client_id, "refresh_token": j.refresh_token},
                )
            except httpx.TransportError:
                r = None
            if r is not None and r.status_code == 200:
                t = r.json()
                self._jeton = Jeton(
                    t["access_token"],
                    t.get("refresh_token") or j.refresh_token,
                    maintenant + float(t.get("expires_in") or 300),
                    j.autorite,
                    j.client_id,
                    maintenant + float(t["refresh_expires_in"]) if t.get("refresh_expires_in") else None,
                )
                self.renouvellements += 1
                return
        # Refus (400 : session SSO expirée), panne, ou plus de jeton de renouvellement : on se reconnecte.
        self._reconnecter()

    def _reconnecter(self, premiere: bool = False) -> None:
        if not premiere:
            if self.reconnexions >= RECONNEXIONS_MAX:
                raise SessionPerdue(f"{RECONNEXIONS_MAX} reconnexions dans la nuit : on s'arrête")
            self.reconnexions += 1
        try:
            self._jeton = self._connecter()
        except (Arret, Usage):
            raise
        except Exception as e:  # noqa: BLE001 — le navigateur peut échouer de mille façons
            raise SessionPerdue(f"la connexion a échoué ({type(e).__name__} : {str(e).splitlines()[0][:200] if str(e) else '—'})") from e

    def oublier_jeton(self) -> None:
        """Force le renouvellement au prochain appel (après un 401)."""
        if self._jeton is not None:
            self._jeton.expires_at = 0

    # Les appels

    def _noter(self, route: str, statut: int, ms: int) -> None:
        c = self.compteurs.setdefault(route, {"appels": 0, "429": 0, "5xx": 0, "injoignable": 0})
        c["appels"] += 1
        if statut == 429:
            c["429"] += 1
        elif statut == 0:
            c["injoignable"] += 1
        elif statut >= 500:
            c["5xx"] += 1
        if self._journal:
            self._journal({"route": route, "statut": statut, "ms": ms})
        self.garde.noter(route, statut, self.seaux[route])

    def appel(self, methode: str, chemin: str, *, route: str, authentifie: bool = True, **kw: Any) -> httpx.Response:
        """Un appel à la cible (`chemin` relatif), cadencé, renouvelé après un 401, réessayé après un 429."""
        url = chemin if chemin.startswith(("http://", "https://")) else f"{self.base}{chemin}"
        entetes = dict(kw.pop("headers", {}) or {})
        deja_401 = False
        r: httpx.Response | None = None
        for _ in range(1 + ESSAIS_429):
            self.seaux[route].attendre()
            if authentifie:
                entetes["Authorization"] = f"Bearer {self.jeton()}"
            debut = self.horloge()
            try:
                r = self._client.request(methode, url, headers=entetes, **kw)
            except httpx.TransportError:
                self._noter(route, 0, int((self.horloge() - debut) * 1000))
                raise
            self._noter(route, r.status_code, int((self.horloge() - debut) * 1000))
            if r.status_code == 401 and authentifie and not deja_401:
                deja_401 = True
                self.oublier_jeton()
                continue
            if r.status_code == 429:
                self.seaux[route].repousser(_retry_after(r))
                continue
            return r
        assert r is not None
        return r

    def mcp(self, methode: str, params: dict | None = None) -> dict:
        """Un appel JSON-RPC au serveur MCP (`/mcp`, sans état) : rend `result`, ou lève ErreurMcp."""
        self._rpc += 1
        corps = {"jsonrpc": "2.0", "id": self._rpc, "method": methode, "params": params or {}}
        r = self.appel("POST", "/mcp", route="assistants", json=corps, headers={"Accept": "application/json, text/event-stream"})
        if r.status_code != 200:
            raise ErreurMcp(f"HTTP {r.status_code}", r.status_code)
        message = lire_message_mcp(r)
        if "error" in message:
            raise ErreurMcp(str((message["error"] or {}).get("message") or "erreur JSON-RPC"))
        return message.get("result") or {}

    def lien(self, url: str) -> int | None:
        """Le statut d'un lien de lecture signé, ouvert SANS jeton (comme un client hors de
        l'application). `None` : le lien ne pointe pas vers la cible — on ne le suit pas."""
        u = urlsplit(url)
        if f"{u.scheme}://{u.netloc}" not in self.origines_liens:
            return None
        try:
            return self.appel("GET", url, route=ROUTE_LIENS, authentifie=False, follow_redirects=False).status_code
        except httpx.TransportError:
            return 0


def _retry_after(r: httpx.Response, defaut: float = 10.0) -> float:
    try:
        return max(1.0, float(r.headers.get("Retry-After", defaut)))
    except ValueError:
        return defaut


# ─── La passerelle de modèles ────────────────────────────────────────────────────────────────


class Passerelle:
    """Un fournisseur OpenAI-compatible, avec la clef dédiée et un budget d'appels."""

    ECHECS_MAX = 5

    def __init__(self, url: str, cle: str, *, max_appels: int, client: httpx.Client | None = None, dormir: Callable[[float], None] = time.sleep, deja: int = 0):
        u = urlsplit(url.strip())
        origine(url, "CAMPAGNE_GATEWAY_URL")
        self.url = f"{u.scheme}://{u.netloc}{u.path.rstrip('/')}"
        self._cle, self._client, self._dormir = cle, client or httpx.Client(timeout=DELAI_S), dormir
        self.max_appels, self.appels, self.deja = max_appels, 0, deja
        self.jetons = {"entree": 0, "sortie": 0}
        self._echecs = 0

    def __repr__(self) -> str:
        return f"Passerelle(url={self.url!r}, appels={self.appels})"

    @classmethod
    def depuis_env(cls, *, max_appels: int, client: httpx.Client | None = None, deja: int = 0) -> Passerelle:
        url = os.environ.get("CAMPAGNE_GATEWAY_URL", "").strip()
        cle = os.environ.get("CAMPAGNE_GATEWAY_TOKEN", "").strip()
        if not cle:
            raise Usage("CAMPAGNE_GATEWAY_TOKEN est requis : la campagne a sa clef, elle n'emprunte jamais celle du chat (MIRAI_GATEWAY_TOKEN)")
        if not url:
            raise Usage("CAMPAGNE_GATEWAY_URL est requis (l'adresse /v1 de la passerelle de modèles)")
        return cls(url, cle, max_appels=max_appels, client=client, deja=deja)

    @property
    def restants(self) -> int:
        return max(0, self.max_appels - self.deja - self.appels)

    def completer(self, corps: dict) -> dict:
        """`POST /chat/completions` ; BudgetEpuise avant l'appel qui dépasserait le budget."""
        if self.restants <= 0:
            raise BudgetEpuise(f"budget de {self.max_appels} appels de modèle atteint")
        self.appels += 1
        r: httpx.Response | None = None
        for _ in range(1 + ESSAIS_429):
            try:
                r = self._client.post(f"{self.url}/chat/completions", json=corps, headers={"Authorization": f"Bearer {self._cle}"})
            except httpx.TransportError as e:
                self._echec(type(e).__name__)
                raise
            if r.status_code == 429:
                self._dormir(_retry_after(r))
                continue
            break
        assert r is not None
        if r.status_code != 200:
            self._echec(f"HTTP {r.status_code}")
            r.raise_for_status()
            raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
        self._echecs = 0
        d = r.json()
        usage = d.get("usage") or {}
        self.jetons["entree"] += int(usage.get("prompt_tokens") or 0)
        self.jetons["sortie"] += int(usage.get("completion_tokens") or 0)
        return d

    def _echec(self, detail: str) -> None:
        self._echecs += 1
        if self._echecs >= self.ECHECS_MAX:
            raise Arret("passerelle", f"{self._echecs} échecs de suite ({detail})")
