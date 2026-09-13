"""Les six connecteurs d'amorces, sans réseau : des fichiers d'exemple entrent, des
documents et une couverture sortent ; rejouer n'ingère rien deux fois ; le RNE ne
laisse passer aucun nom."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import AsyncMock, patch

import pytest

from app.services.amorces import baac, ingestion, justice_administrative as ja, natinf, reseau, rne, sdis, ssmsi
from app.services.amorces.tabulaire import lire_csv, nombre

SSMSI = ('﻿"Code_departement";"Code_region";"annee";"indicateur";"unite_de_compte";"nombre";"taux_pour_mille";"insee_pop";"insee_pop_millesime";"insee_log";"insee_log_millesime"\n'
         '"01";"84";"2016";"Homicides";"Victime";"5";"0,0078318";"638425";"2016";"308491";"2016"\n'
         '"01";"84";"2017";"Homicides";"Victime";"7";"0,0108";"640000";"2017";"309000";"2017"\n'
         '"02";"32";"2016";"Homicides";"Victime";"10";"0,0186520";"536136";"2016";"264180";"2016"\n'
         '"02";"32";"2016";"Vols de véhicules";"Véhicule";"1 234";"2,3";"536136";"2016";"264180";"2016"\n').encode("utf-8")
SDIS_2024 = "Année;Zone;Région;Numéro;Département;Catégorie A;Incendies;Secours à personne;Accidents de circulation;Risques technologiques;Opérations diverses;Total interventions\n2024;Sud-est;Auvergne-Rhône-Alpes;1;Ain;B;2 183;35 396;2 982;378;4 196;45 135\n2024;Nord;Hauts-de-France;2;Aisne;B;2 694;31 056;2 129;475;4 321;40 675\n".encode("cp1252")
CARACT = '"Num_Acc";"jour";"mois";"an";"hrmn";"lum";"dep";"com";"agg";"int";"atm";"col";"adr";"lat";"long"\n"202400000001";"25";"03";"2024";"07:40";"2";"70";"70285";"1";"1";"5";"1";"D438";"47,5";"6,7"\n"202400000002";"20";"03";"2024";"15:05";"1";"21";"21054";"2";"3";"7";"6";"RUE";"47,0";"4,8"\n"202400000003";"22";"04";"2024";"19:30";"2";"70";"70285";"2";"1";"1";"6";"Allée";"44,9";"2,4"\n'.encode()
USAGERS = '"Num_Acc";"id_usager";"grav"\n"202400000001";"a";"2"\n"202400000001";"b";"4"\n"202400000003";"c";"3"\n'.encode()
MAIRES = ("Code du département;Libellé du département;Code de la commune;Libellé de la commune;Nom de l'élu;Prénom de l'élu;Code sexe;Date de naissance;Code de la catégorie socio-professionnelle;Libellé de la catégorie socio-professionnelle;Date de début du mandat;Date de début de la fonction\n"
          "01;Ain;01001;L'Abergement-Clémenciat;EVALET TAPONAT;Line;F;1967-07-22;38;Ingénieur;2026-03-15;2026-03-23\n"
          "01;Ain;01002;L'Abergement-De-Varey;COUROUBLE;François;M;1958-02-21;31;Profession libérale;2026-03-15;2026-03-20\n").encode()
CM = ("Code du département;Libellé du département;Code de la commune;Libellé de la commune;Nom de l'élu;Prénom de l'élu;Code sexe;Date de naissance;Date de début du mandat;Libellé de la fonction;Date de début de la fonction;Code nationalité\n"
      "01;Ain;01001;L'Abergement-Clémenciat;DUPONT;Jean;M;1970-01-01;2026-03-15;;;FR\n01;Ain;01001;L'Abergement-Clémenciat;MARTIN;Anne;F;1980-01-01;2026-03-15;;;FR\n").encode()
NATINF = "Numéro NATINF;Nature de l'infraction;Qualification de l'infraction;Définie par;Réprimée par\n7;Délit;RETRAIT DE LA PROVISION D'UN CHEQUE;ART.L.163-2 C.M.F.;ART.L.163-2 AL.1 C.M.F.\n8;Délit;OPPOSITION AU PAIEMENT D'UN CHEQUE;ART.L.163-2 C.M.F.;ART.L.163-6 C.M.F.\n".encode("cp1252")


def _xml(numero, date, juridiction, code, texte, publication="C"):
    return f'''﻿<?xml version="1.0" encoding="UTF-8" ?>
<Document><Donnees_Techniques><Identification>DCA_{numero}_{date.replace('-', '')}.xml</Identification></Donnees_Techniques>
<Dossier><Code_Juridiction>{code}</Code_Juridiction><Nom_Juridiction>{juridiction}</Nom_Juridiction><Numero_Dossier>{numero}</Numero_Dossier>
<Date_Lecture>{date}</Date_Lecture><Type_Decision>Arrêt</Type_Decision><Type_Recours>excès de pouvoir</Type_Recours><Code_Publication>{publication}</Code_Publication><Solution>Rejet</Solution></Dossier>
<Decision><Texte_Integral><p>Vu la procédure suivante :</p><p>{texte}</p></Texte_Integral></Decision></Document>'''.encode("utf-8")


def _zip(*fichiers):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for nom, contenu in fichiers:
            z.writestr(nom, contenu)
    return tampon.getvalue()


ZIP_CAA = _zip(("DCA_24LY00001_20240110.xml", _xml("24LY00001", "2024-01-10", "Cour administrative d'appel de Lyon", "CAA69", "Refus de titre de séjour sur le fondement du CESEDA.")),
               ("DCA_24BX00002_20240112.xml", _xml("24BX00002", "2024-01-12", "Cour administrative d'appel de Bordeaux", "CAA33", "Marché public de travaux, résiliation.")),
               ("DCA_24MA00003_20240115.xml", _xml("24MA00003", "2024-01-15", "Cour administrative d'appel de Marseille", "CAA13", "Obligation de quitter le territoire français contestée.", "D")))


@pytest.fixture
def sans_reseau(monkeypatch):
    """`reseau.telecharger` sert des octets par URL ; OpenRAG accepte tout."""
    fichiers: dict[str, bytes] = {}

    async def _tele(url, **k):
        if url not in fichiers:
            raise RuntimeError(f"404 introuvable : {url}")
        return fichiers[url]
    monkeypatch.setattr(reseau, "telecharger", _tele)
    with patch("app.services.amorces.ingestion.OpenRAGClient") as cls:
        cls.return_value.create_partition = AsyncMock(return_value={})
        cls.return_value.upload_chunk = AsyncMock(return_value={"ok": True})
        fichiers["_client"] = cls.return_value  # type: ignore[assignment]
        yield fichiers


class TestTabulaire:
    def test_nombres_a_la_francaise(self):
        assert nombre("1 786") == 1786 and nombre("0,0078") == 0.0078 and nombre("") is None and nombre("1 234") == 1234

    def test_encodage_cp1252_et_bom(self):
        assert lire_csv(SDIS_2024)[0]["Département"] == "Ain"
        assert lire_csv(SSMSI)[0]["Code_departement"] == "01"

    def test_encodage_cp850_de_la_liste_natinf(self):
        """Le fichier officiel est en DOS (é = 0x82) : relu en cp1252 il donnerait « Num‚ro »."""
        octets = "Numéro NATINF;Nature de l'infraction\n7;Délit\n".encode("cp850")
        lignes = lire_csv(octets)
        assert lignes[0]["Numéro NATINF"] == "7" and lignes[0]["Nature de l'infraction"] == "Délit"
        assert natinf.numero(lignes[0]) == "7"


class TestDocuments:
    def test_ssmsi_un_document_par_departement(self):
        docs, couv = ssmsi.documents_depuis(lire_csv(SSMSI))
        assert [d.nom for d in docs] == ["ssmsi-departement-01.md", "ssmsi-departement-02.md"]
        assert "| 2016 | 5 | 0,01 |" in docs[0].texte and "1 234" in docs[1].texte
        assert couv["annees"] == ["2016", "2017"] and couv["departements"] == 2

    def test_sdis_annees_en_lignes(self):
        docs, couv = sdis.documents_depuis({"2024": lire_csv(SDIS_2024)})
        assert docs[0].nom == "sis-1.md" and "| 2024 | 2 183 | 35 396 | 2 982 | 378 | 4 196 | 45 135 |" in docs[0].texte
        assert couv["departements"] == 2

    def test_baac_agrege_sans_usager(self):
        docs, couv = baac.documents_depuis("2024", lire_csv(CARACT), lire_csv(USAGERS))
        d70 = next(d for d in docs if d.nom == "baac-2024-departement-70.md")
        assert "Accidents corporels : 2" in d70.texte and "Tués : 1" in d70.texte and "blessés hospitalisés : 1" in d70.texte
        assert "- 70285 : 2" in d70.texte and "id_usager" not in d70.texte and couv["accidents"] == 3

    def test_natinf_une_fiche_par_code(self):
        docs, couv = natinf.documents_depuis(lire_csv(NATINF), {"7": {"peines_principales": [{"display_description": "5 ans d'emprisonnement"}]}})
        assert len(docs) == 1 and docs[0].nom == "natinf-00007-00008.md"
        assert "## NATINF 7 — RETRAIT" in docs[0].texte and "5 ans d'emprisonnement" in docs[0].texte and couv["codes"] == 2

    def test_rne_ne_laisse_passer_aucun_nom(self):
        docs, couv = rne.documents_depuis({"maires": lire_csv(MAIRES), "conseillers_municipaux": lire_csv(CM)})
        t = docs[0].texte
        for interdit in ("EVALET", "Line", "COUROUBLE", "1967", "DUPONT", "MARTIN", "Ingénieur", "FR;"):
            assert interdit not in t, interdit
        assert "| 01001 | L'Abergement-Clémenciat | 2026-03-15 | 2026-03-23 | 2 |" in t
        assert "maires : 2 (femmes : 1, hommes : 1)" in t
        assert "Nom de l'élu" in couv["colonnes_ecartees"]


class TestJusticeAdministrative:
    def test_urls_et_mois(self):
        assert ja.url_du_mois("DTA", 2024, 1) == "https://opendata.justice-administrative.fr/DTA/2024/01/TA_202401.zip"
        assert ja.url_du_mois("DCA", 2024, 12).endswith("/DCA/2024/12/CAA_202412.zip")
        from datetime import date
        assert ja.mois_entre("2024-11", date(2025, 2, 10)) == [(2024, 11), (2024, 12), (2025, 1)]

    def test_le_filtre_par_mots_cles_et_publication(self):
        decisions = ja.decisions_du_zip(ZIP_CAA)
        assert len(decisions) == 3 and decisions[0]["juridiction"].startswith("Cour administrative d'appel de Lyon")
        gardees = [d for d in decisions if ja.retenue(d, ["ceseda", "quitter le territoire"], None)]
        assert {d["numero"] for d in gardees} == {"24LY00001", "24MA00003"}
        assert [d["numero"] for d in decisions if ja.retenue(d, ["ceseda", "quitter le territoire"], ["A", "B", "C"])] == ["24LY00001"]
        doc = ja.document_depuis(gardees[0], "DCA")
        assert doc.nom == "CAA-24LY00001-2024-01-10.md" and "## Texte intégral" in doc.texte and "<p>" not in doc.texte

    @pytest.mark.asyncio
    async def test_import_incremental_par_mois(self, sans_reseau, creer_collection, nom, monkeypatch):
        from datetime import date
        monkeypatch.setattr(ja, "date", type("D", (), {"today": staticmethod(lambda: date(2024, 4, 1))}))
        sans_reseau[ja.url_du_mois("DCA", 2024, 1)] = ZIP_CAA
        sans_reseau[ja.url_du_mois("DCA", 2024, 2)] = ZIP_CAA
        creer_collection(nom)
        entree = {"parametres": {"fonds": ["DCA"], "depuis": "2024-01", "mots_cles": ["CESEDA"], "max_mois_par_run": 1}}
        r1 = await ja.importer(nom, entree)
        assert r1["mois_importes"] == ["DCA-202401"] and r1["documents"] == 1 and r1["couverture"]["juridictions"] == ["CAA69"]
        r2 = await ja.importer(nom, entree, deja_importes=r1["couverture"]["mois_importes"])
        assert r2["mois_importes"] == ["DCA-202402"] and r2["ignores"] == 1, "même décision : ignorée, pas réingérée"
        assert r2["couverture"]["mois_importes"] == ["DCA-202401", "DCA-202402"] and r2["couverture"]["reste_a_importer"] == 1


@pytest.mark.asyncio
async def test_l_ingestion_est_idempotente(sans_reseau, creer_collection, nom):
    creer_collection(nom)
    docs = [ingestion.Document("a.md", "# A\n\ntexte a"), ingestion.Document("b.md", "# B\n\ntexte b")]
    b1 = await ingestion.ingerer(nom, docs)
    assert b1["documents"] == 2 and b1["ignores"] == 0 and b1["morceaux"] >= 2
    b2 = await ingestion.ingerer(nom, docs)
    assert b2["documents"] == 0 and b2["ignores"] == 2
    b3 = await ingestion.ingerer(nom, [ingestion.Document("a.md", "# A\n\ntexte a modifié")])
    assert b3["documents"] == 1 and b3["versions"] == 1
    import os, sqlite3
    con = sqlite3.connect(os.environ["DATABASE_URL"].split("///")[-1])
    assert con.execute("SELECT count(*) FROM source_files WHERE collection_name=?", (nom,)).fetchone()[0] == 2
    con.close()


@pytest.mark.asyncio
async def test_le_connecteur_ssmsi_de_bout_en_bout(sans_reseau, creer_collection, nom):
    creer_collection(nom)
    sans_reseau["https://x/dep.csv"] = SSMSI
    r = await ssmsi.importer(nom, {"parametres": {"url_departemental": "https://x/dep.csv"}})
    assert r["documents"] == 2 and r["lignes_importees"] == 4 and r["couverture"]["departements"] == 2
    assert sans_reseau["_client"].upload_chunk.await_count >= 2
