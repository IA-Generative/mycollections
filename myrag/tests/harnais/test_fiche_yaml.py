"""La fiche d'un assistant en YAML : l'aller-retour garde l'empreinte, la lecture est sûre
(safe_load, sans alias ni clef en double) et ses erreurs disent le champ, en français."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.harnais import fiche_yaml
from app.harnais.contrat import Canaux, FicheAssistant, ReferenceResume, canonique, empreinte
from app.harnais.fiche_yaml import FicheYamlInvalide, charger, ecrire, lire
from tests.conftest import SUPERADMIN
from tests.harnais.conftest import ALICE, DEHORS, fiche_d_essai

EXEMPLE = Path(__file__).resolve().parents[3] / "docs" / "exemples" / "assistants" / "sejour-des-etrangers.yaml"
JEU = {"mienne": "t-mienne", "partagee": "t-partagee", "ouverte": "t-ouverte", "secrete": "t-secrete"}


def _emp(f: FicheAssistant) -> str:
    return empreinte(canonique(f))


def _erreurs(texte: str) -> list[str]:
    with pytest.raises(FicheYamlInvalide) as e:
        charger(texte)
    return [str(x) for x in e.value.erreurs]


def _riche() -> FicheAssistant:
    """Tout ce que le contrat permet : textes multilignes, valeurs qui ressemblent à autre chose."""
    return FicheAssistant.model_validate(
        {
            "assistant": "essai.riche_1",
            "titre": "no",
            "rubrique": "1234",
            "description": "Première ligne : avec deux-points.\nSeconde ligne, # pas un commentaire",
            "seuil_fiable": 0.75,
            "validation_requise": True,
            "sources": [{"id": "abc", "type": "collection", "regime": "toujours", "rang": 2}, {"id": "ref-1", "type": "connecteur", "regime": "sur_consigne"}],
            "consignes": [
                {"id": "c-toujours", "quand": "toujours", "repondre": "Répondre :\n- court\n- sourcé", "gabarit": "juridique"},
                {
                    "id": "c-2",
                    "quand": "yes",
                    "exemples": ["une question « entre guillemets » ?", "x" * 200, "true", "a, b: [c]"],
                    "chercher": [{"source": "abc"}, {"source": "ref-1", "avec": "reference"}],
                },
            ],
        }
    )


# ─── L'aller-retour ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("fiche", [_riche(), fiche_d_essai(JEU, "t-asst-essai")], ids=["riche", "fixture-du-harnais"])
def test_aller_retour_meme_empreinte_et_meme_fiche(fiche):
    texte = ecrire(fiche)
    relue = charger(texte)
    assert _emp(relue) == _emp(fiche)
    assert relue == fiche
    assert texte.startswith(f"# contrat: 1 · empreinte: sha256:{_emp(fiche)}\n")
    assert ecrire(relue) == texte, "écrire est stable"


def test_l_exemple_de_la_documentation_se_charge_et_s_ecrit_a_l_identique():
    texte = EXEMPLE.read_text(encoding="utf-8")
    fiche = charger(texte)
    assert fiche.assistant == "sejour-des-etrangers"
    assert [s.id for s in fiche.sources_ordonnees()] == ["accords-bilateraux", "ceseda", "referentiel-eligibilite"]
    assert fiche.consignes[1].chercher[2].avec == "article_trouve"
    # Le corps (sans les commentaires) est exactement ce qu'écrit `ecrire` : l'exemple a la forme d'un export.
    corps = lambda t: "\n".join(ligne for ligne in t.splitlines() if not ligne.startswith("#"))  # noqa: E731
    assert corps(ecrire(fiche)) == corps(texte)


def test_reference_en_commentaire_et_ignoree_a_l_import():
    fiche = _riche().model_copy(update={"reference": ReferenceResume(questions=12, fiables=3)})
    texte = ecrire(fiche)
    assert "# reference (calculée, ignorée à l'import) : 12 questions, 3 fiables" in texte
    assert "reference:" not in texte and "publication:" not in texte
    lecture = lire(texte + "reference: {questions: 99, fiables: 99}\npublication: {api: true}\n")
    assert lecture.fiche.reference is None and lecture.fiche.publication.api is False
    assert len(lecture.avertissements) == 2 and "reference" in lecture.avertissements[0] and "Publication" in lecture.avertissements[1]
    assert _emp(lecture.fiche) == _emp(fiche)


def test_les_valeurs_par_defaut_ne_s_ecrivent_pas():
    texte = ecrire(fiche_d_essai(JEU, "t-asst-essai"))
    for absent in ("description:", "rubrique:", "consignes:\n  -", "avec:", "gabarit:"):
        assert absent not in texte
    assert "seuil_fiable: 0.9" in texte and "validation_requise: false" in texte


# ─── Les erreurs lisibles ────────────────────────────────────────────────────────────────────

BASE = "assistant: essai\ntitre: Essai\nsources:\n  - {id: abc, type: collection}\n"


def test_une_source_citee_absente_des_sources_est_nommee():
    erreurs = _erreurs(BASE + "consignes:\n  - id: c-1\n    quand: q\n    chercher:\n      - {source: inconnue}\n")
    assert erreurs == ["fiche : la consigne « c-1 » cherche dans « inconnue », qui n'est pas une source de l'assistant"]


def test_avec_sur_la_premiere_etape_est_refuse_avec_le_chemin():
    erreurs = _erreurs(BASE + "consignes:\n  - id: c-1\n    quand: q\n    chercher:\n      - {source: abc, avec: article_trouve}\n")
    assert erreurs == ["consignes[1] (c-1) : « avec » n'a pas de sens sur la première étape : rien n'a encore été trouvé"]


def test_les_erreurs_de_champ_sont_en_francais_avec_leur_chemin():
    erreurs = _erreurs("assistant: Essai!\ntitre: ''\nseuil_fiable: 2\nsources:\n  - {id: abc, type: collection, regime: parfois}\nconsigne: []\n")
    assert "assistant : identifiant invalide : 3 à 64 caractères, minuscules, chiffres, « . », « _ » ou « - »" in erreurs
    assert "titre : ne peut pas être vide" in erreurs
    assert "seuil_fiable : doit être inférieur ou égal à 1.0" in erreurs
    assert "sources[1] (abc) › regime : valeur non admise : attendu 'toujours', 'selon_question' ou 'sur_consigne'" in erreurs
    assert "consigne : champ inconnu du contrat (vérifiez l'orthographe)" in erreurs


def test_un_relais_mal_nomme_et_un_texte_qui_n_en_est_pas_un():
    erreurs = _erreurs(
        BASE.replace("titre: Essai", "titre: 12")
        + "  - {id: ref, type: connecteur}\nconsignes:\n  - id: c-1\n    quand: q\n    chercher: [{source: abc}, {source: ref, avec: Article}]\n"
    )
    assert erreurs[0].startswith("titre : doit être un texte")
    assert erreurs[1].startswith("consignes[1] (c-1) › chercher[2] › avec : nom de relais invalide")


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("!!python/object/apply:os.system ['echo pwned']\n", "balise YAML refusée"),
        (BASE + "titre2: !!python/object/apply:os.system ['echo pwned']\n", "balise YAML refusée"),
        ("a: &x [1, 2]\nb: *x\n", "les alias YAML (*nom) ne sont pas acceptés"),
        (BASE + "titre: Autre\n", "la clef « titre » apparaît deux fois"),
        ("assistant: [\n", "YAML illisible"),
        ("- une liste\n", "doit décrire un objet"),
        ("", "doit décrire un objet"),
    ],
)
def test_lecture_sure(texte, attendu, monkeypatch):
    import os

    appels = []
    monkeypatch.setattr(os, "system", lambda *a: appels.append(a))
    erreurs = _erreurs(texte)
    assert len(erreurs) == 1 and attendu in erreurs[0], erreurs
    assert appels == []


def test_taille_et_encodage():
    trop = BASE + "description: " + "x" * fiche_yaml.TAILLE_MAX + "\n"
    assert "trop gros" in _erreurs(trop)[0]
    with pytest.raises(FicheYamlInvalide, match="UTF-8"):
        charger(b"assistant: \xff\xfe\n")
    assert charger(b"\xef\xbb\xbf" + BASE.encode()).assistant == "essai", "la marque d'ordre des octets est tolérée"


# ─── Les routes ──────────────────────────────────────────────────────────────────────────────


def _url(ident: str) -> str:
    return f"/api/assistants/{ident}/fiche.yaml"


def _put(client, ident: str, texte: str):
    return client.put(_url(ident), content=texte.encode("utf-8"), headers={"Content-Type": "text/yaml"})


@pytest.fixture
def enregistre(client, en_tant_que, jeu, ident_assistant):
    """L'assistant d'essai (trois sources), enregistré par l'administration, servi sur l'API."""
    en_tant_que(SUPERADMIN)
    fiche = fiche_d_essai(jeu, ident_assistant, publication={"api": True})
    assert client.put(f"/api/assistants/{ident_assistant}", json=fiche.model_dump(mode="json")).status_code == 200
    return fiche


def test_exporter_puis_reimporter_puis_publier_garde_l_empreinte(client, enregistre):
    ident = enregistre.assistant
    r = client.get(_url(ident))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "text/yaml; charset=utf-8"
    assert r.headers["content-disposition"] == f'attachment; filename="{ident}.yaml"'
    assert charger(r.text) == enregistre.model_copy(update={"publication": Canaux()})
    assert "# reference (calculée, ignorée à l'import) : 0 questions, 0 fiables" in r.text
    i = _put(client, ident, r.text)
    assert i.status_code == 200, i.text
    assert i.json()["empreinte"] == _emp(enregistre) and i.json()["avertissements"] == []
    assert i.json()["fiche"]["publication"]["api"] is True, "les canaux du brouillon restent"
    p = client.post(f"/api/assistants/{ident}/publier").json()
    assert f"empreinte: sha256:{p['empreinte']}" in r.text, "l'en-tête du fichier annonce l'empreinte de la version"


def test_importer_remplace_le_brouillon_et_avertit(client, enregistre):
    ident = enregistre.assistant
    texte = ecrire(enregistre).replace("titre: Assistant d'essai", "titre: Repris par fichier")
    texte += "publication: {api: false, portail: true}\nreference: {questions: 7}\n"
    r = _put(client, ident, texte)
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["fiche"]["titre"] == "Repris par fichier"
    assert corps["fiche"]["publication"] == {"socle": False, "portail": False, "fenetre_js": False, "api": True}
    assert len(corps["avertissements"]) == 2
    assert corps["empreinte"] == _emp(charger(texte))


def test_import_refuse_lisiblement(client, enregistre):
    ident = enregistre.assistant
    autre = _put(client, ident, ecrire(enregistre.model_copy(update={"assistant": "un-autre"})))
    assert autre.status_code == 400 and "un-autre" in autre.json()["detail"]
    double = _put(client, ident, ecrire(enregistre) + "seuil_fiable: 3\n")
    assert double.status_code == 422
    assert double.json()["detail"]["erreurs"][0]["message"] == "la clef « seuil_fiable » apparaît deux fois"
    hors = _put(client, ident, ecrire(enregistre).replace("seuil_fiable: 0.9", "seuil_fiable: 3"))
    assert hors.status_code == 422
    assert hors.json()["detail"] == {
        "message": "Le fichier n'est pas une fiche d'assistant valide.",
        "erreurs": [{"champ": "seuil_fiable", "message": "doit être inférieur ou égal à 1.0"}],
    }
    assert _put(client, ident, "#" * (fiche_yaml.TAILLE_MAX + 1)).status_code == 413


def test_un_lecteur_exporte_ce_qu_il_lit_sans_pouvoir_importer(client, en_tant_que, jeu, enregistre):
    ident = enregistre.assistant
    texte = client.get(_url(ident)).text
    en_tant_que(ALICE)
    r = client.get(_url(ident))
    assert r.status_code == 200
    assert jeu["secrete"] not in r.text and "# 1 source(s) que vous ne lisez pas sont absentes" in r.text
    assert _put(client, ident, texte).status_code == 403, "Alice ne gère ni `partagee` ni `secrete`"
    en_tant_que(DEHORS)
    assert client.get(_url(ident)).status_code == 404
    assert _put(client, ident, texte).status_code == 404


def test_importer_cree_un_assistant_comme_le_put_json(client, en_tant_que, jeu, ident_assistant):
    fiche = FicheAssistant.model_validate({"assistant": ident_assistant, "titre": "Neuf", "sources": [{"id": jeu["mienne"], "type": "collection"}]})
    en_tant_que(ALICE)
    r = _put(client, ident_assistant, ecrire(fiche))
    assert r.status_code == 200, r.text
    assert r.json()["mes_droits"] == {"ecrire": True} and r.json()["fiche"]["publication"]["api"] is False
    inconnue = fiche.model_copy(update={"sources": [*fiche.sources, fiche.sources[0].model_copy(update={"id": "t-n-existe-pas"})]})
    assert _put(client, ident_assistant, ecrire(inconnue)).status_code == 422
