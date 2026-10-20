"""L'administration : réservée aux superadmins, et cohérente (pas de lien mort)."""

from __future__ import annotations

import re

import pytest


def test_un_testeur_simple_n_entre_pas_dans_l_administration(session_testeur):
    if session_testeur.superadmin():
        pytest.skip("le compte testeur est superadmin")
    page = session_testeur.aller("/admin")
    page.wait_for_timeout(4_000)
    assert "Administration MyRAG" not in session_testeur.texte(), "la page d'administration s'affiche à un simple testeur"


def test_l_administration_s_ouvre_au_superadmin(session_admin, captures):
    page = session_admin.aller("/admin")
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    assert "Administration" in page.locator("h1").first.inner_text()
    captures.prendre(page, "10-administration")
    page = session_admin.aller("/admin/categories")
    assert "Catégories" in page.locator("h1").first.inner_text()
    captures.prendre(page, "10-administration-categories", mobile=False)
    page = session_admin.aller("/admin/amorces")
    assert "Amorces" in page.locator("h1").first.inner_text()
    captures.prendre(page, "10-administration-amorces", mobile=False)


def test_les_cartes_de_l_administration_menent_quelque_part(session_admin):
    page = session_admin.aller("/admin")
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    liens = [page.locator("a[href^='/admin/']").nth(i).get_attribute("href") for i in range(page.locator("a[href^='/admin/']").count())]
    for lien in sorted(set(lien for lien in liens if lien)):
        session_admin.aller(lien)
        page.wait_for_timeout(1_500)
        texte = session_admin.texte()
        assert not re.search(r"Page not found|404", texte), f"{lien} : page absente"


def test_archiver_et_purger_se_trouvent_dans_les_reglages(session_testeur):
    """Refonte du 2026-10-19 : les gestes d'archivage ont quitté le catalogue pour la « Zone
    sensible » des Réglages, réservée à qui gère la collection."""
    reponse = session_testeur.get("/api/collections")
    geree = next((c for c in (reponse.json() or {}).get("collections", []) if (c.get("mes_droits") or {}).get("ecrire") and not c.get("orphan")), None)
    if not geree:
        pytest.skip("le compte testeur ne gère aucune collection sur la cible")
    page = session_testeur.aller(f"/c/{geree['name']}/config")
    zone = page.locator("section", has=page.get_by_role("heading", name="Zone sensible"))
    zone.wait_for(state="visible", timeout=30_000)
    assert zone.get_by_role("button", name=re.compile(r"^(Archiver|Désarchiver)$")).count() == 1
