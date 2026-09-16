# Interroger depuis vos SI

Une collection **publiée à tous** ne vit pas que dans Mes collections. Le bac à sable
sert à l'essayer ; pour s'en servir au quotidien, trois portes, sur les mêmes données.

## Dans l'agent conversationnel de MirAI Next

Chaque collection publiée à tous apparaît dans l'assistant comme un modèle nommé
`openrag-<nom de la collection>` — `openrag-dgef-sdst-faq`, `openrag-amorce-natinf`.
Choisissez-le dans la liste des modèles : la conversation répond à partir des documents
de la collection, avec les sources.

## Par l'API, depuis vos applications

La collection s'interroge par l'API d'OpenRAG, au format OpenAI. Deux appels suffisent :

- **Une réponse rédigée, avec ses sources** — `POST /v1/chat/completions`, avec le
  modèle de la collection :

```
curl https://<adresse de l'API>/v1/chat/completions \
  -H "Authorization: Bearer <clé d'API>" -H "Content-Type: application/json" \
  -d '{"model": "openrag-dgef-sdst-faq",
       "messages": [{"role": "user", "content": "Quelle est la durée d'une APS ?"}]}'
```

- **La recherche seule, sans rédaction** — `GET /search?text=<question>&partitions=<nom>&top_k=5`
  rend les morceaux les plus proches, avec le nom du document et le lien vers l'extrait.

L'adresse de l'API et le nom exact du modèle sont écrits sur la fiche de chaque collection
publiée à tous, dans l'encart « Où interroger cette collection ». La clé d'API se demande à
l'équipe de la bêta ; elle est propre à votre application, et se révoque seule.

## Dans vos outils bureautiques

Le greffon LibreOffice de MirAI interrogera les mêmes collections, depuis un document
ouvert. Il arrive ; les collections publiées à tous y seront servies sans rien refaire.

## Ce que ça engage

Une collection publiée à tous répond à des agents qui ne la connaissent pas, depuis des
applications que vous ne voyez pas. C'est pour cela que la publication à tous demande la
grille de contrôle complète et une relecture (page « Vérifier avant de publier »), et que
le garant reste joignable : le contact est sur la fiche.

## Le geste dans l'outil

Ouvrez la fiche d'une collection publiée à tous : l'encart « Où interroger cette
collection » donne le modèle pour l'assistant et les deux appels d'API, prêts à copier.

## Exemple

La sous-direction du séjour publie `dgef-sdst-faq` à tous. Le lendemain, l'outil de
réponse aux usagers d'une préfecture interroge `openrag-dgef-sdst-faq` par l'API pour
pré-rédiger les réponses sur les APS ; les agents de guichet posent les mêmes questions
dans l'assistant. Une FAQ mise à jour dans la collection change les deux à la fois.
