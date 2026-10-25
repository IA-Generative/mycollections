"""Les sites d'origine d'une collection : validation du champ, motif pour le plug-in, préfixe
commun des documents Résana, ajout idempotent aux sites déclarés."""

import asyncio

import pytest

from app.services import sources_url as m


def test_le_champ_prend_une_adresse_https_par_ligne():
    assert (
        m.valider_urls(" https://a.fake-domain.name/x \nhttps://b.fake-domain.name/, https://a.fake-domain.name/x\n") == "https://a.fake-domain.name/x\nhttps://b.fake-domain.name/"
    )
    assert m.valider_urls("") == "" and m.valider_urls(None) == "" and m.valider_urls(["https://a.fake-domain.name/"]) == "https://a.fake-domain.name/"


@pytest.mark.parametrize("brut", ["http://a.fake-domain.name/", "a.fake-domain.name", "https://", "https://a.fake-domain.name/a b"])
def test_une_adresse_qui_n_est_pas_https_est_refusee(brut):
    with pytest.raises(m.URLInvalide):
        m.valider_urls(brut)


def test_trop_d_adresses_ou_une_trop_longue():
    with pytest.raises(m.URLInvalide):
        m.valider_urls("\n".join(f"https://s{i}.fake-domain.name/" for i in range(11)))
    with pytest.raises(m.URLInvalide):
        m.valider_urls("https://a.fake-domain.name/" + "x" * 300)


def test_le_motif_couvre_l_hote():
    assert m.motif_de("https://WWW.Fake-Domain.name/guides/a.pdf?x=1") == "https://www.fake-domain.name/*"
    assert m.motif_de("http://a.fake-domain.name/") == "" and m.motif_de("") == ""


def test_le_prefixe_commun_des_documents_resana():
    urls = ["https://resana.fake-domain.name/espace-x/ged/1", "https://resana.fake-domain.name/espace-x/ged/2"]
    assert m.prefixe_commun(urls) == "https://resana.fake-domain.name/espace-x/ged/*"
    assert m.prefixe_commun(["https://resana.fake-domain.name/espace-x/ged/1", "https://resana.fake-domain.name/espace-y/ged/2"]) == "https://resana.fake-domain.name/*"
    assert m.prefixe_commun(["https://resana.fake-domain.name/e/ged/1"]) == "https://resana.fake-domain.name/e/ged/*"
    assert m.prefixe_commun(["https://a.fake-domain.name/1", "https://b.fake-domain.name/1"]) == ""
    assert m.prefixe_commun([]) == "" and m.prefixe_commun(["http://a.fake-domain.name/1"]) == ""


def test_l_ajout_aux_sites_declares_est_idempotent_et_garde_la_saisie(client, creer_collection, nom, en_tant_que):
    from app.services import sites
    from tests.conftest import personne

    creer_collection(nom)
    en_tant_que(personne("createur"))
    asyncio.run(sites.remplacer("collection", nom, ["https://saisi.fake-domain.name/*"]))
    assert asyncio.run(m.ajouter_sites(nom, ["https://resana.fake-domain.name/e/ged/*", "pas-un-motif"])) == [
        "https://saisi.fake-domain.name/*",
        "https://resana.fake-domain.name/e/ged/*",
    ]
    assert asyncio.run(m.ajouter_sites(nom, ["https://resana.fake-domain.name/e/ged/*"])) == ["https://saisi.fake-domain.name/*", "https://resana.fake-domain.name/e/ged/*"]
    assert client.get(f"/api/collections/{nom}/sites").json()["motifs"] == ["https://saisi.fake-domain.name/*", "https://resana.fake-domain.name/e/ged/*"]
    asyncio.run(sites.supprimer_cible("collection", nom))


def test_la_fiche_valide_les_sites_d_origine(client, creer_collection, nom, en_tant_que):
    from tests.conftest import personne

    assert creer_collection(nom, source_url="https://www.fake-domain.name/guides/")["source_url"] == "https://www.fake-domain.name/guides/"
    en_tant_que(personne("createur"))
    assert (
        client.patch(f"/api/collections/{nom}", json={"source_url": "https://a.fake-domain.name/\nhttps://b.fake-domain.name/"}).json()["source_url"]
        == "https://a.fake-domain.name/\nhttps://b.fake-domain.name/"
    )
    r = client.patch(f"/api/collections/{nom}", json={"source_url": "http://a.fake-domain.name/"})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "source_url"
    r = client.post("/api/collections", json={"name": f"{nom}-x", "scope": "private", "source_url": "ftp://x"})
    assert r.status_code == 422
