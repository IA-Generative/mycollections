"""Un drapeau à `false` : la route répond 404 — et chaque routeur du chantier des assistants est
gardé par son drapeau dès le lot 0, même vide. Chaque lot qui ajoute une route l'ajoute à ROUTES."""

from __future__ import annotations

import pytest

from app.routers import assistants, assistants_doublure, embed, entraide, openai_compat

#: (drapeau, méthode, adresse) — une ligne par route nouvelle, ajoutée par le lot qui la crée.
ROUTES = [
    ("assistants", "get", "/api/assistants"),
    ("assistants", "get", "/api/assistants/x-y-z"),
    ("assistants", "put", "/api/assistants/x-y-z"),
    ("assistants", "post", "/api/assistants/x-y-z/publier"),
    ("assistants", "get", "/api/assistants/x-y-z/versions"),
]


@pytest.mark.parametrize("drapeau, methode, url", ROUTES)
def test_drapeau_faux_404(client, en_tant_que, capacites, drapeau, methode, url):
    from tests.conftest import personne

    en_tant_que(personne(1))
    capacites(**{drapeau: False})
    r = client.request(methode.upper(), url, json={} if methode in ("put", "post") else None)
    assert r.status_code == 404 and "Fonction désactivée" in r.text


@pytest.mark.parametrize(
    "routeur, drapeau",
    [(assistants.router, "assistants"), (assistants_doublure.router, "assistants"), (openai_compat.router, "assistants"), (entraide.router, "entraide")],
)
def test_chaque_routeur_est_garde_par_son_drapeau(routeur, drapeau):
    assert {getattr(d.dependency, "capacite", None) for d in routeur.dependencies} == {drapeau}


def test_la_fenetre_est_montee_sans_jeton_ni_drapeau():
    """Un script se charge sans en-tête : le lot C décidera de son drapeau et de son CORS."""
    assert embed.router.dependencies == []
