# Amorcer depuis ce qui existe

Avant de saisir quoi que ce soit, chercher ce qui est déjà publié. L'open data de l'État
couvre bien plus qu'on ne croit : nomenclatures, statistiques, décisions de justice,
répertoires. Une collection amorcée depuis une source publiée a déjà une licence, une
fréquence de mise à jour et une origine que tout le monde peut vérifier.

## Où chercher, dans l'ordre

1. **data.gouv.fr** — et son API tabulaire, qui évite de télécharger les fichiers.
2. **Les producteurs eux-mêmes** : justice administrative (opendata.justice-administrative.fr),
   Légifrance par PISTE, natinfo.app pour les infractions.
3. **Ce que le service possède déjà** : un dossier Drive, un tableur Grist, un partage
   Nextcloud ou Resana.

## Ce qu'une amorce fixe dès le départ

- **L'état** : la collection naît « amorcée ». Elle n'est servie à personne hors de son
  groupe, et ses réponses portent la mention « en cours de vérification ».
- **Le garant pressenti** : un nom de service, à confirmer par la personne elle-même.
- **La grille de contrôle** pré-remplie : source et licence, données personnelles,
  fraîcheur. Ce qui manque encore — la relecture — reste visible, vide.
- **Vingt questions de test** dans le bac à sable, pour juger la collection avant de
  la faire circuler.
- **La couverture constatée** : ce que le connecteur a réellement lu (juridictions,
  dates, lignes), écrite par le robot, pas par une personne.

Un import se rejoue sans dommage : ce qui est déjà là est ignoré, ce qui a changé est
versionné.

## Le geste dans l'outil

Administration → **Amorces** : le catalogue, l'état d'import de chacune, le bouton
**Importer**. Pour une collection à partir de vos propres fichiers : **Créer une
collection**, puis l'onglet **Sources**. Dans les deux cas, la fiche montre la grille de
contrôle dès le premier jour.

## Exemple

« Codes NATINF » : la liste officielle du ministère de la Justice sur data.gouv.fr
énumère 17 000 codes ; l'API natinfo.app enrichit les fiches (peines, articles) quand
une clé le permet. La couverture indique combien de codes ont été lus et combien
enrichis — deux chiffres différents, et c'est normal.
