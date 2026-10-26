"""Le client d'une instance de Fichiers (Drive de La Suite numérique), avec le jeton de la personne.

Il parle au moteur d'import comme le client du service d'export Résana : mêmes gestes
(`dossiers`, `documents`, `fichier`, `renouveler_jeton`), mêmes types (`Dossier`, `DocumentResana`,
`Fichier`) et mêmes erreurs (`ErreurResana`, avec leurs codes). Le moteur ne sait donc pas d'où
viennent les documents (docs/fichiers.md).

Ce que l'on sait de Drive (mesuré sur la bêta le 2026-10-25) :

- l'API `/api/v1.0/` accepte le jeton d'accès de la personne (vérifié par Drive auprès du SSO) :
  lister, parcourir, télécharger, avec SES droits ; l'API pour applications tierces
  (`/external_api/v1.0/`) n'autorise que les clients qu'on lui nomme, et pas le téléchargement ;
- les octets ne sont pas servis par Drive : `/media/<clé>` passe par l'ingress, qui demande à Drive
  une signature (`/api/v1.0/items/media-auth/`) puis lit le stockage objet. Depuis le cluster, on
  rejoue ces deux pas (`stockage_url`) ; sinon on suit l'adresse publique du fichier ;
- joint par son service interne, Drive veut `Host` (son nom public) et `X-Forwarded-Proto: https` ;
- chaque fichier porte un `upload_state` (relevé dans drive-migrator, l'outil de migration de La
  Suite) : `pending` (envoi pas fini), `analyzing` (antivirus en cours), `ready`, `suspicious`
  (l'antivirus l'a signalé : Drive le cache aux autres membres) et `file_too_large_to_analyze`
  (trop gros pour l'antivirus, mais servi). On n'indexe ni un fichier suspect, ni un fichier
  dont l'analyse n'est pas finie ; ce dernier est repris à la mise à jour suivante. Un fichier
  suspect sort de la liste, comme Drive le fait pour les membres : déjà indexé, il est retiré.

Le jeton n'est ni écrit ni journalisé ; la page ouverte le renouvelle (`renouveler_jeton`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from app.services.connectors.resana import DocumentResana, Dossier, ErreurResana, Fichier, nom_depuis_disposition
from app.services.fichiers_instances import Instance

DELAI_S = 60.0
OCTETS_MAX_FICHIER = 100 * 1024 * 1024
DOCUMENTS_MAX = 20000
DOSSIERS_MAX = 5000
TAILLE_PAGE = 100
#: Appels simultanés vers Drive pendant un parcours : une instance partagée, on reste sobre.
PARCOURS_PARALLELES = 4

MESSAGES = {
    "jeton_invalide": "Votre connexion n'est pas reconnue par Fichiers : reconnectez-vous à Mes collections, puis réessayez.",
    "hors_droits": "Fichiers vous refuse ce document ou ce dossier.",
    "introuvable": "Ce dossier ou ce document est introuvable dans Fichiers (supprimé, ou plus partagé avec vous).",
    "trop_de_documents": f"Ce dossier contient trop de documents ({DOCUMENTS_MAX} au plus) : choisissez un sous-dossier.",
    "trop_de_dossiers": f"Trop de dossiers à parcourir ({DOSSIERS_MAX} au plus) : choisissez un sous-dossier.",
    "trop_volumineux": "Un document dépasse la taille admise (100 Mo).",
    "service_injoignable": "Fichiers ne répond pas pour le moment. Réessayez dans un instant.",
    "reponse_illisible": "Fichiers a répondu de façon inattendue.",
    "fichier_vide": "Fichiers a renvoyé ce fichier vide : le téléchargement n'a rien rapporté.",
    "document_vide": "Ce document est vide dans Fichiers.",
    "en_cours_d_envoi": "Ce document est encore en cours d'envoi dans Fichiers.",
    "en_cours_d_analyse": "Fichiers analyse encore ce document (antivirus) : il sera repris à la prochaine mise à jour.",
    "fichier_suspect": "Fichiers a signalé ce document comme suspect (antivirus) : il n'est pas indexé.",
}

#: `upload_state` de Drive → l'erreur qui empêche de lire le fichier. Absent ou inconnu : on lit.
ETATS_BLOQUANTS: dict[str, tuple[int, str, bool]] = {
    "pending": (409, "en_cours_d_envoi", True),
    "analyzing": (409, "en_cours_d_analyse", True),
    "suspicious": (422, "fichier_suspect", False),
}


def erreur(statut: int, code: str, *, reessayable: bool = False) -> ErreurResana:
    """Une erreur du moteur, dite au nom de Fichiers."""
    e = ErreurResana(statut, code, MESSAGES.get(code, ""), reessayable=reessayable)
    e.message = MESSAGES.get(code) or e.message
    return e


class ClientFichiers:
    """Le client d'une instance, pour une personne. `espace` (vocabulaire du moteur) est
    l'identifiant de l'instance : un client ne sert qu'une instance."""

    def __init__(self, instance: Instance, jeton: str, *, transport: httpx.AsyncBaseTransport | None = None):
        if not jeton:
            raise erreur(401, "jeton_invalide")
        self.instance = instance
        self._jeton = jeton
        self._transport = transport
        #: Ce que le dernier parcours a vu : les dossiers (pour l'arbre et les exclusions) et
        #: l'adresse `/media/…` de chaque fichier (pour le télécharger sans le relire).
        self._dossiers: dict[str, Dossier] = {}
        self._medias: dict[str, str] = {}
        self._tailles: dict[str, int] = {}
        self._etats: dict[str, str] = {}

    # --- Le jeton -------------------------------------------------------------------------

    def renouveler_jeton(self, jeton: str) -> bool:
        jeton = (jeton or "").strip()
        if not jeton or jeton == self._jeton:
            return False
        self._jeton = jeton
        return True

    # --- HTTP -----------------------------------------------------------------------------

    def _entetes(self) -> dict:
        e = {"Authorization": f"Bearer {self._jeton}", "Accept": "application/json"}
        if self.instance.hote_public and urlparse(self.instance.url).hostname != self.instance.hote_public:
            e["Host"] = self.instance.hote_public
            e["X-Forwarded-Proto"] = "https"
        return e

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=f"{self.instance.url}/api/v1.0", timeout=DELAI_S, transport=self._transport, follow_redirects=False)

    @staticmethod
    def _http(r: httpx.Response) -> ErreurResana:
        if r.status_code == 401:
            return erreur(401, "jeton_invalide")
        if r.status_code == 403:
            return erreur(403, "hors_droits")
        if r.status_code == 404:
            return erreur(404, "introuvable")
        if r.status_code >= 500 or r.status_code == 429:
            return erreur(502, "service_injoignable", reessayable=True)
        return erreur(502, "reponse_illisible")

    async def _get(self, chemin: str, params: dict | None = None) -> dict:
        try:
            async with self._client() as c:
                r = await c.get(chemin, params=params, headers=self._entetes())
        except httpx.HTTPError:
            raise erreur(504, "service_injoignable", reessayable=True) from None
        if r.status_code != 200:
            raise self._http(r)
        try:
            return r.json()
        except ValueError:
            raise erreur(502, "reponse_illisible") from None

    async def _pages(self, chemin: str, params: dict) -> list[dict]:
        rendu: list[dict] = []
        page = 1
        while True:
            corps = await self._get(chemin, {**params, "page": page, "page_size": TAILLE_PAGE})
            resultats = corps.get("results") if isinstance(corps, dict) else None
            if not isinstance(resultats, list):
                raise erreur(502, "reponse_illisible")
            rendu.extend(r for r in resultats if isinstance(r, dict) and r.get("id"))
            if not corps.get("next") or not resultats:
                return rendu
            page += 1

    # --- Parcourir ------------------------------------------------------------------------

    def dossiers_vus(self) -> list[Dossier]:
        """Les dossiers rencontrés par le dernier parcours (`documents`, `dossiers`)."""
        return list(self._dossiers.values())

    async def racines(self) -> list[dict]:
        """Les dossiers du premier niveau : l'espace de la personne et ce qu'on lui a partagé."""
        return await self._pages("/items/", {"type": "folder"})

    async def enfants(self, dossier: str, *, type_: str | None = None) -> list[dict]:
        return await self._pages(f"/items/{dossier}/children/", {"type": type_} if type_ else {})

    async def element(self, ident: str) -> dict:
        return await self._get(f"/items/{ident}/")

    async def dossiers(self, espace: str = "", recherche: str = "") -> list[Dossier]:
        """Tous les dossiers que la personne voit, avec leur parent et leur chemin : de quoi
        dessiner l'arbre à cocher et appliquer les exclusions."""
        file: list[tuple[dict, str | None, str]] = [(r, None, "") for r in await self.racines()]
        vus: dict[str, Dossier] = {}
        while file:
            lot, file = file[:PARCOURS_PARALLELES], file[PARCOURS_PARALLELES:]
            for brut, parent, chemin_parent in lot:
                titre = str(brut.get("title") or brut["id"])
                chemin = f"{chemin_parent}/{titre}" if chemin_parent else titre
                vus[brut["id"]] = Dossier(id=brut["id"], titre=titre, parent_id=parent, chemin=chemin)
                if len(vus) > DOSSIERS_MAX:
                    raise erreur(413, "trop_de_dossiers")
            sous = await asyncio.gather(*(self.enfants(b["id"], type_="folder") if b.get("numchild_folder", 1) != 0 else _rien() for b, _, _ in lot))
            for (brut, _, _), enfants in zip(lot, sous, strict=True):
                file.extend((e, brut["id"], vus[brut["id"]].chemin) for e in enfants if e["id"] not in vus)
        self._dossiers = dict(vus)
        rendu = list(vus.values())
        if recherche:
            mots = recherche.lower().split()
            rendu = [d for d in rendu if all(m in d.chemin.lower() for m in mots)]
        return rendu

    async def documents(self, espace: str, dossier: str, *, attendre: bool = False, suivi: Callable[..., Awaitable[None]] | None = None) -> list[DocumentResana]:
        """Tous les fichiers du dossier, sous-dossiers compris (`attendre` et `suivi` : sans objet
        ici, Drive répond aussitôt)."""
        racine = self._dossiers.get(dossier)
        if racine is None:
            brut = await self.element(dossier)
            if str(brut.get("type")).lower() != "folder":
                raise erreur(400, "introuvable")
            racine = Dossier(id=dossier, titre=str(brut.get("title") or dossier), parent_id=None, chemin=str(brut.get("title") or dossier))
            self._dossiers[dossier] = racine
        rendu: list[DocumentResana] = []
        file = [racine]
        while file:
            lot, file = file[:PARCOURS_PARALLELES], file[PARCOURS_PARALLELES:]
            contenus = await asyncio.gather(*(self.enfants(d.id) for d in lot))
            for d, enfants in zip(lot, contenus, strict=True):
                for e in enfants:
                    if str(e.get("type")).lower() == "folder":
                        sous = Dossier(id=e["id"], titre=str(e.get("title") or e["id"]), parent_id=d.id, chemin=f"{d.chemin}/{e.get('title') or e['id']}")
                        self._dossiers[sous.id] = sous
                        file.append(sous)
                        continue
                    if e.get("upload_state") == "suspicious":
                        continue  # caché aux membres par Drive : hors de la liste, donc hors de l'index
                    rendu.append(self._document(e, d))
                    if len(rendu) > DOCUMENTS_MAX:
                        raise erreur(413, "trop_de_documents")
        return rendu

    def _document(self, e: dict, dossier: Dossier) -> DocumentResana:
        ident = str(e["id"])
        if e.get("url"):
            self._medias[ident] = str(e["url"])
        taille = e.get("size")
        self._tailles[ident] = int(taille) if isinstance(taille, int) else -1
        self._etats[ident] = str(e.get("upload_state") or "")
        return DocumentResana(
            id=ident,
            titre=str(e.get("title") or e.get("filename") or ident),
            nom_fichier=str(e.get("filename") or e.get("title") or ident),
            mime=str(e.get("mimetype") or ""),
            dossier_id=dossier.id,
            chemin=dossier.chemin,
            url_consultation=self.instance.url_consultation(ident),
            modifie_le=str(e.get("updated_at") or "") or None,
            version_fichier=None,
            taille_approx_mo=round(taille / (1024 * 1024), 1) if isinstance(taille, int) else None,
        )

    # --- Télécharger ----------------------------------------------------------------------

    async def fichier(self, document: DocumentResana | str, espace: str = "") -> Fichier:
        ident = document.id if isinstance(document, DocumentResana) else str(document)
        repli = document.nom_fichier if isinstance(document, DocumentResana) else f"document-{ident}"
        media = self._medias.get(ident)
        if not media or ident not in self._etats:
            brut = await self.element(ident)
            self._etats[ident] = str(brut.get("upload_state") or "")
            media = str(brut.get("url") or "")
        _controler_etat(self._etats[ident])
        if self._tailles.get(ident) == 0:
            raise erreur(422, "document_vide")
        if not media:
            raise erreur(404, "introuvable")
        chemin = urlparse(media).path
        if self.instance.stockage_url and chemin.startswith("/media/"):
            entetes = await self._signature(chemin)
            url = f"{self.instance.stockage_url}/{chemin[len('/media/') :]}"
        else:
            entetes, url = self._entetes(), media
        contenu, nom, mime = await self._lire(url, entetes, repli)
        if not contenu:
            # Fichier annoncé non vide, reçu vide : un raté à retenter, pas un document.
            raise erreur(503, "fichier_vide", reessayable=True)
        return Fichier(contenu=contenu, nom=nom, mime=mime)

    async def _signature(self, chemin: str) -> dict:
        """La signature du stockage objet que Drive rend à l'ingress pour ce fichier, s'il est lisible
        par la personne (sinon 403)."""
        try:
            async with self._client() as c:
                r = await c.get("/items/media-auth/", headers={**self._entetes(), "X-Original-URL": chemin})
        except httpx.HTTPError:
            raise erreur(504, "service_injoignable", reessayable=True) from None
        if r.status_code != 200:
            raise self._http(r)
        entetes = {k: r.headers[k] for k in ("authorization", "x-amz-date", "x-amz-content-sha256") if k in r.headers}
        if "authorization" not in entetes:
            raise erreur(502, "reponse_illisible")
        return entetes

    async def _lire(self, url: str, entetes: dict, repli: str) -> tuple[bytes, str, str]:
        try:
            async with (
                httpx.AsyncClient(timeout=DELAI_S, transport=self._transport, follow_redirects=True) as c,
                c.stream("GET", url, headers=entetes) as r,
            ):
                if r.status_code != 200:
                    await r.aread()
                    raise self._http(r)
                morceaux: list[bytes] = []
                total = 0
                async for bloc in r.aiter_bytes():
                    total += len(bloc)
                    if total > OCTETS_MAX_FICHIER:
                        raise erreur(413, "trop_volumineux")
                    morceaux.append(bloc)
                attendu = r.headers.get("content-length")
                if attendu and attendu.isdigit() and int(attendu) != total:
                    raise erreur(502, "service_injoignable", reessayable=True)
                nom = nom_depuis_disposition(r.headers.get("content-disposition"), repli)
                mime = (r.headers.get("content-type") or "").split(";")[0].strip()
                return b"".join(morceaux), nom, mime
        except httpx.TimeoutException:
            raise erreur(504, "service_injoignable", reessayable=True) from None
        except httpx.HTTPError:
            raise erreur(502, "service_injoignable", reessayable=True) from None


def _controler_etat(etat: str) -> None:
    """Refuse un fichier que Drive n'a pas fini de recevoir ou d'analyser, ou qu'il juge suspect."""
    bloquant = ETATS_BLOQUANTS.get(etat)
    if bloquant:
        statut, code, reessayable = bloquant
        raise erreur(statut, code, reessayable=reessayable)


async def _rien() -> list:
    return []
