"""Le guide « Soyez acteurs vous-mêmes » : cinq pages, chacune finie par le geste et un exemple."""

from app.routers.guide import pages
from tests.conftest import personne

ATTENDUES = ["dire-ce-qui-manque", "rassembler-cinq-collegues-et-un-garant", "amorcer-depuis-ce-qui-existe",
             "verifier-avant-de-publier", "entretenir"]


def test_cinq_pages_dans_l_ordre():
    assert [p["slug"] for p in pages()] == ATTENDUES


def test_chaque_page_finit_par_le_geste_et_un_exemple():
    for p in pages():
        assert "## Le geste dans l'outil" in p["markdown"], p["slug"]
        assert "## Exemple" in p["markdown"], p["slug"]
        assert p["markdown"].index("## Le geste dans l'outil") < p["markdown"].index("## Exemple")


def test_les_exemples_citent_les_six_premiers_jeux():
    texte = "\n".join(p["markdown"] for p in pages())
    for jeu in ("NATINF", "SSMSI", "CESEDA", "élus", "SDIS", "BAAC"):
        assert jeu in texte, jeu


def test_les_routes_servent_le_guide(client, en_tant_que):
    en_tant_que(personne(1))
    liste = client.get("/api/guide").json()
    assert liste["titre"] == "Soyez acteurs vous-mêmes" and len(liste["pages"]) == 5 and "markdown" not in liste["pages"][0]
    page = client.get("/api/guide/entretenir").json()
    assert page["titre"] == "Entretenir" and page["markdown"].startswith("# Entretenir")
    assert client.get("/api/guide/inconnue").status_code == 404


def test_le_guide_est_une_amorce_ouverte_aux_propositions(client, en_tant_que):
    en_tant_que(personne(1))
    amorce = next(a for a in client.get("/api/amorces").json()["amorces"] if a["id"] == "guide")
    assert amorce["collection"] == "guide-soyez-acteurs" and amorce["nb_questions"] == 20
