"""Un morceau relu dans OpenRAG, débarrassé de son habillage technique.

OpenRAG range un morceau ainsi :
`[CONTEXT] résumé  * filename: x.md  [CHUNK_START] texte [CHUNK_END]`.
Un lecteur n'a pas à voir ces balises. Même découpe que `decouperMorceau` côté
frontend (utils/extrait.ts) : toute nouvelle vue d'un morceau passe par l'une des deux.
"""

from __future__ import annotations

import re

_FICHIER = re.compile(r"^[ \t]*\*[ \t]*filename[ \t]*:[ \t]*(.*)$", flags=re.I | re.M)


def decouper_morceau(texte: str | None) -> tuple[str, str, str]:
    """Rend (contexte, fichier, corps). Sans balise, le texte ressort tel quel."""
    texte = texte or ""
    debut = texte.find("[CHUNK_START]")
    if debut < 0:
        return "", "", re.sub(r"\[CHUNK_END\]\s*$", "", texte).strip()
    apres = texte[debut + len("[CHUNK_START]"):]
    fin = apres.rfind("[CHUNK_END]")
    corps = (apres if fin < 0 else apres[:fin]).strip()
    entete = re.sub(r"^\s*\[CONTEXT\]", "", texte[:debut])
    fichier = ""
    m = _FICHIER.search(entete)
    if m:
        fichier = m.group(1).strip()
        entete = entete[:m.start()] + entete[m.end():]
    return entete.strip(), fichier, corps
