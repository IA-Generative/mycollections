"""Tests du modèle d'accès complet (scope + groupes autorisés + créateur).

Couvre app.services.access.can_read / can_write / groups_match.
"""

from app.services import access


SUPERADMIN = ["/myrag/superadmin"]
CREATOR_SUB = "u-creator"


class TestGroupsMatch:
    def test_match_fiche_avec_ou_sans_slash_initial(self):
        # Côté fiche, la valeur enregistrée est normalisée.
        assert access.groups_match(["/dir/pole-juridique"], ["dir/pole-juridique"])
        assert access.groups_match(["/dir/pole-juridique"], ["/dir/pole-juridique"])

    def test_claim_en_noms_courts_ne_correspond_a_rien(self):
        # Côté jeton, seul un chemin complet compte : un nom court est forgeable.
        assert not access.groups_match(["dir/pole-juridique"], ["/dir/pole-juridique"])
        assert not access.groups_match(["mirai-beta-testeurs"], ["mirai-beta-testeurs"])
        assert not access.groups_match(["pole-juridique", "/dir/pole-juridique"], ["/dir/pole-juridique"])

    def test_homonyme_dans_un_autre_parent_refuse(self):
        assert not access.groups_match(["/g/BACI/Admins"], ["/g/Mirai Analyse/Admins"])

    def test_pas_de_match(self):
        assert not access.groups_match(["/dir/rh"], ["/dir/juridique"])

    def test_listes_vides(self):
        assert not access.groups_match([], ["/dir/x"])
        assert not access.groups_match(["/dir/x"], [])
        assert not access.groups_match(None, None)


class TestCanWrite:
    def _w(self, **kw):
        base = dict(name="victor", created_by="", user_groups=[], user_sub="x")
        base.update(kw)
        return access.can_write(**base)

    def test_superadmin(self):
        assert self._w(user_groups=SUPERADMIN)

    def test_createur(self):
        assert self._w(created_by=CREATOR_SUB, user_sub=CREATOR_SUB)

    def test_membre_groupe_admin(self):
        assert self._w(user_groups=["/myrag/victor-admin"])

    def test_lecteur_simple_refuse(self):
        # membre du groupe lecteur /myrag/victor : pas d'écriture
        assert not self._w(user_groups=["/myrag/victor"])

    def test_groupe_autorise_ne_donne_pas_ecriture(self):
        # un groupe autorisé en lecture n'écrit jamais
        assert not self._w(user_groups=["/dir/juridique"])


class TestCanRead:
    def _r(self, **kw):
        base = dict(name="victor", scope="group", scope_groups=[],
                    created_by="", user_groups=[], user_sub="x")
        base.update(kw)
        return access.can_read(**base)

    # --- gestionnaires lisent toujours ---
    def test_createur_lit_meme_en_prive(self):
        assert self._r(scope="private", created_by=CREATOR_SUB, user_sub=CREATOR_SUB)

    def test_admin_lit_meme_en_prive(self):
        assert self._r(scope="private", user_groups=["/myrag/victor-admin"])

    def test_superadmin_lit_tout(self):
        assert self._r(scope="private", user_groups=SUPERADMIN)

    # --- public ---
    def test_public_lisible_par_tous(self):
        assert self._r(scope="public", user_groups=["/myrag/autre"])

    # --- private ---
    def test_prive_refuse_aux_tiers(self):
        assert not self._r(scope="private", user_groups=["/myrag/victor"])

    # --- group ---
    def test_group_membre_lecteur(self):
        assert self._r(scope="group", user_groups=["/myrag/victor"])

    def test_group_groupe_autorise(self):
        assert self._r(scope="group", scope_groups=["/dir/juridique"],
                       user_groups=["/dir/juridique"])

    def test_group_tiers_refuse(self):
        assert not self._r(scope="group", scope_groups=["/dir/juridique"],
                           user_groups=["/dir/rh"])


class TestFormeDeLaBeta:
    """Modèle complet, claim en noms courts (bêta, mapper ``full.path=false``)."""

    def test_superadmin_en_nom_court_ne_donne_ni_ecriture_ni_lecture(self):
        groups = ["mirai-beta-testeurs", "superadmin", "/myrag/superadmin"]
        assert not access.can_write(name="victor", created_by="", user_groups=groups, user_sub="x")
        assert not access.can_read(name="victor", scope="private", scope_groups=[],
                                   created_by="", user_groups=groups, user_sub="x")

    def test_createur_garde_ses_droits(self):
        # Le créateur est reconnu par son `sub`, pas par ses groupes.
        groups = ["mirai-beta-testeurs"]
        assert access.can_write(name="victor", created_by=CREATOR_SUB, user_groups=groups, user_sub=CREATOR_SUB)

    def test_superadmin_en_chemins_complets(self):
        groups = ["/g/mirai-beta-testeurs", "/myrag/superadmin"]
        assert access.can_write(name="victor", created_by="", user_groups=groups, user_sub="x")
