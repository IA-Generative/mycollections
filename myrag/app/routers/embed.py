"""La fenêtre de recherche à insérer dans une application (lot C) : le script `fenetre.js` et ce
qu'il appelle. Routeur vide au lot 0, déjà monté SANS jeton (un script se charge sans en-tête) :
le lot C le remplit, avec son propre CORS limité aux origines configurées."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["fenetre"])
