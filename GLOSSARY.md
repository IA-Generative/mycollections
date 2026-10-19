# Mes collections

Front DSFR pour OpenRAG : collections de documents, indexation déléguée, publication dans Open WebUI.

## Language

**Découpage d'indexation** :
Le découpage d'un document en passages cherchables, effectué par OpenRAG au moment de l'indexation. MyRAG ne découpe plus rien pour l'indexation.
_Avoid_: chunking maison, découpage (seul), stratégie de découpage

**Découpage de structuration**:
Le découpage local d'un document source, uniquement pour construire le graphe de références croisées. Rien n'est indexé par ce chemin.
_Avoid_: re-découpage, découpage du graphe

**Preset d'indexation**:
Une configuration nommée du pipeline d'indexation d'OpenRAG (chunker, tailles), assignée à une partition.
_Avoid_: stratégie, type de découpage

**Morceau**:
Un passage produit par le découpage d'indexation, stocké chez OpenRAG et cité comme source.
_Avoid_: chunk, extrait

**Consignes**:
Les instructions données au modèle pour répondre ; ce qui reste des anciens « types de collection » une fois le découpage délégué.
_Avoid_: type de collection, profil de découpage

**Réindexation**:
Action de maintenance qui vide la partition OpenRAG d'une collection et renvoie ses fichiers sources tels quels.
_Avoid_: redécoupage

**Amorce**:
Collection de démarrage fournie par Mes collections elle-même (guide, NATINF, justice administrative).
_Avoid_: collection d'exemple

**Partition**:
L'espace de stockage OpenRAG qui porte une collection ; une collection correspond à une partition.
_Avoid_: workspace
