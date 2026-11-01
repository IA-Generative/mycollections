"""La fiche d'un assistant en YAML : l'aller-retour garde l'empreinte, la lecture est sûre
(safe_load, sans alias ni clef en double) et ses erreurs disent le champ, en français."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.harnais import fiche_yaml
from app.harnais.contrat import FicheAssistant, ReferenceResume, canonique, empreinte
from app.harnais.fiche_yaml import FicheYamlInvalide, charger, ecrire, lire
from tests.harnais.conftest import fiche_d_essai

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
    assert charger(("﻿" + BASE).encode()).assistant == "essai", "la marque d'ordre des octets est tolérée"
