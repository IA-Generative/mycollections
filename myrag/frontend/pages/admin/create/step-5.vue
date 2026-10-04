<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous êtes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Accueil</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin/create">Créer une collection</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Partage</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Partager — {{ titre || collection }}</h1>
    <p class="fr-text--lg fr-mb-4w">Étape 5 sur 5 — Votre collection est créée. Qui doit pouvoir l'interroger dès maintenant ?</p>

    <WizardStepper :current-step="5" />

    <div v-if="!collection" class="fr-alert fr-alert--warning fr-mb-4w">
      <p>Aucune collection indiquée. <NuxtLink to="/admin/create">Retour à l'étape 1</NuxtLink></p>
    </div>

    <div v-else class="fr-col-12 fr-col-md-8">
      <div class="fr-callout fr-mb-4w">
        <h2 class="fr-callout__title fr-h6">Ce qui se passe ensuite</h2>
        <p class="fr-callout__text fr-text--sm">
          Une collection neuve est <strong>en cours de vérification</strong> : elle se partage avec un groupe,
          pas encore avec tout le ministère. Pour l'ouvrir à tous, complétez sa grille de contrôle et faites-la
          avancer depuis sa fiche — c'est là que vous la retrouverez.
        </p>
      </div>

      <fieldset class="fr-fieldset fr-mb-4w">
        <legend class="fr-fieldset__legend fr-h5">Dans l'assistant MirAI</legend>
        <div class="fr-fieldset__element">
          <div class="fr-radio-group">
            <input id="part-plus-tard" v-model="choix" type="radio" value="plus-tard" />
            <label class="fr-label" for="part-plus-tard">
              Plus tard — je la vérifie d'abord
              <span class="fr-hint-text">Elle ne s'interroge que dans son bac à sable, depuis sa fiche. Vous la publierez quand vous voudrez.</span>
            </label>
          </div>
        </div>
        <div class="fr-fieldset__element">
          <div class="fr-radio-group">
            <input id="part-groupe" v-model="choix" type="radio" value="groupe" />
            <label class="fr-label" for="part-groupe">
              Un groupe, pour la tester à plusieurs
              <span class="fr-hint-text">Seuls les membres du groupe indiqué la verront dans la liste des modèles de l'assistant.</span>
            </label>
          </div>
          <div v-if="choix === 'groupe'" class="fr-input-group fr-ml-4w fr-mt-1w">
            <label class="fr-label" for="part-groupe-nom">Groupe
              <span class="fr-hint-text">Son nom tel qu'il apparaît dans l'assistant. Un nom inconnu de l'assistant est refusé : la collection ne viserait personne.</span>
            </label>
            <input id="part-groupe-nom" v-model="groupe" class="fr-input" />
          </div>
        </div>
        <div v-if="choix === 'groupe'" class="fr-fieldset__element fr-mt-2w">
          <div class="fr-input-group">
            <label class="fr-label" for="nom-fiche">Nom dans l'assistant
              <span class="fr-hint-text">Laissez vide : c'est le titre de la collection.</span>
            </label>
            <input id="nom-fiche" v-model="nomFiche" class="fr-input" :placeholder="titre" />
          </div>
        </div>
      </fieldset>

      <p class="fr-text--sm" style="color:var(--text-mention-grey)">
        D'autres façons de l'interroger (comme outil dans toute conversation, depuis une page web, depuis une
        extension du navigateur) sont prévues ; elles n'existent pas encore et ne sont donc pas proposées ici.
      </p>

      <div class="fr-btns-group fr-btns-group--inline fr-mt-4w">
        <NuxtLink :to="`/admin/create/step-4?collection=${collection}`" class="fr-btn fr-btn--secondary">← Précédent</NuxtLink>
        <button class="fr-btn" :disabled="envoi || (choix === 'groupe' && !groupe.trim())" @click="terminer">
          {{ envoi ? 'Enregistrement…' : choix === 'groupe' ? 'Partager avec ce groupe' : 'Terminer' }}
        </button>
      </div>

      <div v-if="resultat" class="fr-alert fr-mt-2w" :class="erreur ? 'fr-alert--error' : 'fr-alert--success'">
        <p>{{ resultat }}</p>
        <NuxtLink v-if="!erreur" :to="`/c/${collection}`" class="fr-btn fr-btn--sm fr-mt-1w">Ouvrir la fiche de la collection</NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const collection = route.query.collection as string
const { titre } = useTitreCollection(collection)
const { post } = useApi()

const choix = ref<'plus-tard' | 'groupe'>('plus-tard')
const groupe = ref('')
const nomFiche = ref('')
const envoi = ref(false)
const resultat = ref('')
const erreur = ref(false)

async function terminer() {
  erreur.value = false
  resultat.value = ''
  if (choix.value === 'plus-tard') {
    resultat.value = "Votre collection est prête. Vérifiez ses réponses dans son bac à sable, puis publiez-la depuis sa fiche."
    return
  }
  envoi.value = true
  try {
    const chemin = groupe.value.trim()
    const r: any = await post(`/api/collections/${collection}/publish`, {
      alias_enabled: true,
      alias_name: nomFiche.value.trim(),
      visibility: 'group',
      visibility_groups: [chemin],
    })
    resultat.value = r?.owui?.error
      ? `La collection est publiée, mais l'assistant ne l'a pas encore reçue : ${r.owui.error}`
      : `Votre collection est visible du groupe « ${chemin} » dans l'assistant. Pour l'ouvrir à tous, vérifiez-la depuis sa fiche.`
  } catch (e) {
    erreur.value = true
    resultat.value = messageErreur(e)
  } finally {
    envoi.value = false
  }
}
</script>
