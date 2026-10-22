"""Le connecteur du référentiel d'éligibilité, contre un transport HTTP simulé : mots significatifs,
au plus trois appels par table, classement, relais, passages, pannes, et rien d'identifiant envoyé."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.harnais.connecteurs import eligibilite
from app.harnais.connecteurs.eligibilite import ConnecteurEligibilite, empreinte_ligne, mots_significatifs, reference_courte
from app.harnais.contrat import Appelant, Etape, Passage

pytestmark = pytest.mark.asyncio

URL = "http://referentiel.fake-domain.name"
APPELANT = Appelant(sub="personne-1", groupes=["/g/equipe"])

TITRES = [
    {"id": 1, "intitule": "Carte de séjour pluriannuelle salarié", "pieces": "Contrat de travail, passeport", "article": "L. 421-1"},
    {"id": 2, "intitule": "Carte de résident", "pieces": "Justificatif de domicile, passeport", "article": "L. 423-1"},
]


class Service:
    """Un faux service : journalise les requêtes, répond par table."""

    def __init__(self, tables: dict[str, list[dict]] | None = None, *, statut: int = 200, corps: bytes | None = None, lenteur: float = 0.0):
        self.tables = tables if tables is not None else {"titres": TITRES}
        self.requetes: list[httpx.Request] = []
        self.statut, self.corps, self.lenteur = statut, corps, lenteur

    async def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.requetes.append(requete)
        if self.lenteur:
            await asyncio.sleep(self.lenteur)
        if self.statut != 200:
            return httpx.Response(self.statut)
        if self.corps is not None:
            return httpx.Response(200, content=self.corps)
        morceaux = requete.url.path.strip("/").split("/")
        if len(morceaux) != 3 or morceaux[0] != "tables" or morceaux[2] != "search" or morceaux[1] not in self.tables:
            return httpx.Response(404)
        q = requete.url.params["q"].lower()
        return httpx.Response(200, json=[r for r in self.tables[morceaux[1]] if any(q in str(v).lower() for v in r.values())])

    def connecteur(self, **options) -> ConnecteurEligibilite:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self))
        options.setdefault("tables", list(self.tables) or ["titres"])
        return ConnecteurEligibilite(ident="eligibilite-dgef", url=URL, titre="Référentiel d'éligibilité", client=client, **options)

    def recherches(self) -> list[httpx.Request]:
        return [r for r in self.requetes if r.url.path.endswith("/search")]


def etape(question: str, *, avec: str | None = None) -> Etape:
    return Etape(n=2 if avec else 1, source="eligibilite-dgef", question=question, attend=[1] if avec else [], avec=avec)


def amont(titre: str, texte: str) -> Passage:
    return Passage(source="docs", etape=1, rang=1, document="d", titre=titre, texte=texte)


# ─── Les mots ────────────────────────────────────────────────────────────────────────────────


def test_les_mots_significatifs_sans_mots_vides_du_plus_long_au_plus_court():
    mots = mots_significatifs("Quelles sont les pièces pour une carte de séjour salarié ?")
    normes = [n for _, n in mots]
    assert normes == ["salarie", "pieces", "sejour", "carte"]
    assert "sont" not in normes and "les" not in normes and "pour" not in normes
    # la forme cherchée garde les accents, la forme normalisée non
    assert ("séjour", "sejour") in mots


def test_les_accents_sont_tolerees_dans_les_mots_vides():
    assert [n for _, n in mots_significatifs("Après quel délai, très bien")] == ["delai"]


def test_pas_de_mots_courts_ni_de_doublons_mais_les_numeros_restent():
    normes = [n for _, n in mots_significatifs("a un L2 visa visa 12")]
    assert normes.count("visa") == 1 and "l2" in normes and "12" in normes and "a" not in normes


# ─── Les appels ──────────────────────────────────────────────────────────────────────────────


async def test_au_plus_trois_appels_par_table_sur_les_mots_les_plus_specifiques():
    service = Service({"titres": TITRES, "pieces": []})
    await service.connecteur().chercher(etape("quelles pièces pour une carte de séjour salarié pluriannuelle"), APPELANT)
    par_table: dict[str, int] = {}
    for r in service.recherches():
        table = r.url.path.split("/")[2]
        par_table[table] = par_table.get(table, 0) + 1
    assert par_table == {"titres": 3, "pieces": 3}
    cherches = {r.url.params["q"] for r in service.recherches()}
    assert cherches == {"pluriannuelle", "salarié", "pièces"}
    assert all(r.url.params["limit"] == "20" for r in service.recherches())


async def test_classement_par_nombre_de_mots_retrouves():
    service = Service()
    passages = await service.connecteur().chercher(etape("pièces carte résident passeport"), APPELANT)
    assert [p.titre for p in passages][0] == "Carte de résident — Justificatif de domicile, passeport"
    assert passages[0].score > passages[1].score
    assert [p.rang for p in passages] == [1, 2]


async def test_une_ligne_trouvee_par_deux_mots_n_est_rendue_qu_une_fois():
    service = Service()
    passages = await service.connecteur().chercher(etape("carte passeport"), APPELANT)
    assert len(passages) == len({p.document for p in passages}) == 2


async def test_avec_cherche_la_reference_courte_du_meilleur_passage_amont():
    service = Service()
    passages = await service.connecteur().chercher(
        etape("quelles pièces ?", avec="reference"), APPELANT, amont=[amont("Code", "Selon l'article L. 423-1 du code, la carte de résident est délivrée.")]
    )
    assert [r.url.params["q"] for r in service.recherches()] == ["L. 423-1"]
    assert [p.titre for p in passages] == ["Carte de résident — Justificatif de domicile, passeport"]


async def test_avec_sans_article_cherche_le_titre_court():
    assert reference_courte(amont("Carte de résident", "texte sans numéro")) == "Carte de résident"
    assert reference_courte(amont("", "Première ligne\nsuite")) == "Première ligne"
    assert reference_courte(amont("x" * 200, "")) == "x" * eligibilite.REFERENCE_MAX


async def test_avec_sans_amont_retombe_sur_la_question():
    service = Service()
    await service.connecteur().chercher(etape("carte résident", avec="reference"), APPELANT)
    assert {r.url.params["q"] for r in service.recherches()} == {"résident", "carte"}


# ─── Le passage ──────────────────────────────────────────────────────────────────────────────


async def test_une_ligne_devient_un_passage():
    service = Service()
    [p] = await service.connecteur().chercher(etape("justificatif domicile"), APPELANT)
    assert p.source == "eligibilite-dgef" and p.etape == 1 and p.rang == 1
    assert p.document == f"titres:{empreinte_ligne('titres', TITRES[1])}"
    assert p.titre == "Carte de résident — Justificatif de domicile, passeport"  # la colonne `id` ne nomme pas une ligne ; « article » est le contenu
    assert p.texte.splitlines() == ["Id : 2", "Intitule : Carte de résident", "Pieces : Justificatif de domicile, passeport", "Article : L. 423-1"]
    assert p.url is None and p.ident is None and p.meta == {"table": "titres"}


def test_l_empreinte_ne_depend_ni_de_l_ordre_des_colonnes_ni_d_un_appel_a_l_autre():
    a, b = {"x": 1, "y": "z"}, {"y": "z", "x": 1}
    assert empreinte_ligne("t", a) == empreinte_ligne("t", b) != empreinte_ligne("u", a)
    assert len(empreinte_ligne("t", a)) == 16


async def test_valeurs_vides_et_structurees():
    service = Service({"t": [{"nom": "Visa", "notes": None, "pieces": ["a", "b"]}]})
    [p] = await service.connecteur().chercher(etape("visa"), APPELANT)
    assert p.texte.splitlines() == ["Nom : Visa", 'Pieces : ["a", "b"]']


# ─── Les pannes ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("statut", [500, 503, 404])
async def test_un_statut_d_erreur_rend_une_liste_vide(statut):
    assert await Service(statut=statut).connecteur().chercher(etape("carte résident"), APPELANT) == []


@pytest.mark.parametrize("corps", [b"pas du json", b'{"rows": []}', b"[1, 2]", b""])
async def test_une_reponse_illisible_rend_une_liste_vide(corps):
    assert await Service(corps=corps).connecteur().chercher(etape("carte résident"), APPELANT) == []


async def test_le_delai_rend_une_liste_vide():
    service = Service(lenteur=0.5)
    assert await service.connecteur(delai_s=0.05).chercher(etape("carte résident"), APPELANT) == []


async def test_une_table_inconnue_n_empeche_pas_les_autres():
    service = Service({"titres": TITRES})
    passages = await service.connecteur(tables=["absente", "titres"]).chercher(etape("carte résident"), APPELANT)
    assert passages and all(p.meta["table"] == "titres" for p in passages)


async def test_une_question_sans_mot_significatif_n_appelle_rien():
    service = Service()
    assert await service.connecteur().chercher(etape("et alors ?"), APPELANT) == []
    assert service.requetes == []


# ─── Ce qui n'est jamais envoyé ──────────────────────────────────────────────────────────────


async def test_aucun_en_tete_d_autorisation_ni_identifiant_de_personne_et_jamais_de_query():
    service = Service()
    conn = service.connecteur()
    await conn.chercher(etape("carte résident passeport"), APPELANT)
    await conn.chercher(etape("pièces", avec="reference"), APPELANT, amont=[amont("Carte de résident", "")])
    assert service.requetes
    for r in service.requetes:
        assert r.method == "GET" and r.url.path.endswith("/search")  # jamais /query, jamais de POST
        assert "authorization" not in {k.lower() for k in r.headers}
        assert set(r.url.params) == {"q", "limit"}
        tout = f"{r.url} {dict(r.headers)} {r.content!r}"
        assert "personne-1" not in tout and "equipe" not in tout


async def test_le_client_cree_par_le_connecteur_n_envoie_pas_d_autorisation(monkeypatch):
    vues: list[httpx.Request] = []

    async def repondre(requete):
        vues.append(requete)
        return httpx.Response(200, json=[])

    reel = httpx.AsyncClient

    def faux(**options):
        return reel(transport=httpx.MockTransport(repondre), **options)

    monkeypatch.setattr(eligibilite.httpx, "AsyncClient", faux)
    conn = ConnecteurEligibilite(ident="eligibilite-dgef", url=URL + "/", titre="R", tables=["titres"])
    await conn.chercher(etape("carte résident"), APPELANT)
    assert vues and all("authorization" not in {k.lower() for k in r.headers} for r in vues)
    assert vues[0].url.path == "/tables/titres/search"  # la barre finale de l'adresse est retirée


async def test_la_fiche_dit_le_relais_reference():
    fiche = await Service().connecteur(description="Titres et pièces", exemples=["Quelles pièces ?"]).fiche()
    assert fiche.type == "connecteur" and fiche.id == "eligibilite-dgef" and fiche.relais == ["reference"]
    assert fiche.description == "Titres et pièces" and fiche.exemples == ["Quelles pièces ?"]


def test_le_titre_d_une_ligne_de_referentiel_nomme_ce_qui_la_distingue():
    """Les premières colonnes regroupent (communes à toutes les lignes) ; le titre prend les deux
    intitulés qui précèdent le premier contenu long."""
    from app.harnais.connecteurs.eligibilite import libelle_colonne, titre_de_ligne

    ligne = {
        "groupement": "Catégories de titres de séjour",
        "categorie": "Titres de séjour pour motif professionnel",
        "titre": 'Carte de séjour portant la mention  " salarié "',
        "situation": "1. Pièces à fournir dans tous les cas :",
        "pieces": "Justificatif de domicile de moins de six mois : " + "facture, quittance de loyer ou attestation d'hébergement. " * 3,
    }
    assert titre_de_ligne(ligne) == 'Carte de séjour portant la mention " salarié " — 1. Pièces à fournir dans tous les cas'
    # Sans contenu long, la dernière valeur est le contenu : la liste des pièces, même courte.
    courte = {**ligne, "pieces": "Visa de long séjour en cours de validité"}
    assert titre_de_ligne(courte) == 'Carte de séjour portant la mention " salarié " — 1. Pièces à fournir dans tous les cas'
    assert titre_de_ligne({"id": 3, "nom": "Visa"}) == "Visa"
    assert titre_de_ligne({"id": 3}) == ""
    assert libelle_colonne("titre_pour_eligibilite") == "Titre pour eligibilite"
