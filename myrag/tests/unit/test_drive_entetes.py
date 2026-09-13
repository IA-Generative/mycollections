"""En-têtes d'appel à Drive quand on passe par son service interne.

Deux en-têtes, deux pannes muettes évitées : sans `Host`, Drive répond « Bad Request
(400) » en HTML nu ; sans `X-Forwarded-Proto`, il redirige en 301 vers son adresse
publique — que l'appelant suit, retombant sur ce qu'on voulait éviter.
"""

from app.services.connectors.drive import DriveClient, _entetes


def test_sans_hote_public_rien_n_est_ajoute():
    assert _entetes("j3t0n", None) == {"Authorization": "Bearer j3t0n"}
    assert _entetes("j3t0n", "") == {"Authorization": "Bearer j3t0n"}


def test_avec_hote_public_les_deux_entetes_sont_poses():
    e = _entetes("j3t0n", "mesfichiers.numerique-interieur.com")
    assert e["Authorization"] == "Bearer j3t0n"
    assert e["Host"] == "mesfichiers.numerique-interieur.com"
    assert e["X-Forwarded-Proto"] == "https"


def test_le_client_les_transmet():
    c = DriveClient("http://drive-backend.drive.svc.cluster.local", "j3t0n",
                    public_host="mesfichiers.numerique-interieur.com")
    entetes = c._client.headers
    assert entetes["host"] == "mesfichiers.numerique-interieur.com"
    assert entetes["x-forwarded-proto"] == "https"
    # L'adresse jointe reste celle du service interne : c'est tout l'intérêt.
    assert "drive-backend.drive" in str(c._client.base_url)
