"""Le lien d'installation de « MirAI Assistant pour navigateur » (page du device management) :
donné à l'écran par /api/config, en https seulement."""

import pytest


@pytest.mark.parametrize(
    ("posee", "rendue"),
    [
        ("https://dm.fake-domain.name/installer", "https://dm.fake-domain.name/installer"),
        ("http://dm.fake-domain.name/installer", ""),
        ("", ""),
    ],
)
def test_le_lien_d_installation_n_est_donne_qu_en_https(client, monkeypatch, posee, rendue):
    from app.config import settings

    monkeypatch.setattr(settings, "navigateur_installation_url", posee)
    assert client.get("/api/config").json()["navigateur_installation_url"] == rendue
