"""Tests du contrôle d'accès par groupe (app.services.access)."""

import pytest

from app.services import access


# Groupes typiques (chemins Keycloak)
G_SUPER = "/myrag/superadmin"
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

    def test_paths_without_leading_slash(self):
        # Keycloak peut émettre les groupes sans slash initial
        assert access.visible_collection_names(["myrag/collec-user1"]) == {"collec-user1"}


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

    def test_can_create_requires_operator(self):
        assert access.can_create_collection([G_SUPER]) is True
        assert access.can_create_collection([G_USER1_ADMIN]) is True
        assert access.can_create_collection([G_USER1]) is False  # membre simple
        assert access.can_create_collection([]) is False
