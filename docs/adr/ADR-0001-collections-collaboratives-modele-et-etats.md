# ADR-0001 — Les collections collaboratives : modèle, états et identités

- **Statut** : Accepted
- **Date** : 2026-09-13
- **Décideurs** : PO bêta (eric.tiquet), chantier « collections collaboratives » (Mes collections × barre commune × suivi)
- **Sujet** : permettre aux agents de dire quel jeu de données leur manque, de se rassembler pour le constituer, de signaler un jeu défaillant et de proposer des modifications — amorcé depuis l'open data, contrôlé avant diffusion large.

## Contexte

Mes collections savait créer, indexer et publier une collection ; elle ne savait ni
recueillir un besoin, ni faire porter un jeu par un collectif, ni tracer ce qui lui
arrive. Six principes non négociables cadrent le chantier :

1. une demande porte un usage et une fréquence, jamais un score ;
2. un chantier ne démarre qu'à N soutiens **et** un garant ; N vit dans `capacites.json` ;
3. une collection va `amorcee → en_controle → publiee_groupe → publiee_tous` ; non
   publiée à tous, elle n'est jamais servie hors de son groupe et ses réponses portent
   la mention « en cours de vérification » ;
4. proposer une modification est ouvert à tout utilisateur authentifié ; publier est
   réservé au garant ; chaque modification a un avant/après, une justification, une
   source facultative, un historique, un refus motivé ;
5. aucun bouton n'apparaît si le service ne sait pas le faire ;
6. chaque écran de suivi ouvre par un verdict ; une mesure absente n'est jamais un bon verdict.

Trois faits du code contraignaient le modèle : pas d'Alembic (`create_all` + micro-
migrations), aucune pseudonymisation (`created_by` porte le `sub` en clair), aucun
journal générique.

## Options considérées

### Identité : condensé avec le sel du bus (retenue) / sel propre / sub en clair
- **Même sel** (`obs-pseudo-salt` → `MYRAG_PSEUDO_SEL`) : un abonné a le même condensé
  ici et dans `message_testeur` de la cloche ; le relais du fil (lot 4) et les jointures
  du suivi (lot 6) marchent. Coût : un secret partagé entre deux namespaces.
- **Sel propre** : condensés incomparables, relais impossible sans repasser le sub en clair.
- **Sub en clair** : contraire au principe RGPD du bus.

### Collections existantes : déduire de la publication (retenue) / tout au groupe / hors circuit
- Déduire : publiée « tout le monde » ⇒ `publiee_tous`, sinon `publiee_groupe`. Rien ne
  change pour les testeurs, la règle 3 vaut dès le premier démarrage.

### Seuil : lu chez le menu + figé (retenue) / variable d'environnement seule
- Le serveur lit `capacites.json` par le service interne (cache 60 s, repli 5) et chaque
  demande fige le seuil à sa création. Une seule valeur à régler.

## Décision

Règles actées :

1. **Toute identité du collectif est un condensé** HMAC-SHA256 salé, jamais le sub.
   Sel absent ⇒ 503, jamais d'écriture en clair. Aucun cookie de session n'est introduit ;
   si l'un l'est un jour, il porte une référence, jamais un jeton (< 1 024 o, testé).
2. **Le passage en chantier se calcule côté serveur** (`etats.demande_atteint_le_chantier`,
   ET jamais OU) ; aucune route n'accepte un état en entrée.
3. **L'ordre des états est strict pour le garant** ; `publiee_tous` exige une grille
   complète ; **un administrateur peut forcer le cycle**, et le forçage se lit dans le
   journal (`force: true`, motif).
4. **Une demande exige comment on se procure la donnée aujourd'hui** et une réponse
   explicite au recontact ; le courriel n'existe que consenti (contrainte de table).
5. **Chaque geste écrit un événement** dans la même transaction, signé d'une personne
   ou d'un robot ; « en sommeil » se calcule à la lecture (30 jours), jamais stocké.
6. **Un drapeau à `false` dans `capacites.json` rend 404** côté API — le bouton absent
   n'est pas la seule garde.

## Conséquences

- **Positives** : les six règles sont des tests (`tests/unit/test_regle*.py`) ; la suite
  historique est isolée sur une base propre (`tests/conftest.py`) et passe de 207 à 304
  verts ; le fil d'avancement est le contrat commun des lots 4 et 6.
- **Négatives** : publier « tout le monde » depuis la page de publication répond 422
  tant que la collection n'est pas `publiee_tous` — déployer avec le lot 3. Dix tests
  historiques (`test_collections.py`, `test_publication.py`) restent rouges : ils
  lisent un `metadata.json` disparu depuis le passage en base et patchent un symbole
  absent ; ils l'étaient déjà sur `main` (16 sur 17).
- **À surveiller** : le domaine d'`etat_collab` n'est pas une contrainte SQL (SQLite
  ne sait pas l'ajouter après coup) — il est tenu par `etats.py` et le store.

## Suivi

- [x] Schéma, machine à états, tests, routes — lot 1 (`lot-1/modele-api`)
- [ ] Déploiement : Secret `obs-pseudo-salt` copié dans `mycollections`, `CAPACITES_URL`,
      sortie Cilium vers `apps-menu` (8080), `IMAGE_TAG=0.3.0` après fusion
- [ ] Lot 0 : connecteurs des six amorces (`app/routers/amorces.py::CONNECTEURS`)
- [ ] Lot 2 : `collectif_store.appliquer_proposition` (Grist, versions de fichier)
- [ ] Lot 4 : route machine `POST /_beta/messages` côté bus, relais des événements aux abonnés
- [ ] Lot 6 : canal de lecture du suivi (GRANT SELECT ou route agrégée) — ADR à part
