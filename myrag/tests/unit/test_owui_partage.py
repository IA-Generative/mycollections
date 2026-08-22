"""Traduction de la portée d'une publication en autorisations OpenWebUI (>= 0.11).

Le piège que ces tests verrouillent : une collection publiée « pour tout le monde »
qui n'est en réalité visible que du compte portant la clé d'administration. Rien dans
la réponse d'OpenWebUI ne le signale — le modèle apparaît dans l'interface
d'administration, et nulle part ailleurs.
"""

from app.services.owui_client import grants_de_partage


def test_tout_le_monde_signifie_tout_compte_connecte():
    assert grants_de_partage("all", []) == [
        {"principal_type": "user", "principal_id": "*", "permission": "read"}
    ]


def test_jamais_d_acces_sans_authentification():
    """`anyone/*` ouvrirait la collection SANS connexion. On ne l'émet jamais — et le
    socle le retire de toute façon sur cette route, ce qui rendrait le partage muet."""
    for portee in ("all", "group", "private", ""):
        emis = grants_de_partage(portee, ["un-groupe"])
        assert all(g["principal_type"] != "anyone" for g in emis)


def test_portee_par_groupe():
    assert grants_de_partage("group", ["g1", "g2"]) == [
        {"principal_type": "group", "principal_id": "g1", "permission": "read"},
        {"principal_type": "group", "principal_id": "g2", "permission": "read"},
    ]


def test_portee_par_groupe_sans_groupe_ne_partage_rien():
    assert grants_de_partage("group", []) == []


def test_portee_privee_ne_partage_rien():
    assert grants_de_partage("private", ["g1"]) == []
