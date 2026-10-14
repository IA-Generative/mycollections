# Prompts français de la génération

Écrits une fois par `python -m app.generation.adapter_prompts` (traduction par le modèle de la
passerelle MirAI, 14 octobre 2026), puis **relus et corrigés à la main**. Le moteur les charge à
chaque run (`moteur.charger_prompts`) ; il ne traduit jamais rien lui-même.

Nommage imposé par ragas : `{nom de l'extracteur ou du synthétiseur}_{nom du prompt}_french.json`.

Corrections faites à la main après la traduction automatique :

- **appariement thèmes / personas** : l'exemple traduit gardait des clés anglaises (« HR Manager »)
  pour des personas devenus « Responsable RH » — il aurait appris au modèle à rendre des noms qui
  ne correspondent à aucun persona. Clés alignées, et consigne de reprendre les noms à l'identique. Après le premier essai réel
  (des questions techniques prêtées à un persona qui ne les poserait pas), consigne resserrée : un
  thème ne va à un persona que s'il poserait la question ; l'exemple montre un thème laissé sans persona.
- **génération de paires** : « requête à un seul saut » (calque de *single-hop*) remplacé ; le sens
  des styles que ragas envoie en anglais (`Perfect grammar`, `Misspelled queries`…) est expliqué ;
  exemple remplacé par un cas du ministère, avec les valeurs de style et de longueur réellement
  transmises.
- `original_hash` est mis à `null` : ragas le compare à un `hash()` Python, aléatoire d'un processus
  à l'autre — l'avertissement « hash does not match » apparaissait à chaque run, fichier modifié ou non.

Après une montée de version de ragas : relancer l'outil dans un dossier temporaire, comparer, et
reporter les corrections ci-dessus.
