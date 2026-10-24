"""Le client du service d'export Résana (contrat v1 : owuitools-resana, `docs/export-v1.md`).

Résana n'a pas d'API publique : le service `resana` sert, avec **la session Résana de la
personne**, quatre routes en lecture sous `/export/v1`. Mes collections s'y présente avec deux
en-têtes, tous deux obligatoires :

- `X-Internal-Token` : le secret propre à Mes collections (`MYCOLLECTIONS_RESANA_EXPORT_SECRET`) ;
- `Authorization: Bearer <jeton d'accès de la personne>` : le jeton reçu du navigateur, relayé tel
  quel (le service vérifie lui-même signature, émetteur, `azp` et prend `email`). Jamais d'adresse
  en paramètre ni de compte de service : les droits Résana appliqués sont ceux de la personne.

Erreurs du service : `{code, message, reessayable}` (+ `url_connexion` pour `session_absente`),
rendues ici en `ErreurResana`. Aucun mot de passe n'est jamais demandé : une session absente se
dit avec le lien de connexion que donne le service.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from urllib.parse import unquote

import httpx

PREFIXE = "/export/v1"
#: `/espaces` peut lancer la connexion automatique (coffre + navigateur, 20 à 40 s) : 90 s au moins.
DELAI_ESPACES_S = 90.0
DELAI_S = 60.0
#: Plafonds du contrat : 100 Mo par fichier, 5 000 documents par dossier.
OCTETS_MAX_FICHIER = 100 * 1024 * 1024
DOCUMENTS_MAX = 5000
LIMITE_PAGE = 200
#: Une liste en cache expirée (`410 curseur_perime`) se relit une fois depuis le début.
RELECTURES_CURSEUR = 1
#: Un grand dossier se prépare côté service (`202 en_preparation`, un appel Résana par dossier) :
#: on rappelle la même adresse au rythme de `Retry-After`, sans dépasser ce délai.
ATTENTE_PREPARATION_MAX_S = 20 * 60

MESSAGES = {
    "session_absente": "Vous n'avez pas de session Résana ouverte. Connectez-vous à Résana depuis le lien proposé, puis réessayez.",
    "jeton_invalide": "Votre connexion n'est pas reconnue par le service Résana : reconnectez-vous à Mes collections, puis réessayez.",
    "appelant_inconnu": "Mes collections n'est pas autorisé par le service Résana : la configuration est à vérifier.",
    "hors_droits": "Résana vous refuse ce document.",
    "introuvable": "Cet espace, ce dossier ou ce document est introuvable dans votre Résana.",
    "trop_de_documents": "Ce dossier contient trop de documents (5 000 au plus) : choisissez un sous-dossier.",
    "trop_volumineux": "Un document dépasse la taille admise (100 Mo).",
    "resana_indisponible": "Résana ne répond pas pour le moment. Réessayez dans un instant.",
    "curseur_perime": "La liste des documents a expiré : relancez l'import.",
    "dossier_requis": "Choisissez un dossier : un espace entier ne s'importe pas.",
    "espace_requis": "L'espace du document est requis.",
    "parametre_invalide": "Paramètre refusé par le service Résana.",
    "reponse_illisible": "Le service Résana a répondu de façon inattendue.",
    "service_injoignable": "Le service Résana est injoignable pour le moment. Réessayez dans un instant.",
    "disque_plein": "Le disque de Mes collections est presque plein : l'indexation s'est arrêtée en route. Les documents reçus sont gardés ; réessayez plus tard.",
    "en_preparation": "Le service Résana prépare la liste de ce dossier.",
    "preparation_trop_longue": "La liste de ce dossier n'a pas pu être préparée à temps : réessayez, ou choisissez un sous-dossier.",
}


class ErreurResana(Exception):
    """Une erreur du service d'export, prête à rendre à l'écran."""

    def __init__(self, statut: int, code: str, message: str = "", *, reessayable: bool = False, url_connexion: str | None = None):
        self.statut, self.code, self.reessayable, self.url_connexion = statut, code, reessayable, url_connexion
        self.message = MESSAGES.get(code) or message or "Erreur du service Résana."
        super().__init__(f"{statut} {code}")

    def detail(self) -> dict:
        d = {"code": self.code, "message": self.message, "reessayable": self.reessayable}
        if self.url_connexion:
            d["url_connexion"] = self.url_connexion
        return d


class EnPreparation(ErreurResana):
    """`202 en_preparation` : la liste d'un grand dossier se prépare ; rappeler la même adresse."""

    def __init__(self, dossiers_lus: int | None, dossiers: int | None, attente: float):
        super().__init__(202, "en_preparation", reessayable=True)
        self.dossiers_lus, self.dossiers, self.attente = dossiers_lus, dossiers, attente

    def detail(self) -> dict:
        return {**super().detail(), "dossiers_lus": self.dossiers_lus, "dossiers": self.dossiers}


@dataclass(frozen=True)
class Espace:
    id: str
    nom: str


@dataclass(frozen=True)
class Dossier:
    id: str
    titre: str
    parent_id: str | None
    chemin: str


@dataclass(frozen=True)
class DocumentResana:
    id: str
    titre: str
    nom_fichier: str
    mime: str
    dossier_id: str | None
    chemin: str
    url_consultation: str
    modifie_le: str | None = None
    meme_titre_que: str | None = None
    #: L'identifiant du FICHIER derrière le document (change a priori à chaque version, sans
    #: garantie : seul le sha256 décide qu'un document a changé).
    version_fichier: str | None = None
    #: La taille qu'affiche Résana, en Mo arrondis (les octets exacts ne sont pas donnés).
    taille_approx_mo: float | None = None


@dataclass
class Fichier:
    contenu: bytes
    nom: str
    mime: str
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self.sha256 = hashlib.sha256(self.contenu).hexdigest()


def _ident(v) -> str:
    return str(v).strip() if v is not None else ""


def _taille(v) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and v >= 0 else None


_NOM_DISPOSITION = re.compile(r"filename\*=(?:UTF-8|utf-8)''([^;]+)|filename=\"?([^\";]+)\"?")


def nom_depuis_disposition(entete: str | None, repli: str) -> str:
    """Le nom de fichier d'un `Content-Disposition` (forme `filename*=UTF-8''…` d'abord)."""
    m = _NOM_DISPOSITION.search(entete or "")
    if not m:
        return repli
    nom = unquote(m.group(1)) if m.group(1) else m.group(2)
    nom = nom.replace("/", "_").replace("\\", "_").strip()
    return nom or repli


class ClientExportResana:
    """Les quatre routes du contrat, avec le jeton de la personne. `transport` : pour les tests."""

    def __init__(self, base_url: str, secret: str, jeton: str, *, transport: httpx.AsyncBaseTransport | None = None):
        if not base_url or not secret:
            raise ErreurResana(503, "service_injoignable", "Le service Résana n'est pas configuré.")
        if not jeton:
            raise ErreurResana(401, "jeton_invalide")
        self.base_url = base_url.rstrip("/") + PREFIXE
        self._entetes = {"X-Internal-Token": secret, "Authorization": f"Bearer {jeton}", "Accept": "application/json"}
        self._transport = transport

    def renouveler_jeton(self, jeton: str) -> bool:
        """Remplace le jeton de la personne par un plus récent, pour les appels suivants (une tâche
        longue survit ainsi à l'expiration du jeton qu'elle avait au départ). Rend True s'il a changé."""
        jeton = (jeton or "").strip()
        if not jeton or self._entetes.get("Authorization") == f"Bearer {jeton}":
            return False
        self._entetes["Authorization"] = f"Bearer {jeton}"
        return True

    def _client(self, delai: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, headers=self._entetes, timeout=delai, transport=self._transport, follow_redirects=False)

    @staticmethod
    def _erreur(reponse: httpx.Response) -> ErreurResana:
        try:
            corps = reponse.json()
        except ValueError:
            corps = {}
        if not isinstance(corps, dict):
            corps = {}
        code = str(corps.get("code") or ("resana_indisponible" if reponse.status_code >= 500 else "reponse_illisible"))
        url = corps.get("url_connexion")
        return ErreurResana(
            reponse.status_code,
            code,
            str(corps.get("message") or ""),
            reessayable=bool(corps.get("reessayable", reponse.status_code >= 500)),
            url_connexion=url if isinstance(url, str) and url.startswith("https://") else None,
        )

    @staticmethod
    def _preparation(reponse: httpx.Response) -> EnPreparation:
        try:
            corps = reponse.json()
        except ValueError:
            corps = {}
        corps = corps if isinstance(corps, dict) else {}

        def entier(v) -> int | None:
            return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None

        attente = reponse.headers.get("retry-after", "")
        return EnPreparation(entier(corps.get("dossiers_lus")), entier(corps.get("dossiers")), float(attente) if attente.isdigit() else 10.0)

    async def _json(self, chemin: str, params: dict | None = None, *, delai: float = DELAI_S) -> dict:
        try:
            async with self._client(delai) as c:
                r = await c.get(chemin, params={k: v for k, v in (params or {}).items() if v not in (None, "")})
        except httpx.TimeoutException:
            raise ErreurResana(504, "service_injoignable", reessayable=True) from None
        except httpx.HTTPError:
            raise ErreurResana(502, "service_injoignable", reessayable=True) from None
        if r.status_code == 202:
            raise self._preparation(r)
        if r.status_code != 200:
            raise self._erreur(r)
        try:
            corps = r.json()
        except ValueError:
            raise ErreurResana(502, "reponse_illisible") from None
        if not isinstance(corps, dict):
            raise ErreurResana(502, "reponse_illisible")
        return corps

    async def espaces(self) -> list[Espace]:
        corps = await self._json("/espaces", delai=DELAI_ESPACES_S)
        return [
            Espace(id=_ident(e.get("id")), nom=str(e.get("nom") or e.get("slug") or e.get("id"))) for e in corps.get("espaces") or [] if isinstance(e, dict) and _ident(e.get("id"))
        ]

    async def dossiers(self, espace: str, recherche: str = "") -> list[Dossier]:
        corps = await self._json(f"/espaces/{_ident(espace)}/dossiers", {"search": recherche.strip()})
        rendu = []
        for d in corps.get("dossiers") or []:
            if isinstance(d, dict) and _ident(d.get("id")):
                parent = _ident(d.get("parent_id")) or None
                rendu.append(Dossier(id=_ident(d.get("id")), titre=str(d.get("titre") or ""), parent_id=parent, chemin=str(d.get("chemin") or d.get("titre") or "")))
        return rendu

    async def documents(self, espace: str, dossier: str, *, attendre: bool = False, suivi: Callable[[EnPreparation], Awaitable[None]] | None = None) -> list[DocumentResana]:
        """La liste **complète** d'un dossier et de ses sous-dossiers (sans `depuis` : c'est elle qui
        révèle les suppressions). Pages suivies par `suivant` ; un curseur périmé relance la lecture
        une fois depuis le début. Un grand dossier en préparation (`202`) lève `EnPreparation`, ou,
        avec `attendre`, se rappelle jusqu'à ce qu'il soit prêt (`suivi` reçoit chaque étape)."""
        relectures = 0
        fin = asyncio.get_running_loop().time() + ATTENTE_PREPARATION_MAX_S
        while True:
            try:
                return await self._documents(espace, dossier)
            except EnPreparation as e:
                if not attendre:
                    raise
                if asyncio.get_running_loop().time() >= fin:
                    raise ErreurResana(504, "preparation_trop_longue", reessayable=True) from None
                if suivi is not None:
                    await suivi(e)
                await self._dormir(min(max(e.attente, 1.0), 30.0))
            except ErreurResana as e:
                if e.code != "curseur_perime" or relectures >= RELECTURES_CURSEUR:
                    raise
                relectures += 1

    @staticmethod
    async def _dormir(secondes: float) -> None:
        await asyncio.sleep(secondes)

    async def _documents(self, espace: str, dossier: str) -> list[DocumentResana]:
        rendu: list[DocumentResana] = []
        vus: set[str] = set()
        curseur: str | None = None
        while True:
            corps = await self._json(f"/espaces/{_ident(espace)}/documents", {"dossier": _ident(dossier), "recursif": "true", "limite": LIMITE_PAGE, "curseur": curseur})
            for d in corps.get("documents") or []:
                if not isinstance(d, dict) or not _ident(d.get("id")) or _ident(d.get("id")) in vus:
                    continue
                vus.add(_ident(d.get("id")))
                nom = str(d.get("nom_fichier") or d.get("titre") or _ident(d.get("id")))
                rendu.append(
                    DocumentResana(
                        id=_ident(d.get("id")),
                        titre=str(d.get("titre") or nom),
                        nom_fichier=nom,
                        mime=str(d.get("mime") or ""),
                        dossier_id=_ident(d.get("dossier_id")) or None,
                        chemin=str(d.get("chemin") or ""),
                        url_consultation=str(d.get("url_consultation") or ""),
                        modifie_le=d.get("modifie_le") if isinstance(d.get("modifie_le"), str) else None,
                        meme_titre_que=_ident(d.get("meme_titre_que")) or None,
                        version_fichier=_ident(d.get("version_fichier")) or None,
                        taille_approx_mo=_taille(d.get("taille_approx_mo")),
                    )
                )
                if len(rendu) > DOCUMENTS_MAX:
                    raise ErreurResana(413, "trop_de_documents")
            suivant = corps.get("suivant")
            if not suivant:
                return rendu
            curseur = str(suivant)

    async def fichier(self, document: DocumentResana | str, espace: str) -> Fichier:
        """Les octets d'origine, lus en flux et plafonnés : un flux coupé ou trop long est jeté."""
        ident = document.id if isinstance(document, DocumentResana) else _ident(document)
        repli = document.nom_fichier if isinstance(document, DocumentResana) else f"document-{ident}"
        try:
            async with self._client(DELAI_S) as c, c.stream("GET", f"/documents/{ident}/fichier", params={"espace": _ident(espace)}) as r:
                if r.status_code != 200:
                    await r.aread()
                    raise self._erreur(r)
                morceaux: list[bytes] = []
                total = 0
                async for bloc in r.aiter_bytes():
                    total += len(bloc)
                    if total > OCTETS_MAX_FICHIER:
                        raise ErreurResana(413, "trop_volumineux")
                    morceaux.append(bloc)
                attendu = r.headers.get("content-length")
                if attendu and attendu.isdigit() and int(attendu) != total:
                    raise ErreurResana(502, "resana_indisponible", reessayable=True)
                nom = nom_depuis_disposition(r.headers.get("content-disposition"), repli)
                mime = (r.headers.get("content-type") or "").split(";")[0].strip()
                return Fichier(contenu=b"".join(morceaux), nom=nom, mime=mime)
        except (httpx.RemoteProtocolError, httpx.ReadError):
            raise ErreurResana(502, "resana_indisponible", reessayable=True) from None
        except httpx.TimeoutException:
            raise ErreurResana(504, "service_injoignable", reessayable=True) from None
        except httpx.HTTPError:
            raise ErreurResana(502, "service_injoignable", reessayable=True) from None


def nom_unique(nom: str, ident: str, pris: set[str]) -> str:
    """`nom` s'il est libre dans `pris` (sans tenir compte de la casse), sinon `nom (ident).ext`.
    Le nom retenu est ajouté à `pris`."""
    nom = (nom or "").replace("/", "_").replace("\\", "_").strip() or ident
    if nom.lower() in pris:
        suffixe = re.sub(r"[^\w-]", "", ident)[:40] or "bis"
        base, point, ext = nom.rpartition(".")
        nom = f"{base} ({suffixe}).{ext}" if point and base else f"{nom} ({suffixe})"
    pris.add(nom.lower())
    return nom


def noms_uniques(documents: list[DocumentResana]) -> dict[str, str]:
    """Un nom de fichier par document, unique dans la collection : deux documents Résana peuvent
    porter le même nom ; le second reçoit son identifiant avant l'extension. `{id: nom}`."""
    pris: set[str] = set()
    return {d.id: nom_unique(d.nom_fichier or d.titre or d.id, d.id, pris) for d in documents}


def par_lots(elements: list, taille: int) -> Iterator[list]:
    for i in range(0, len(elements), taille):
        yield elements[i : i + taille]
