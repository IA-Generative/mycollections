"""Les sites déclarés : sur quelles pages l'extension du navigateur propose la bulle « + IA ».

Une collection ou un assistant porte une liste de motifs d'adresse. L'extension télécharge les
motifs que la personne peut lire (`GET /api/v1/sites`) et les compare elle-même à l'adresse de
la page : aucune adresse visitée n'est envoyée au serveur.

Un motif suit la règle des *match patterns* d'extension, restreinte : `https://` seulement, un
hôte explicite (éventuellement précédé de `*.`), un chemin qui commence par `/` et peut contenir
`*`. Le chemin est comparé avec la query de l'adresse ; le fragment (`#…`) ne l'est jamais.
`validation` et `correspond` sont pures : le serveur et l'extension appliquent la même règle.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from sqlalchemy import delete, select

from app.database import async_session
from app.models.db import SiteDeclare

TYPES_CIBLE = ("collection", "assistant")
MOTIFS_MAX = 20
LONGUEUR_MAX = 300
TTL_S = 3600

_LIBELLE = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOTE = re.compile(rf"^(?:\*\.)?{_LIBELLE}(?:\.{_LIBELLE})+$")


class MotifInvalide(ValueError):
    """Un motif refusé, avec la raison en mots simples."""


def valider_motif(brut: str) -> str:
    """Le motif normalisé (hôte en minuscules), ou `MotifInvalide` avec la raison."""
    motif = (brut or "").strip()
    if not motif:
        raise MotifInvalide("Le motif est vide.")
    if len(motif) > LONGUEUR_MAX:
        raise MotifInvalide(f"Le motif dépasse {LONGUEUR_MAX} caractères.")
    if any(c.isspace() for c in motif):
        raise MotifInvalide("Le motif ne doit pas contenir d'espace.")
    if not motif.lower().startswith("https://"):
        raise MotifInvalide("Le motif doit commencer par https://.")
    reste = motif[len("https://") :]
    hote, barre, chemin = reste.partition("/")
    if not barre:
        raise MotifInvalide("Le motif doit avoir un chemin, au moins « / » (par exemple https://www.fake-domain.name/*).")
    if "#" in chemin:
        raise MotifInvalide("Le fragment (#…) n'est jamais comparé : retirez-le du motif.")
    hote = hote.lower()
    if ":" in hote or "@" in hote:
        raise MotifInvalide("L'hôte ne doit porter ni port ni identifiant.")
    if hote.startswith("*.") and hote.count(".") < 2:
        raise MotifInvalide("« *. » doit précéder au moins deux niveaux de nom, par exemple *.fake-domain.name.")
    if not _HOTE.match(hote):
        raise MotifInvalide("L'hôte doit être explicite, par exemple www.fake-domain.name ou *.fake-domain.name.")
    return f"https://{hote}/{chemin}"


def valider_motifs(bruts: list[str]) -> list[str]:
    """Les motifs normalisés, dédoublonnés dans l'ordre. `MotifInvalide` au premier refus."""
    vus: list[str] = []
    for i, brut in enumerate(bruts, start=1):
        try:
            m = valider_motif(brut)
        except MotifInvalide as e:
            raise MotifInvalide(f"Motif {i} : {e}") from None
        if m not in vus:
            vus.append(m)
    if len(vus) > MOTIFS_MAX:
        raise MotifInvalide(f"{MOTIFS_MAX} motifs au plus.")
    return vus


def _glob(chemin: str) -> re.Pattern[str]:
    return re.compile("^" + ".*".join(re.escape(p) for p in chemin.split("*")) + "$", re.DOTALL)


def correspond(url: str, motif: str) -> bool:
    """L'adresse correspond-elle au motif ? Schéma exact, hôte exact ou sous-domaine pour `*.`,
    chemin et query comparés au chemin du motif ; le fragment est ignoré."""
    try:
        u = urlsplit(url)
        m = urlsplit(motif)
    except ValueError:
        return False
    if u.scheme != "https" or m.scheme != "https":
        return False
    hote, hote_motif = (u.hostname or "").lower(), (m.netloc or "").lower()
    if hote_motif.startswith("*."):
        base = hote_motif[2:]
        if hote != base and not hote.endswith("." + base):
            return False
    elif hote != hote_motif:
        return False
    chemin = (u.path or "/") + (f"?{u.query}" if u.query else "")
    chemin_motif = motif.split(hote_motif, 1)[1] if hote_motif else "/"
    return bool(_glob(chemin_motif).match(chemin))


# ─── Magasin ─────────────────────────────────────────────────────────────────────────────────


async def lire(cible_type: str, cible_id: str) -> list[str]:
    async with async_session() as session:
        lignes = await session.execute(
            select(SiteDeclare.motif).where(SiteDeclare.cible_type == cible_type, SiteDeclare.cible_id == cible_id).order_by(SiteDeclare.cree_le, SiteDeclare.motif)
        )
        return [m for (m,) in lignes]


async def remplacer(cible_type: str, cible_id: str, motifs: list[str]) -> list[str]:
    """Remplace les motifs de la cible par ceux-ci (déjà validés), en une transaction."""
    async with async_session() as session:
        await session.execute(delete(SiteDeclare).where(SiteDeclare.cible_type == cible_type, SiteDeclare.cible_id == cible_id))
        for m in motifs:
            session.add(SiteDeclare(cible_type=cible_type, cible_id=cible_id, motif=m))
        await session.commit()
    return await lire(cible_type, cible_id)


async def supprimer_cible(cible_type: str, cible_id: str) -> int:
    async with async_session() as session:
        r = await session.execute(delete(SiteDeclare).where(SiteDeclare.cible_type == cible_type, SiteDeclare.cible_id == cible_id))
        await session.commit()
        return int(r.rowcount or 0)


async def tous() -> list[tuple[str, str, str]]:
    """Toutes les déclarations : (type, identifiant, motif)."""
    async with async_session() as session:
        lignes = await session.execute(select(SiteDeclare.cible_type, SiteDeclare.cible_id, SiteDeclare.motif).order_by(SiteDeclare.motif))
        return [(t, i, m) for t, i, m in lignes]
