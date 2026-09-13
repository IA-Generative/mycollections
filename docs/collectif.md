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
