"""Un faux Drive (La Suite numérique), pour les tests de la source Fichiers : l'API `/api/v1.0/`
(lister, parcourir, `media-auth`) et le stockage objet derrière `/media/`, sur un
`httpx.MockTransport`. Données fictives ; aucun appel réseau."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote, urlparse

import httpx

JETON = "jeton-fictif-de-la-personne"
API = "http://drive-interne.test"
HOTE = "fichiers.fake-domain.name"
STOCKAGE = "https://stockage.fake-domain.name/seau"
SIGNATURE = "AWS4-HMAC-SHA256 Credential=fictif"


@dataclass
class Element:
    id: str
    titre: str
    type: str = "file"  # file | folder
    parent: str | None = None
    contenu: bytes = b""
    modifie_le: str = "2026-10-01T10:00:00Z"
    taille: int | None = None
    #: Le stockage rend ce contenu à la place (un fichier annoncé non vide, reçu vide…).
    recu: bytes | None = None
    #: `upload_state` de Drive : pending, analyzing, ready, suspicious, file_too_large_to_analyze.
    etat: str = "ready"

    def vers_json(self, faux: FauxDrive) -> dict:
        d = {"id": self.id, "title": self.titre, "type": self.type, "updated_at": self.modifie_le, "upload_state": self.etat}
        if self.type == "folder":
            enfants = [e for e in faux.elements.values() if e.parent == self.id]
            d.update(numchild=len(enfants), numchild_folder=sum(1 for e in enfants if e.type == "folder"))
        else:
            d.update(
                filename=self.titre,
                mimetype="text/markdown",
                size=len(self.contenu) if self.taille is None else self.taille,
                url=f"https://{HOTE}/media/item/{self.id}/{quote(self.titre)}",
            )
        return d


@dataclass
class FauxDrive:
    elements: dict[str, Element] = field(default_factory=dict)
    jeton: str = JETON
    requetes: list[str] = field(default_factory=list)
    #: Codes HTTP imposés à une adresse (chemin exact) : {chemin: statut}.
    pannes: dict[str, int] = field(default_factory=dict)

    def ajouter(self, *elements: Element) -> FauxDrive:
        for e in elements:
            self.elements[e.id] = e
        return self

    def telechargements(self) -> list[str]:
        return [r for r in self.requetes if r.startswith(STOCKAGE) or "/media/" in r]

    def _page(self, liste: list[Element], params: dict) -> httpx.Response:
        type_ = (params.get("type") or [None])[0]
        if type_:
            liste = [e for e in liste if e.type == type_]
        page = int((params.get("page") or ["1"])[0])
        taille = int((params.get("page_size") or ["100"])[0])
        morceau = liste[(page - 1) * taille : page * taille]
        suivant = "x" if page * taille < len(liste) else None
        return httpx.Response(200, json={"count": len(liste), "next": suivant, "previous": None, "results": [e.vers_json(self) for e in morceau]})

    def transport(self) -> httpx.MockTransport:
        def repondre(req: httpx.Request) -> httpx.Response:
            url = str(req.url)
            self.requetes.append(url)
            chemin = req.url.path
            if chemin in self.pannes:
                return httpx.Response(self.pannes[chemin], json={"detail": "panne fictive"})
            if url.startswith(STOCKAGE):
                if req.headers.get("authorization") != SIGNATURE:
                    return httpx.Response(403, text="SignatureDoesNotMatch")
                ident = chemin.split("/item/", 1)[1].split("/", 1)[0]
                e = self.elements.get(ident)
                if e is None:
                    return httpx.Response(404)
                return httpx.Response(200, content=e.contenu if e.recu is None else e.recu, headers={"content-type": "text/markdown"})
            if req.headers.get("authorization") != f"Bearer {self.jeton}":
                return httpx.Response(401, json={"detail": "jeton refusé"})
            if url.startswith(f"https://{HOTE}/media/"):
                ident = chemin.split("/item/", 1)[1].split("/", 1)[0]
                e = self.elements[ident]
                return httpx.Response(200, content=e.contenu if e.recu is None else e.recu)
            params = parse_qs(urlparse(url).query)
            if chemin == "/api/v1.0/items/":
                return self._page([e for e in self.elements.values() if e.parent is None], params)
            if chemin == "/api/v1.0/items/media-auth/":
                original = req.headers.get("x-original-url") or ""
                if not original.startswith("/media/item/"):
                    return httpx.Response(403)
                return httpx.Response(200, json="authorized", headers={"Authorization": SIGNATURE, "X-Amz-Date": "20261025T000000Z", "X-Amz-Content-SHA256": "e3b0"})
            if chemin.startswith("/api/v1.0/items/"):
                reste = chemin[len("/api/v1.0/items/") :].strip("/").split("/")
                e = self.elements.get(reste[0])
                if e is None:
                    return httpx.Response(404, json={"detail": "introuvable"})
                if len(reste) == 2 and reste[1] == "children":
                    return self._page([x for x in self.elements.values() if x.parent == e.id], params)
                return httpx.Response(200, json=e.vers_json(self))
            return httpx.Response(404, content=json.dumps({"detail": "route inconnue"}))

        return httpx.MockTransport(repondre)
