"""Les passages donnés à la génération : échantillon, nettoyage, identifiants conservés."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.generation import morceaux as m
from app.services import corpus

TEXTE = "Le titre de séjour pluriannuel est délivré par le préfet après un premier titre d'un an."


def _fichiers(n: int) -> list[dict]:
    return [{"file_id": f"f{i}", "title": f"Question {i}"} for i in range(n)]


def _chunk(cid: str, fid: str, texte: str = TEXTE, partition: str = "faq") -> dict:
    return {
        "link": f"https://openrag/extract/{cid}",
        "content": f"[CONTEXT] résumé\n* filename: {fid}.md\n[CHUNK_START] {texte} [CHUNK_END]",
        "metadata": {"_id": cid, "file_id": fid, "partition": partition, "page": 1, "filename": f"{fid}.md"},
    }


@pytest.fixture(autouse=True)
def _sans_cache():
    corpus.oublier()
    yield
    corpus.oublier()


def test_nombre_a_lire_quatre_par_paire_plafonne():
    assert m.nombre_a_lire(30, 200) == 120
    assert m.nombre_a_lire(60, 200) == 200
    assert m.nombre_a_lire(0, 200) == 4


def test_echantillon_couvre_toute_la_collection_et_reste_stable():
    fichiers = _fichiers(3585)
    a = m.echantillonner_fichiers(fichiers, 120, "run-1")
    assert len(a) == 120 and len({f["file_id"] for f in a}) == 120
    assert a == m.echantillonner_fichiers(list(reversed(fichiers)), 120, "run-1")
    assert a != m.echantillonner_fichiers(fichiers, 120, "run-2")
    # Le tourniquet va jusqu'au bout de la liste, pas seulement le début.
    rangs = sorted(int(f["file_id"][1:]) for f in a)
    assert rangs[0] < 40 and rangs[-1] > 3500


def test_echantillon_prend_tout_si_moins_de_fichiers():
    assert len(m.echantillonner_fichiers(_fichiers(5), 120, "g")) == 5


def test_morceau_sans_habillage_avec_ses_identifiants():
    morceau = m.morceau_depuis_chunk(_chunk("42", "f1"), "faq")
    assert morceau.texte == TEXTE
    assert morceau.identifiants() == {"chunk_id": "42", "file_id": "f1", "partition": "faq", "fichier": "f1.md", "page": "1"}


def test_morceau_ignore_vide_court_et_partition_etrangere():
    assert m.morceau_depuis_chunk(_chunk("1", "f1", texte=""), "faq") is None
    assert m.morceau_depuis_chunk(_chunk("1", "f1", texte="Oui."), "faq") is None
    assert m.morceau_depuis_chunk(_chunk("1", "f1", partition="autre"), "faq") is None


def test_documents_gardent_les_identifiants():
    pytest.importorskip("langchain_core")
    morceaux = [m.morceau_depuis_chunk(_chunk(str(i), f"f{i}"), "faq") for i in range(3)]
    docs = m.en_documents(morceaux)
    assert [d.page_content for d in docs] == [TEXTE] * 3
    assert [d.metadata["chunk_id"] for d in docs] == ["0", "1", "2"]
    assert docs[1].metadata == {"chunk_id": "1", "file_id": "f1", "partition": "faq", "fichier": "f1.md", "page": "1"}


def _client(fichiers, par_fichier=None, chunks_absent=False, en_panne=()):
    c = MagicMock()
    c.list_files = AsyncMock(return_value=fichiers)

    async def partition_chunks(partition, file_id=None, limit=None):
        if file_id in en_panne:
            raise RuntimeError("panne")
        if chunks_absent:
            return None
        return (par_fichier or {}).get(file_id, [_chunk(f"c-{file_id}", file_id)])

    c.partition_chunks = AsyncMock(side_effect=partition_chunks)
    c.file_detail = AsyncMock(side_effect=lambda p, fid: {"documents": [{"link": f"http://o/extract/x-{fid}"}]})
    c.extract = AsyncMock(side_effect=lambda cid: {"page_content": TEXTE, "metadata": {"partition": "faq", "filename": "a.md"}})
    return c


def test_lecture_par_chunks_un_passage_par_fichier():
    pris, total = asyncio.run(m.lire_echantillon(_client(_fichiers(10)), "faq", 4, "g"))
    assert total == 10 and len(pris) == 4
    assert len({p.file_id for p in pris}) == 4
    assert all(p.chunk_id == f"c-{p.file_id}" for p in pris)


def test_lecture_repli_extract_quand_la_route_manque():
    client = _client(_fichiers(3), chunks_absent=True)
    pris, _ = asyncio.run(m.lire_echantillon(client, "faq", 3, "g"))
    assert sorted(p.chunk_id for p in pris) == ["x-f0", "x-f1", "x-f2"]
    assert client.extract.await_count == 3


def test_deuxieme_tour_quand_il_manque_des_passages():
    par_fichier = {"f0": [_chunk("a", "f0"), _chunk("b", "f0"), _chunk("c", "f0")]}
    pris, _ = asyncio.run(m.lire_echantillon(_client(_fichiers(1), par_fichier), "faq", 3, "g"))
    assert sorted(p.chunk_id for p in pris) == ["a", "b", "c"]


def test_un_fichier_en_panne_ne_bloque_pas():
    pris, _ = asyncio.run(m.lire_echantillon(_client(_fichiers(4), en_panne={"f1"}), "faq", 4, "g"))
    assert sorted(p.file_id for p in pris) == ["f0", "f2", "f3"]
