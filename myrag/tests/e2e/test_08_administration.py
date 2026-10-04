"""L'administration : réservée aux superadmins, et cohérente (pas de lien mort)."""
from __future__ import annotations

import re

import pytest


def test_un_testeur_simple_n_entre_pas_dans_l_administration(session_testeur):
    if any(g.endswith("/superadmin") for g in session_testeur.groupes()):
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


@pytest.mark.xfail(strict=True, reason="P2 : la carte « Templates » de /admin mène à /admin/templates, qui n'existe pas")
def test_les_cartes_de_l_administration_menent_quelque_part(session_admin):
    page = session_admin.aller("/admin")
    page.locator("h1").first.wait_for(state="visible", timeout=30_000)
    liens = [page.locator("a[href^='/admin/']").nth(i).get_attribute("href")
             for i in range(page.locator("a[href^='/admin/']").count())]
    for lien in sorted(set(l for l in liens if l)):
        session_admin.aller(lien)
        page.wait_for_timeout(1_500)
        texte = session_admin.texte()
        assert not re.search(r"Page not found|404", texte), f"{lien} : page absente"
