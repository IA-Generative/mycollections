"""Créer une collection par l'interface, en cinq étapes (gabarit de la refonte du 2026-10-19 : « Commencer
la création », « Étape suivante », stepper « Étape n sur 5 »), puis la retrouver sur sa fiche.

La séquence partage la page du testeur : chaque étape reprend là où la précédente s'arrête.
"""

from __future__ import annotations

import re

from tests.e2e.conftest import DOCUMENT_TEMOIN, QUESTION_TEMOIN, TEMOIN, attendre, prefixe_de_la_cible


def _suivant(page):
    """Le bouton « Suivant → » des étapes 4 et 5 (contenu inchangé par la refonte)."""
    page.get_by_text(re.compile(r"^\s*Suivant\s*→\s*$")).last.click()


def _etape_suivante(page):
    page.locator(".etape__actions").get_by_role("button", name="Étape suivante").click()


def _stepper(page) -> str:
    return re.sub(r"\s+", " ", page.locator(".fr-stepper").inner_text())


#: La catégorie choisie à l'étape 2, retrouvée sur la fiche à la fin de la séquence.
CATEGORIE = {}


def test_etape_1_choisir_la_source(session_testeur, collection_essai, captures):
    page = session_testeur.aller("/admin/create")
    assert page.locator("h1").first.inner_text().strip() == "Créer une nouvelle collection"
    assert "Étape 1 sur 5" in _stepper(page) and "Étape suivante : Identification" in _stepper(page)
    assert "Bientôt :" in session_testeur.texte()
    captures.prendre(page, "05-creation-1-source")
    page.get_by_label(re.compile("^Un fichier")).check()
    page.get_by_role("button", name="Commencer la création").click()
    page.wait_for_url(re.compile(r"/admin/create/step-2"), timeout=30_000)


def test_etape_2_identifier(session_testeur, collection_essai, captures):
    page = session_testeur.page
    assert "/admin/create/step-2" in page.url
    assert "Étape 2 sur 5" in _stepper(page)
    page.locator("#titre").fill("Note de contrôle de la suite e2e")
    # L'identifiant est proposé d'après le titre, en lecture seule.
    propose = page.locator("#name-propose")
    page.wait_for_function("() => document.querySelector('#name-propose').value.length > 0", timeout=10_000)
    assert propose.get_attribute("readonly") is not None
    # Sur une preview, l'identifiant proposé porte le préfixe imposé (`pr-<n>-note-controle…`).
    assert propose.input_value().removeprefix(prefixe_de_la_cible(session_testeur)).startswith("note-controle"), propose.input_value()
    # La suite impose son identifiant (ménage par préfixe) : il se choisit dans les réglages avancés.
    avances = page.get_by_role("button", name="Réglages avancés (facultatif)")
    if avances.get_attribute("aria-expanded") != "true":
        avances.click()
    # Une case DSFR est masquée sous son libellé : on clique le libellé, comme une personne.
    page.locator("label[for='identifiant-manuel']").click()
    assert page.locator("#identifiant-manuel").is_checked()
    page.locator("#name").fill(collection_essai)
    verdict = page.locator(".fr-valid-text, .fr-error-text").first
    verdict.wait_for(state="visible", timeout=20_000)
    assert "disponible" in verdict.inner_text(), verdict.inner_text()
    # Une catégorie existante, choisie par le créateur.
    options = page.locator("#categorie option")
    CATEGORIE["libelle"] = options.nth(1).inner_text().strip()
    page.locator("#categorie").select_option(index=1)
    captures.prendre(page, "05-creation-2-identification")
    _etape_suivante(page)
    page.wait_for_url(re.compile(r"/admin/create/step-3"), timeout=60_000)
    fiche = session_testeur.get(f"/api/collections/{collection_essai}")
    assert fiche.status == 200, "la collection créée n'est pas relue par son créateur"
    assert fiche.json().get("categorie"), "la catégorie choisie n'est pas enregistrée"


def test_etape_3_deposer_sans_attendre_l_indexation(session_testeur, collection_essai, captures):
    page = session_testeur.page
    assert page.locator("h1").first.inner_text().strip() == "Déposez vos documents"
    assert "Étape 3 sur 5" in _stepper(page)
    page.locator("input[type=file]").set_input_files(str(DOCUMENT_TEMOIN))
    captures.prendre(page, "05-creation-3-donnees", mobile=False)
    page.get_by_role("button", name="Déposer le document").click()
    # L'étape suivante s'offre dès le dépôt : l'indexation continue en tâche de fond.
    suivante = page.locator(".etape__actions").get_by_role("button", name="Étape suivante")
    suivante.wait_for(state="visible", timeout=60_000)
    captures.prendre(page, "05-creation-3-deposee", mobile=False)
    suivante.click()
    page.wait_for_url(re.compile(r"/admin/create/step-4"), timeout=30_000)


def test_etape_4_jeu_de_questions_et_question_libre(session_testeur, collection_essai, captures):
    page = session_testeur.page
    assert "Étape 4 sur 5" in _stepper(page)

    def indexation_terminee():
        reponse = session_testeur.get(f"/api/ingest/jobs?collection={collection_essai}")
        travaux = (reponse.json() or {}).get("jobs", []) if reponse.status == 200 else []
        return next((t for t in travaux if str(t.get("status", "")).startswith("done")), None)

    travail = attendre(indexation_terminee, delai=180, motif="indexation terminée")
    assert not travail.get("failed_chunks"), f"morceaux refusés : {travail}"
    # Le jeu de questions : une question saisie, avec sa réponse de référence, entre validée.
    page.get_by_role("button", name="Ajouter une question").click()
    champs = page.locator(".jeu__panneau textarea")
    champs.nth(0).fill(QUESTION_TEMOIN)
    champs.nth(1).fill(TEMOIN)
    page.get_by_role("button", name=re.compile(r"Ajouter au jeu")).click()
    attendre(lambda: "Question ajoutée au jeu" in session_testeur.texte(), delai=30, motif="la question ajoutée au jeu")
    assert "Mesurer avec 1 question validée" in session_testeur.texte(), "la question saisie doit être mesurable"
    captures.prendre(page, "05-creation-4-jeu", mobile=False)
    # Une question libre, posée tout de suite à la collection.
    page.get_by_text("Poser une question libre à la collection").click()
    page.locator("#etape4-question").fill(QUESTION_TEMOIN)
    page.get_by_role("button", name=re.compile(r"^\s*Poser la question\s*$")).click()
    attendre(lambda: TEMOIN in page.locator(".etape4__reponse").inner_text(), delai=180, motif=f"le témoin « {TEMOIN} » dans la réponse de l'étape 4")
    captures.prendre(page, "05-creation-4-reponse", mobile=False)
    _suivant(page)
    page.wait_for_url(re.compile(r"/admin/create/step-5"), timeout=30_000)


def test_etape_5_dit_ce_qui_suit_et_mene_a_la_fiche(session_testeur, collection_essai, captures):
    page = session_testeur.page
    assert "Étape 5 sur 5" in _stepper(page)
    texte = session_testeur.texte()
    captures.prendre(page, "05-creation-5-partage")
    assert "en cours de vérification" in texte, "l'étape 5 doit dire que la collection est à vérifier avant d'être ouverte à tous"
    for promesse in ("embed.js", "Extension navigateur", "Tool MyRAG", "localhost"):
        assert promesse not in texte, f"l'étape 5 promet encore « {promesse} »"
    page.get_by_role("button", name="Terminer").click()
    page.get_by_role("link", name=re.compile("Ouvrir la fiche de la collection")).click()
    page.wait_for_url(re.compile(rf"/c/{collection_essai}"), timeout=30_000)
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    assert "Note de contrôle" in page.locator("h1").first.inner_text()
    if CATEGORIE.get("libelle"):
        assert CATEGORIE["libelle"] in session_testeur.texte(), "la catégorie choisie à l'étape 2 n'est pas sur la fiche"
    captures.prendre(page, "05-creation-6-fiche-creee")


def _pdf_minimal(texte: str) -> bytes:
    """Une page, une ligne, police standard : le plus petit PDF qu'un extracteur lise."""
    flux = f"BT /F1 12 Tf 72 720 Td ({texte}) Tj ET".encode("ascii")
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(flux) + flux + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    positions = []
    for i, o in enumerate(objets, 1):
        positions.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
    out += b"".join(b"%010d 00000 n \n" % p for p in positions)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objets) + 1, xref)
    return bytes(out)


def test_un_pdf_est_accepte_et_confie_a_openrag(session_testeur, collection_essai):
    """Depuis la 0.4.0 (PR #61), un document (PDF, Word…) est gardé comme source puis confié tel quel
    à OpenRAG, qui l'extrait lui-même : il n'est plus refusé en 415. Un vrai PDF, pour qu'OpenRAG
    (qui vérifie le contenu contre l'extension depuis la 2.3) l'accepte aussi."""
    r = session_testeur.page.request.post(
        f"{session_testeur.base}/api/ingest/{collection_essai}",
        headers={"Authorization": f"Bearer {session_testeur.jeton}"},
        multipart={"file": {"name": "essai.pdf", "mimeType": "application/pdf", "buffer": _pdf_minimal("Essai de bout en bout")}},
    )
    assert r.status == 200, f"{r.status} : {r.text()[:200]}"


def test_un_lien_de_graphe_d_une_collection_non_publique_est_ferme_sans_signature(cible, collection_essai, session_testeur):
    """Les vues ouvertes sans jeton (graphe, articles) ne servent une collection non publiée à
    tous que par un lien signé ; la fiche en obtient un pour son iframe."""
    import httpx

    with httpx.Client(timeout=20.0) as client:
        assert client.get(f"{cible['base']}/graph/data?corpus_id={collection_essai}").status_code == 401
        assert client.get(f"{cible['base']}/articles/{collection_essai}/1").status_code == 401
        lien = session_testeur.get(f"/graph/{collection_essai}/lien").json()["url"]
        assert client.get(cible["base"] + lien.replace("/graph?", "/graph/data?")).status_code == 200
