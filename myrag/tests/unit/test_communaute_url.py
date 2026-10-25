"""Le lien vers Communauté (créer un groupe) : donné à l'écran par /api/config, en https seulement."""

import pytest


@pytest.mark.parametrize(
    ("posee", "rendue"),
    [
        ("https://communaute.fake-domain.name/", "https://communaute.fake-domain.name"),
        ("http://communaute.fake-domain.name", ""),
        ("", ""),
    ],
)
def test_le_lien_communaute_n_est_donne_qu_en_https(client, monkeypatch, posee, rendue):
    from app.config import settings

    monkeypatch.setattr(settings, "communaute_url", posee)
    assert client.get("/api/config").json()["communaute_url"] == rendue
