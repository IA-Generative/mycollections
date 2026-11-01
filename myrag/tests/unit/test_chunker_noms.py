"""Le nom de fichier d'une section ou d'une question se lit : OpenRAG ne garde que lui, pas le titre en métadonnée."""

from app.services.chunker import chunk_by_qr, chunk_by_section, slug_de_section


def test_les_accents_sont_translitteres_pas_supprimes():
    assert slug_de_section("Le code de contrôle") == "le-code-de-controle"
    assert slug_de_section("Élus et vie publique : délais") == "elus-et-vie-publique-delais"


def test_le_reste_ne_change_pas():
    assert slug_de_section("Article L423-3") == "article-l423-3"
    assert len(slug_de_section("x" * 80)) == 50


def test_le_decoupage_par_section_nomme_ses_fichiers_lisiblement():
    morceaux = chunk_by_section("## Le code de contrôle\nQUETZAL.\n\n## Ce que cette collection n'est pas\nRien.")
    assert [m["filename"] for m in morceaux] == ["section-le-code-de-controle.md", "section-ce-que-cette-collection-n-est-pas.md"]


def test_le_decoupage_par_question_garde_les_accents_translitteres():
    morceaux = chunk_by_qr("## Quelle quotité de temps partiel ?\nCinquante pour cent.\n\n## Où déposer sa demande de congé bonifié ou de détachement ?\nAu service.")
    assert [m["filename"] for m in morceaux] == ["QR-1-quelle-quotite-de-temps-partiel.md", "QR-2-ou-deposer-sa-demande-de-conge-bonifie-o.md"]  # 40 caractères au plus
    assert morceaux[0]["metadata"]["question"] == "Quelle quotité de temps partiel ?"
