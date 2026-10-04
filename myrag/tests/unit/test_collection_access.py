"""Tests du contrôle d'accès par groupe (app.services.access)."""

import pytest

from app.services import access


# Groupes typiques (chemins Keycloak)
G_SUPER = "/g/administration-de-test"
G_USER1 = "/myrag/collec-user1"
G_USER1_ADMIN = "/myrag/collec-user1-admin"
G_AUDIT = "/myrag/collec-audit"


class TestVisibility:
    def test_superadmin_sees_all(self):
        assert access.visible_collection_names([G_SUPER]) is None
        assert access.writable_collection_names([G_SUPER]) is None

    def test_member_sees_only_own(self):
        names = access.visible_collection_names([G_USER1])
        assert names == {"collec-user1"}

    def test_admin_group_grants_read_and_write(self):
        groups = [G_USER1_ADMIN]
        assert access.visible_collection_names(groups) == {"collec-user1"}
        assert access.writable_collection_names(groups) == {"collec-user1"}

    def test_member_cannot_write(self):
        groups = [G_USER1]  # membre simple, pas -admin
        assert access.writable_collection_names(groups) == set()

    def test_no_group_sees_nothing(self):
        assert access.visible_collection_names([]) == set()
        assert access.visible_collection_names(None) == set()

    def test_groups_outside_root_ignored(self):
        groups = ["/autre/chose", "/myrag", "/myrag/a/b"]
        assert access.visible_collection_names(groups) == set()

    def test_paths_without_leading_slash_refused(self):
        # Keycloak en full.path=true émet toujours un « / » initial. Sans lui, c'est un
        # NOM de groupe — et un nom peut contenir « / » : aucun droit.
        assert access.visible_collection_names(["myrag/collec-user1"]) == set()
        assert access.is_superadmin(["myrag/superadmin"]) is False


class TestPredicates:
    def test_auditeur_cannot_read_user1(self):
        # Le bug signalé : auditeur1 (groupe collec-audit) ne doit PAS voir collec-user1
        groups = [G_AUDIT]
        assert access.can_read_collection("collec-audit", groups) is True
        assert access.can_read_collection("collec-user1", groups) is False

    def test_superadmin_reads_and_writes_anything(self):
        assert access.can_read_collection("whatever", [G_SUPER]) is True
        assert access.can_write_collection("whatever", [G_SUPER]) is True

    def test_member_read_not_write(self):
        groups = [G_USER1]
        assert access.can_read_collection("collec-user1", groups) is True
        assert access.can_write_collection("collec-user1", groups) is False

    def test_any_authenticated_user_can_create(self):
        # Créer sa collection = action utilisateur (multi-tenant), pas réservée aux ops.
        assert access.can_create_collection([G_SUPER]) is True
        assert access.can_create_collection([G_USER1_ADMIN]) is True
        assert access.can_create_collection([G_USER1]) is True  # membre simple : OK
        assert access.can_create_collection([]) is True


class TestFormeDeLaBeta:
    """Mapper Keycloak en ``full.path=false`` (bêta) : le claim porte des noms courts.

    Le realm de la bêta laisse ses utilisateurs créer leurs groupes (keycloak-comu,
    sous ``/g``) : tout nom court y est forgeable. On n'en tire donc aucun droit.
    """

    COURTS = ["mirai-beta-testeurs", "Admins"]

    def test_nom_court_superadmin_refuse(self):
        assert access.is_superadmin(self.COURTS + ["superadmin"]) is False

    def test_homonyme_imitant_un_chemin_refuse(self):
        # Groupe keycloak-comu NOMMÉ « /myrag/superadmin » : en noms courts, le claim
        # porte cette valeur, mais aussi le groupe exigé des testeurs, sans « / ».
        forge = self.COURTS + ["/g/administration-de-test", "/myrag/collec-user1-admin"]
        assert access.is_superadmin(forge) is False
        assert access.writable_collection_names(forge) == set()
        assert access.visible_collection_names(forge) == set()

    def test_groupe_de_collection_en_nom_court_ignore(self):
        groups = self.COURTS + ["collec-user1", "collec-user1-admin"]
        assert access.visible_collection_names(groups) == set()
        assert access.can_write_collection("collec-user1", groups) is False


class TestCheminsCompletsDeLaBeta:
    """Même realm, mapper basculé en ``full.path=true``."""

    TESTEUR = "/g/mirai-beta-testeurs"

    def test_superadmin_reconnu(self):
        assert access.is_superadmin([self.TESTEUR, G_SUPER]) is True
        assert access.can_write_collection("nimporte", [self.TESTEUR, G_SUPER]) is True

    def test_homonyme_hors_perimetre_refuse(self):
        # Ce que keycloak-comu permet de créer : tout vit sous /g.
        forge = [self.TESTEUR, "/g/superadmin", "/g/myrag/superadmin", "/g/x/collec-user1-admin"]
        assert access.is_superadmin(forge) is False
        assert access.writable_collection_names(forge) == set()
        assert access.visible_collection_names(forge) == set()

    def test_groupes_de_collection_reconnus(self):
        groups = [self.TESTEUR, G_USER1, "/myrag/collec-b-admin"]
        assert access.visible_collection_names(groups) == {"collec-user1", "collec-b"}
        assert access.writable_collection_names(groups) == {"collec-b"}
        assert access.can_write_collection("collec-user1", groups) is False

    def test_chemins_rend_le_claim_ou_rien(self):
        assert access.chemins([self.TESTEUR, G_SUPER]) == [self.TESTEUR, G_SUPER]
        assert access.chemins([self.TESTEUR, "superadmin"]) == []
        assert access.chemins(None) == []


class TestSuperadminParVariable:
    """MYRAG_SUPERADMIN_GROUPES remplace le groupe codé en dur /myrag/superadmin."""

    def test_seuls_les_chemins_configures_comptent(self):
        assert access.is_superadmin(["/g/administration-de-test"]) is True
        assert access.is_superadmin(["/myrag/superadmin"]) is False, "l'ancien groupe ne donne plus rien"
        assert access.is_superadmin(["/g/administration-de-test/sous-groupe"]) is False

    def test_une_liste_de_plusieurs_groupes(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "myrag_superadmin_groupes", "/g/a , /g/b, nom-court")
        assert access.is_superadmin(["/g/b"]) is True
        assert access.is_superadmin(["/x/nom-court"]) is False
        assert access.groupes_superadmin() >= {"/g/a", "/g/b"}

    def test_vide_personne_n_est_superadmin_sauf_le_developpeur_sans_authentification(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "myrag_superadmin_groupes", "")
        assert access.is_superadmin([access.GROUPE_DEV]) is True  # AUTH_ENABLED=false dans les tests
        monkeypatch.setattr(settings, "auth_enabled", True)
        assert access.is_superadmin([access.GROUPE_DEV]) is False
