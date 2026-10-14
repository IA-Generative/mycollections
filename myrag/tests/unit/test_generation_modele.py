"""Fabrique des modèles, compteur d'appels et de jetons, disponibilité de la génération."""

from __future__ import annotations

import threading

import pytest

import app.generation as generation
from app.config import settings


def test_manques_nomme_les_variables_vides(monkeypatch):
    for champ in ("generation_llm_url", "generation_llm_cle", "generation_llm_modele"):
        monkeypatch.setattr(settings, champ, "")
    assert generation.manques() == ["MYCOLLECTIONS_GENERATION_LLM_URL", "MYCOLLECTIONS_GENERATION_LLM_CLE",
                                    "MYCOLLECTIONS_GENERATION_LLM_MODELE"]
    with pytest.raises(generation.GenerationIndisponible, match="MYCOLLECTIONS_GENERATION_LLM_CLE"):
        generation.exiger_prete()
    monkeypatch.setattr(settings, "generation_llm_url", "https://passerelle.fake-domain.name/v1")
    monkeypatch.setattr(settings, "generation_llm_cle", "cle")
    monkeypatch.setattr(settings, "generation_llm_modele", "chat")
    assert generation.manques() == []


def test_sans_ragas_le_message_dit_l_extra(monkeypatch):
    monkeypatch.setattr(generation.importlib.util, "find_spec", lambda nom: None)
    assert not generation.disponible() and not generation.prete()
    with pytest.raises(generation.GenerationIndisponible, match="extra « generation »"):
        generation.exiger_prete()


def test_telemetrie_de_ragas_coupee():
    import os
    assert os.environ.get("RAGAS_DO_NOT_TRACK") == "true"


pytest.importorskip("ragas")
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, LLMResult  # noqa: E402

from app.generation import modele  # noqa: E402


def test_fabrique_du_modele_de_langage(monkeypatch):
    monkeypatch.setattr(settings, "generation_max_tokens", 2048)
    llm = modele.fabriquer_llm(modele.Compteurs(), url="https://passerelle.fake-domain.name/v1", cle="cle", modele="chat")
    chat = llm.langchain_llm
    assert chat.openai_api_base == "https://passerelle.fake-domain.name/v1"
    assert chat.model_name == "chat" and chat.max_tokens == 2048
    assert chat.openai_api_key.get_secret_value() == "cle"
    assert chat.max_retries == 0  # les réessais sont ceux de ragas, comptés


def test_fabrique_des_embeddings_reprend_l_url_du_modele(monkeypatch):
    monkeypatch.setattr(settings, "generation_llm_url", "https://passerelle.fake-domain.name/v1")
    monkeypatch.setattr(settings, "generation_embeddings_url", "")
    emb = modele.fabriquer_embeddings(modele.Compteurs(), cle="cle", modele="bge-m3")
    assert emb.embeddings.openai_api_base == "https://passerelle.fake-domain.name/v1"
    assert emb.embeddings.check_embedding_ctx_length is False
    assert emb.embeddings.model == "bge-m3"


def _resultat(entree=100, sortie=20, fin="stop"):
    g = ChatGeneration(message=AIMessage(content="{}"), generation_info={"finish_reason": fin})
    return LLMResult(generations=[[g]], llm_output={"token_usage": {"prompt_tokens": entree, "completion_tokens": sortie}})


def test_compteur_jetons_reparations_inachevees_erreurs():
    c = modele.Compteurs()
    c.observer("extraire", _resultat(), 0.5)
    c.observer(f"... {modele.MARQUE_REPARATION} ...", _resultat(50, 10), 0.2)
    c.observer("long", _resultat(10, 4096, fin="length"), 3.0)
    c.observer("panne", None, 0.1, RuntimeError("x"))
    i = c.instantane()
    assert (i["appels_llm"], i["tokens_entree"], i["tokens_sortie"]) == (4, 160, 4126)
    assert (i["reparations_json"], i["inachevees"], i["erreurs_llm"]) == (1, 1, 1)


def test_compteur_sous_verrou():
    c = modele.Compteurs()

    def frapper():
        for _ in range(1000):
            c.observer("x", _resultat(1, 1), 0.0)
    fils = [threading.Thread(target=frapper) for _ in range(4)]
    [f.start() for f in fils]
    [f.join() for f in fils]
    assert c.instantane()["appels_llm"] == 4000 and c.instantane()["tokens_entree"] == 4000


def test_jetons_lus_dans_usage_metadata_a_defaut():
    msg = AIMessage(content="{}", usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10})
    r = LLMResult(generations=[[ChatGeneration(message=msg)]], llm_output={})
    assert modele._usage(r) == (7, 3, False)


def test_debit_bloque_au_dela_du_quota_par_minute():
    from app.generation.resultats import Debit
    t = [0.0]
    dormi = []
    d = Debit(3, horloge=lambda: t[0], dormir=lambda s: (dormi.append(s), t.__setitem__(0, t[0] + s)))
    for _ in range(3):
        d.prendre()
    assert dormi == []
    d.prendre()  # la 4e attend que la 1re sorte de la fenêtre de 60 s
    assert len(dormi) == 1 and 59.9 < dormi[0] < 60.2
    Debit(0, dormir=lambda s: (_ for _ in ()).throw(AssertionError("0 = sans limite"))).prendre()


def test_refus_de_debit_compte_et_dit():
    from app.generation.resultats import message_sur

    class RateLimitError(Exception):
        pass
    c = modele.Compteurs()
    c.observer("x", None, 0.1, RateLimitError("Error code: 429 - rate limit exceeded"))
    assert c.instantane()["refus_debit"] == 1 and c.instantane()["erreurs_llm"] == 1
    assert "débit" in message_sur(RateLimitError("429"))
