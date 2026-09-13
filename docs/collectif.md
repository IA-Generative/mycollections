# Le collectif — modèle, états, routes, fil d'avancement

Décision : [ADR-0001](adr/ADR-0001-collections-collaboratives-modele-et-etats.md).
Code : `app/models/db.py` (tables), `app/services/etats.py` (règles, module pur),
`app/services/collectif_store.py` (écritures), `app/routers/{demandes,collectif,amorces}.py`.

## Les tables

| table | ce qu'elle porte | clé |
|---|---|---|
| `demande` | titre, usage, fréquence, service, **acces_actuel**, **recontact** (+ `contact` consenti), état, **seuil figé**, condensé de l'auteur, lien amorce/collection, clôture motivée | `id` (uuid) |
| `soutien` | rôle ∈ soutien · fournisseur · relecteur · garant, temps déclaré (min) | `(demande_id, sub_hash)` |
| `abonnement` | qui reçoit le fil d'une demande ou d'une collection | `(objet_type, objet_id, sub_hash)` |
| `proposition` | cible (ligne Grist / fichier), avant, après, justification, source, état, motif de refus | `id` |
| `signalement` | motif ∈ obsolete · erreur · manquant, texte, fichier, état de traitement | `id` |
| `grille_controle` | source/licence, données perso, fraîcheur, relecteurs (condensés), couverture constatée | `collection_name` |
| `evenement` | le fil : objet, type, personne **ou** robot, détail chiffré | `id` |
| `amorce` | l'état d'import d'une entrée du catalogue `app/amorces/catalogue.json` | `id` (slug) |

Sur `collections` : `etat_collab`, `garant_hash`, `garant_pressenti`, `demande_id`.
Aucun `sub` en clair dans ces tables ; le `contact` n'existe que si `recontact` (CHECK).

## Les états

- **Demande** : `ouverte` → `chantier` (N soutiens distincts ET un garant, calculé par le
  serveur, seuil figé à la création) → `realisee` (sa collection est publiée à tous) ;
  `close` avec doublon ou motif. « en sommeil » = chantier sans événement depuis
  `SOMMEIL_JOURS` (30), calculé à la lecture.
- **Collection** : `amorcee` → `en_controle` → `publiee_groupe` → `publiee_tous`, une
  étape à la fois ; retour `publiee_tous` → `publiee_groupe` permis ; `publiee_tous`
  exige la grille complète (3 champs + 1 relecture). Un superadmin peut **forcer**
  (`forcer: true`, motif) : l'événement le dit.
- Non `publiee_tous` : `POST /publish` refuse `visibility: all` (422, sauf brouillon), la
  description envoyée au socle est préfixée « ⚠ en cours de vérification », le bac à
  sable préfixe sa réponse et rend `mention`.

## Les routes

Toutes sous jeton ; l'identité est condensée (`MYRAG_PSEUDO_SEL`, sinon 503).
`demandes: false` ou `signalements: false` dans `capacites.json` ⇒ 404.

```
GET    /api/demandes?etat=&q=            liste enrichie ; q ⇒ demandes proches (dédoublonnage)
POST   /api/demandes                     201 ; titre, usage, frequence, service, acces_actuel, recontact, contact?, amorce_id?
GET    /api/demandes/{id}                fiche : nb_soutiens, garant, roles, sommeil, soutenue_par_moi, mon_role, abonne
PATCH  /api/demandes/{id}                auteur ou superadmin ; jamais `etat`
POST   /api/demandes/{id}/soutenir       {role, temps_declare_min?} — recalcul d'état serveur ; 409 si second garant
DELETE /api/demandes/{id}/soutenir
DELETE /api/demandes/{id}/garant         superadmin
POST|DELETE /api/demandes/{id}/abonner
GET    /api/demandes/{id}/journal?limite=&avant=
POST   /api/demandes/{id}/clore          {doublon_de | motif}

GET    /api/collections/{n}/etat         etat, mention, garant, je_suis_garant, transitions_possibles
POST   /api/collections/{n}/etat         {cible, forcer?, motif?} garant ; forcer = superadmin
GET|PUT /api/collections/{n}/grille      servie même vide ; PUT garant
POST   /api/collections/{n}/grille/relire   l'appelant devient relecteur
GET|POST /api/collections/{n}/propositions  ; GET .../{id} (+ historique)
POST   /api/collections/{n}/propositions/{id}/publier | /refuser {motif}   garant
GET|POST /api/collections/{n}/signalements ; POST .../{id}/traiter {etat}  garant
GET    /api/collections/{n}/journal
POST|DELETE /api/collections/{n}/abonner

GET    /api/amorces                      catalogue + état d'import
POST   /api/amorces/{id}/import          superadmin ; idempotent ; 501 nommé tant que le connecteur manque
GET    /api/config                       + demandes, signalements, seuil_chantier
```

## Le fil d'avancement — contrat partagé (lots 4 et 6)

Un événement : `{id, objet_type, objet_id, collection, type, par, detail, cree_le}` où
`par` vaut `personne` ou `robot:<nom>`. Types émis :

| objet | types |
|---|---|
| demande | `demande.creee`, `demande.modifiee`, `soutien.ajoute` {role, temps_declare_min, nb_soutiens}, `soutien.retire`, `garant.retire`, `seuil.atteint` {soutiens, seuil, garant}, `demande.etat` {de, vers}, `collection.purgee` |
| collection | `collection.creee`, `collection.etat` {de, vers, force?, motif?}, `grille.maj`, `grille.relue`, `proposition.*`, `signalement.*`, `publication.publiee` / `publication.brouillon` / `publication.retiree`, `collection.archivee` / `.desarchivee`, `import.termine` {fichiers, morceaux, morceaux_en_echec} |
| proposition | `proposition.deposee`, `proposition.publiee`, `proposition.refusee` {motif} |
| signalement | `signalement.depose`, `signalement.traite` {de, vers} |
| synchronisation | `source.enregistree`, `synchro.terminee` {source, fichiers} |

## Réglages

| variable | défaut | rôle |
|---|---|---|
| `MYRAG_PSEUDO_SEL` | vide (⇒ 503) | sel HMAC des identités — le même que `obs-pseudo-salt` du bus |
| `CAPACITES_URL` | vide | `http://apps-menu.apps-menu.svc.cluster.local/_beta/capacites.json` en bêta |
| `SEUIL_CHANTIER_DEFAUT` | 5 | repli si le menu ne répond pas |
| `SOMMEIL_JOURS` | 30 | seuil du « en sommeil » |

## Tests

`cd myrag && python3 -m pytest tests/unit -v` — un fichier par règle
(`test_regle1_usage_frequence.py` … `test_regle5_capacites.py`), plus `test_journal.py`,
`test_pseudo.py`, `test_doublons.py`, `test_amorces.py`, `test_non_regression.py`.
`tests/conftest.py` isole la base (SQLite propre par session) et joue le cycle de vie.

## Les amorces (lot 0)

Catalogue : `myrag/app/amorces/catalogue.json` — six entrées, dans l'ordre de la note,
chacune avec sa source, son garant pressenti, sa grille pré-remplie (source/licence,
données personnelles, fraîcheur), ses paramètres et ses vingt questions de test.
Connecteurs : `myrag/app/services/amorces/` (un module par source, registre dans
`__init__.py`). Import : `POST /api/amorces/{id}/import` (superadmin ; `?synchrone=true`
pour attendre ; 409 si déjà en cours) ou, depuis le pod,
`python -m app.services.amorces.cli {id} [--max-documents N]`.

| amorce | source réelle | documents produits | données personnelles |
|---|---|---|---|
| `natinf` | liste officielle NATINF (ministère de la Justice, data.gouv.fr) + fiches natinfo.app par lots de 50 si `NATINFO_API_KEY` et `enrichir_max` | un document par tranche de 200 codes, une section par code | aucune |
| `ssmsi-delinquance` | base départementale SSMSI (csv) | un document par département, un tableau par indicateur | aucune (agrégats) |
| `ta-caa-ceseda` | ZIP mensuels XML `/DCA/AAAA/MM/CAA_AAAAMM.zip`, `/DTA/…/TA_…zip` | une décision retenue = un document (en-tête + texte intégral) ; filtre par mots-clés et code de publication ; **2 mois par appel**, mémoire des mois faits dans `amorce.detail_json` | pseudonymisées à la source |
| `rne-elus` | RNE, six fichiers de mandats | un document par département : effectifs par mandat (F/H), par commune dates de mandat/fonction du maire et nombre de conseillers | **colonnes nominatives jamais lues** (nom, prénom, naissance, CSP, nationalité) — la couverture les nomme |
| `sdis-interventions` | interventions SIS 2019–2024 (csv cp1252) | un document par SIS, années en lignes, familles en colonnes | aucune |
| `baac` | BAAC 2019–2024 (caractéristiques + usagers) | un document par département et par an : accidents, tués, blessés, en/hors agglo, communes les plus touchées, mois | comptages seuls |

Chaque import est **idempotent** (`SourceFile` nom + empreinte : même contenu ignoré,
contenu changé = nouvelle version), écrit la **couverture constatée** dans la grille
(`couverture_json`, robot `amorce:<id>`), pose les vingt questions en banque une seule
fois, et laisse `import.termine` / `import.echoue` dans le fil. Le critère d'ouverture
de la section collaborative est servi par `GET /api/amorces` : `ouverture.ouverte` dès
que **3 des 6** collections d'amorce sont au moins `en_controle`.

Sorties réseau à ouvrir côté cluster : `static.data.gouv.fr`, `natinfo.app`,
`opendata.justice-administrative.fr` (443).

## Les écrans (lot 3, option A)

Front Nuxt 4 + DSFR, `myrag/frontend/` :

- **Onglet « Demandes de la communauté »** (`pages/demandes/index.vue`, `[id].vue`) : seuil
  affiché (lu dans `/_beta/capacites.json`, repli `/api/config`), formulaire avec
  dédoublonnage en tapant (`GET /api/demandes?q=`), colonne « Je peux aider » (rôles et
  coût en temps, `utils/collectif.ts::ROLES`), « Moi aussi » sans rechargement, badge
  « en sommeil », fiche avec le fil d'avancement et l'abonnement.
- **Fiche collection** (`pages/c/[id]/index.vue`) : parcours des quatre états en tête
  (`components/collectif/EtapesCollection.vue`, boutons du garant seul, forçage sous
  `<details>` pour l'administration avec motif obligatoire), mention « en cours de
  vérification », onglets **Consulter** (grille de contrôle toujours affichée, même
  vide, « Je relis cette collection ») / **Signaler un défaut** / **Proposer une
  modification** (avant/après, justification, source facultative ; publier/refuser
  visibles du garant seul) / **Historique** (le fil) / **Discussion** (renvoi aux forums,
  abonnement) / System Prompt.
- **Page Publier** : « Tout le monde » désactivé tant que la collection n'est pas
  publiée à tous, avec le pourquoi et le lien vers la fiche.
- **Guide « Soyez acteurs vous-mêmes »** (`pages/guide/`) : cinq pages Markdown servies
  par `GET /api/guide`, rendues en DSFR (`marked` + DOMPurify), liées depuis la
  navigation, le bloc « Comment ça se passe » de l'accueil et chaque écran ; indexées
  comme collection `guide-soyez-acteurs` (amorce `guide`), ouvertes aux propositions.
- **Administration → Amorces** (`pages/admin/amorces.vue`) : le catalogue, l'état
  d'import, le bouton Importer, le critère d'ouverture (3 sur 6).
- **Règle 5** : `composables/useCapacites.ts` — un drapeau n'est vrai que s'il vaut
  `true` ; l'onglet des demandes, le bloc de l'accueil et le formulaire de signalement
  n'apparaissent qu'avec la capacité déclarée.

Tests : `cd myrag/frontend && npm test` (`tests/unit/collectif.test.ts`) ;
`npx nuxt build` doit passer.
