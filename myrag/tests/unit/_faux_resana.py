"""Un faux service d'export Résana (contrat v1, owuitools-resana `docs/export-v1.md`).

Aucun appel réseau : il se branche par `httpx.MockTransport`. Les titres sont fictifs ; le jeton
de la personne est un témoin qu'on cherche ensuite partout où il ne doit pas être.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

SECRET = "secret-de-test-resana"
TEMOIN = "SESSION-TEMOIN-9191"
BASE = "http://resana-export.fake-domain.name:9101"


@dataclass
class DocFaux:
    id: str
    titre: str
    nom_fichier: str
    contenu: bytes
    dossier_id: str = "d-1"
    chemin: str = "Dossier fictif"
    mime: str = "text/markdown"
    refus: tuple[int, str] | None = None  # (statut, code) rendu par /fichier

    def ligne(self) -> dict:
        return {
            "id": self.id,
            "titre": self.titre,
            "nom_fichier": self.nom_fichier,
            "mime": self.mime,
            "taille": None,
            "taille_approx_mo": round(len(self.contenu) / 1_000_000, 2),
            "modifie_le": "2026-10-01T08:00:00Z",
            "version_fichier": f"v-{self.id}-{len(self.contenu)}",
            "dossier_id": self.dossier_id,
            "chemin": self.chemin,
            "url_consultation": f"https://resana.fake-domain.name/espace-fictif/ged/{self.id}",
            "copie_de": None,
            "meme_titre_que": None,
        }


@dataclass
class FauxResana:
    espaces: list[dict] = field(default_factory=lambda: [{"id": "e-2", "slug": "zeta", "nom": "Zêta fictif"}, {"id": "e-1", "slug": "alpha", "nom": "Alpha fictif"}])
    dossiers: list[dict] = field(default_factory=lambda: [{"id": "d-1", "titre": "Notes", "parent_id": None, "chemin": "Notes"}])
    documents: list[DocFaux] = field(default_factory=list)
    page: int = 2
    #: Les réponses forcées : {chemin: (statut, corps)} — corps dict (JSON) ou bytes.
    pannes: dict[str, tuple[int, object]] = field(default_factory=dict)
    curseurs_perimes: int = 0
    requetes: list[httpx.Request] = field(default_factory=list)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._repondre)

    @staticmethod
    def _erreur(statut: int, code: str, **extra) -> httpx.Response:
        return httpx.Response(statut, json={"code": code, "message": f"message du service : {code}", "reessayable": statut >= 500, **extra})

    def _repondre(self, req: httpx.Request) -> httpx.Response:
        self.requetes.append(req)
        if req.headers.get("x-internal-token") != SECRET:
            return self._erreur(401, "appelant_inconnu")
        if not (req.headers.get("authorization") or "").startswith("Bearer "):
            return self._erreur(401, "jeton_invalide")
        chemin = req.url.path.removeprefix("/export/v1")
        for prefixe, (statut, corps) in self.pannes.items():
            if chemin.startswith(prefixe):
                return httpx.Response(statut, json=corps) if isinstance(corps, dict) else httpx.Response(statut, content=corps)
        if chemin == "/espaces":
            return httpx.Response(200, json={"espaces": self.espaces})
        if chemin.endswith("/dossiers"):
            return httpx.Response(200, json={"dossiers": self.dossiers})
        if chemin.endswith("/documents"):
            if not req.url.params.get("dossier"):
                return self._erreur(400, "dossier_requis")
            curseur = req.url.params.get("curseur")
            if curseur and self.curseurs_perimes > 0:
                self.curseurs_perimes -= 1
                return self._erreur(410, "curseur_perime")
            debut = int(curseur or 0)
            tranche = self.documents[debut : debut + self.page]
            suivant = str(debut + self.page) if debut + self.page < len(self.documents) else None
            return httpx.Response(200, json={"documents": [d.ligne() for d in tranche], "suivant": suivant, "total": len(self.documents), "depuis_applique": False})
        if chemin.startswith("/documents/") and chemin.endswith("/fichier"):
            if not req.url.params.get("espace"):
                return self._erreur(400, "espace_requis")
            ident = chemin.split("/")[2]
            doc = next((d for d in self.documents if d.id == ident), None)
            if doc is None:
                return self._erreur(404, "introuvable")
            if doc.refus:
                return self._erreur(*doc.refus)
            return httpx.Response(
                200,
                content=doc.contenu,
                headers={"content-type": doc.mime, "content-disposition": f"attachment; filename*=UTF-8''{quote(doc.nom_fichier)}"},
            )
        return self._erreur(404, "introuvable")
