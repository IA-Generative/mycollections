"""Les sites d'origine des documents d'une collection (`collections.source_url`, une adresse par
ligne) et ce qu'on en tire pour MirAI Assistant pour navigateur : un motif de site déclaré, posé
sans écraser ceux saisis à la main.

- Cas général : la personne donne, à la création ou dans les réglages, le ou les sites d'où
  viennent ses documents (facultatif).
- Résana, dépôt par adresse : l'adresse est connue du service, qui la déduit (préfixe commun des
  documents Résana, hôte d'un fichier téléchargé) et la propose au plug-in.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.services import sites

URLS_MAX = 10
LONGUEUR_MAX = 300


class URLInvalide(ValueError):
    """Une adresse refusée, avec la raison en mots simples."""


def lignes_vers_urls(texte: str | list[str] | None) -> list[str]:
    """Les adresses d'un champ libre (une par ligne ou séparées par des virgules), sans vide ni doublon."""
    brut = texte if isinstance(texte, list) else (texte or "").replace(",", "\n").split("\n")
    vus: list[str] = []
    for u in (x.strip() for x in brut):
        if u and u not in vus:
            vus.append(u)
    return vus


def valider_urls(texte: str | list[str] | None) -> str:
    """Le champ `source_url` normalisé (une adresse https par ligne), ou `URLInvalide`."""
    urls = lignes_vers_urls(texte)
    if len(urls) > URLS_MAX:
        raise URLInvalide(f"{URLS_MAX} adresses au plus.")
    for u in urls:
        if len(u) > LONGUEUR_MAX:
            raise URLInvalide(f"Une adresse dépasse {LONGUEUR_MAX} caractères.")
        p = urlsplit(u)
        if p.scheme != "https" or not p.netloc or any(c.isspace() for c in u):
            raise URLInvalide(f"« {u[:60]} » n'est pas une adresse https valide (par exemple https://www.fake-domain.name/guides).")
    return "\n".join(urls)


def motif_de(url: str) -> str:
    """Le motif de site déclaré qui couvre l'hôte d'une adresse : `https://<hôte>/*` ; '' si inutilisable."""
    p = urlsplit((url or "").strip())
    if p.scheme != "https" or not p.hostname:
        return ""
    return f"https://{p.hostname.lower()}/*"


def prefixe_commun(urls: list[str]) -> str:
    """Le motif commun à des adresses de consultation (`https://<hôte>/<chemin commun>/*`) : même
    hôte obligatoire, chemin coupé au dernier `/` commun ; '' sans adresse https ou avec plusieurs hôtes."""
    propres = [urlsplit(u) for u in urls if isinstance(u, str) and u.startswith("https://")]
    hotes = {p.hostname.lower() for p in propres if p.hostname}
    if len(hotes) != 1:
        return ""
    hote = next(iter(hotes))
    chemins = [p.path.rsplit("/", 1)[0] + "/" for p in propres]
    segments = [c.split("/") for c in chemins]
    commun: list[str] = []
    for morceaux in zip(*segments, strict=False):
        if len(set(morceaux)) != 1:
            break
        commun.append(morceaux[0])
    chemin = "/".join(commun)
    if not chemin.endswith("/"):
        chemin += "/"
    return f"https://{hote}{chemin}*"


async def ajouter_sites(collection: str, motifs: list[str]) -> list[str]:
    """Ajoute des motifs aux sites déclarés de la collection, sans toucher à ceux déjà là ; sans
    effet si tout y est déjà, ou si le plafond serait dépassé. Rend la liste finale."""
    actuels = await sites.lire("collection", collection)
    voulus = list(actuels)
    for m in motifs:
        try:
            m = sites.valider_motif(m)
        except sites.MotifInvalide:
            continue
        if m not in voulus and len(voulus) < sites.MOTIFS_MAX:
            voulus.append(m)
    if voulus == actuels:
        return actuels
    return await sites.remplacer("collection", collection, voulus)
