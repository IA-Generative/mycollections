# Interroger une collection avec un agent

Sur la fiche d'une collection, l'onglet « Interroger avec un agent » liste les agents de
**Mes agents** que la personne a le droit de lancer et qui savent travailler sur une collection,
puis lance l'agent choisi sur les passages de la collection qui répondent à sa question.
C'est la consommation, côté Mes collections, du
[contrat d'agents MirAI](https://github.com/IA-Generative/myagents/blob/main/docs/contrats/contrat-agents-mirai.md)
(version 1, 2026-10-06), jumeau du contrat de recherche que sert `/api/v1/search`.

## Ce que voit la personne

1. L'onglet n'existe que si Mes agents est branché **et** a répondu sans refus. Un service
   injoignable, un jeton refusé, une audience qui n'est pas la sienne ou un 403 masquent
   l'onglet sans bloquer la fiche.
2. Dans l'onglet : la liste des agents (nom, description, « Le vôtre » ou « Partagé par des
   collègues », « Brouillon » le cas échéant), un champ question, « Lancer ».
3. L'attente est dite : la recherche dans la collection d'abord, puis l'agent (jusqu'à deux
   minutes, le délai que demande le contrat).
4. La réponse, en Markdown assaini, puis les passages transmis — ceux que la réponse cite par
   leur numéro `[n]` d'abord, avec les puces de source habituelles (bulle au survol, fenêtre de
   lecture, document complet). « Copier » met la réponse et la liste des passages dans le
   presse-papiers.

Un 422 de la garde anti-injection (`blocked_input`, `blocked_output`) s'affiche tel quel ; un
404 dit « Cet agent n'est plus accessible » ; un 429 invite à réessayer ; un 502 dit que l'agent
ne répond pas. Si aucun passage de la collection ne répond à la question, l'agent n'est pas
lancé, et la personne le sait.

## Rien ne transite côté serveur

Tout se passe dans le navigateur, avec le jeton de la session de la personne :

| Étape | Qui | Avec quoi |
|---|---|---|
| Lister les agents | `GET {MESAGENTS}/api/v1/agents?input=collection` | `Authorization: Bearer <jeton de la session>` |
| Trouver les passages | `GET /api/v1/search?q=<question>&scope=<collection>&limit=8` — **notre** recherche, qui applique les droits de la collection (`access.can_read`) et signe les liens | le même jeton (`azp = mycollections-front`, accepté par `audience_acceptee`) |
| Lancer l'agent | `POST {MESAGENTS}/v1/chat/completions` avec `model = fiche.model`, un seul message `user` : la question, la consigne « Réponds à partir des passages suivants, en citant [n]. », puis les passages entre `<<<` et `>>>` (`stream: false`, délai 120 s) | le même jeton |

Le serveur de Mes collections ne relaie rien vers Mes agents et ne voit jamais la réponse de
l'agent. Il n'a pas changé pour cette fonction. Les droits sont ceux des deux services : Mes
collections pour les passages, Mes agents pour l'agent.

Les fiches sont une donnée **non fiable** (contrat) : lues avec méfiance (`lireFiches`), textes
bornés (nom ≤ 200, description ≤ 2 000), valeurs d'entrée hors vocabulaire ignorées, affichées
par interpolation — jamais en HTML. Les passages sont neutralisés avant d'entrer dans le bloc
`<<< … >>>` (`neutraliser` : une ligne, jamais trois chevrons de suite) ; le message ne dépasse
pas 20 000 caractères (les derniers passages sont écartés, et la liste affichée est celle des
passages réellement transmis).

## Brancher

### 1. La variable, cuite au build du frontend

`NUXT_PUBLIC_MESAGENTS_BASE_URL` : l'origine publique de Mes agents
(`https://mesagents.fake-domain.name`, sans barre finale). Vide par défaut ⇒ la fonction
n'existe pas, et rien ne change pour le SSO.

Comme `KEYCLOAK_URL` et les autres, elle se lit **à la construction** de l'image, pas au
démarrage (`myrag/frontend/Dockerfile`, `ARG NUXT_PUBLIC_MESAGENTS_BASE_URL`) :

```bash
docker buildx build --platform linux/amd64 --push -t <REGISTRE>/myrag-frontend:$TAG \
  --build-arg KEYCLOAK_URL=https://<votre-sso> \
  --build-arg NUXT_PUBLIC_MESAGENTS_BASE_URL=https://<mes-agents> myrag/frontend/
```

En développement : `NUXT_PUBLIC_MESAGENTS_BASE_URL=https://<mes-agents> npx nuxt dev --port 8201`.

### 2. La portée Keycloak `mesagents-agents`

Quand la variable est renseignée, le frontend demande la portée optionnelle `mesagents-agents`
en plus de `openid email profile basic` (`portesOidc`, `utils/agents.ts`). Elle ajoute au jeton
d'accès l'audience `mesagents` et le claim `groups` en chemins complets — ce que Mes agents
vérifie.

À faire une fois dans le realm `mirai` : importer le client scope depuis le JSON de référence
du dépôt Mes agents (`keycloak/mesagents-agents.client-scope.json`), puis l'affecter en
**optionnel** au client `mycollections-front` (Clients → mycollections-front → Client scopes →
Add client scope → Optional).

**Sans cette affectation, ne pas renseigner la variable** : Keycloak refuse une portée non
affectée au client dès la connexion (`invalid_scope`), et plus personne n'entre dans Mes
collections. C'est pour cela que la portée n'est demandée que si l'adresse est là.

Ne jamais configurer `audience=mycollections-front` côté Mes agents : ce serait une confusion
d'audience (contrat).

### 3. Côté Mes agents : CORS

Le navigateur appelle Mes agents depuis l'origine de Mes collections : cette origine doit figurer
dans `CONTRAT_ORIGINES` de Mes agents (motifs `fnmatch` acceptés). Sans elle, le préflight est
refusé, la liste ne vient pas, et l'onglet reste masqué.

### 4. Côté Mes collections : la recherche accepte le jeton du front

`GET /api/v1/search` est appelé avec le jeton du front. Il passe si `azp` figure dans
`MYCOLLECTIONS_RECHERCHE_AUDIENCE` (par défaut `mycollections-front`) : en développement, avec
le client `myrag-front`, poser `MYCOLLECTIONS_RECHERCHE_AUDIENCE=myrag-front`. Quand le frontend
tourne sur une autre origine que l'API (`:8201` et `:8200` en dev), l'origine du frontend doit
aussi figurer dans `MYCOLLECTIONS_RECHERCHE_ORIGINES`. En production, même origine : rien à faire.

## Ce qu'il faut savoir pour y toucher

| Quoi | Où |
|---|---|
| Les portées OIDC, la lecture des fiches et des passages, le message, les erreurs (pur) | [`utils/agents.ts`](../myrag/frontend/utils/agents.ts) |
| La liste (garde de trois minutes, partagée), le lancement en deux temps | [`composables/useMesAgents.ts`](../myrag/frontend/composables/useMesAgents.ts) |
| L'onglet : sélecteur, question, attente, réponse, sources, « Copier » | [`components/agents/InterrogerAvecAgent.vue`](../myrag/frontend/components/agents/InterrogerAvecAgent.vue) |
| Son accrochage à la fiche (`?onglet=agent`) | [`pages/c/[id]/index.vue`](../myrag/frontend/pages/c/[id]/index.vue) |
| La portée demandée au SSO | [`composables/useAuth.ts`](../myrag/frontend/composables/useAuth.ts) |
| Les tests | [`tests/unit/agents.test.ts`](../myrag/frontend/tests/unit/agents.test.ts) |

**Le lien d'un passage est signé** (`?exp=…&sig=…`, 12 h) et absolu dans la réponse de la
recherche. La puce de source attend le chemin : `cheminSigne` en garde le chemin **et** la
signature (`proxiedSourceUrl` réécrirait une adresse absolue en perdant la signature). Passé le
délai, la fenêtre de lecture relit la source avec le jeton de la session, comme pour le bac à
sable.

**Un refus en cours de route ne retire pas l'onglet sous les pieds de la personne** : la
disponibilité est figée à l'ouverture de la fiche, le composant affiche le message, et c'est le
chargement suivant qui enlève l'onglet.

**Ce qui ne se prouve pas par un test unitaire** : le parcours réel (SSO avec la portée, CORS
de Mes agents, un vrai agent sur une vraie collection). À jouer dans un navigateur avant la bêta.
