<script setup lang="ts">
/**
 * La sensibilité d'une collection Résana (#134) : celle de la fiche (« Interne » à la création),
 * enregistrée dès qu'on la change. Elle accompagne chaque document envoyé à l'indexeur.
 * Partagée par « Gérer les documents » et par l'étape 3 de l'assistant Résana.
 */
import { SENSIBILITES } from '~/utils/libelles'

const props = defineProps<{
  collection: string
  /** La valeur de la fiche si la page l'a déjà lue ; absente, le composant la lit. */
  valeur?: string
}>()

const { get, patch } = useApi()
const champ = useId()
const sensitivity = ref(props.valeur || 'internal')
const enregistree = ref(props.valeur || 'internal')
const enregistrement = ref(false)
const message = ref('')
const erreur = ref('')

watch(() => props.valeur, (v) => {
  if (v) {
    sensitivity.value = v
    enregistree.value = v
  }
})

onMounted(async () => {
  if (props.valeur) {
    return
  }
  try {
    const f = await get(`/api/collections/${encodeURIComponent(props.collection)}`)
    if (f?.sensitivity) {
      sensitivity.value = f.sensitivity
      enregistree.value = f.sensitivity
    }
  }
  catch { /* la valeur par défaut reste affichée */ }
})

async function enregistrer () {
  enregistrement.value = true
  message.value = ''
  erreur.value = ''
  try {
    const f = await patch(`/api/collections/${encodeURIComponent(props.collection)}`, { sensitivity: sensitivity.value })
    enregistree.value = f?.sensitivity || sensitivity.value
    message.value = 'Sensibilité enregistrée.'
  }
  catch {
    erreur.value = 'La sensibilité n\'a pas pu être enregistrée. Réessayez dans un instant.'
    sensitivity.value = enregistree.value
  }
  finally {
    enregistrement.value = false
  }
}
</script>

<template>
  <div class="fr-select-group">
    <label
      class="fr-label"
      :for="champ"
    >Sensibilité
      <span class="fr-hint-text">Elle accompagne chaque document envoyé à l'indexeur, à partir de la prochaine mise à jour. Elle ne change pas qui peut lire la collection.</span>
    </label>
    <select
      :id="champ"
      v-model="sensitivity"
      class="fr-select"
      :disabled="enregistrement"
      @change="enregistrer"
    >
      <option
        v-for="s in SENSIBILITES"
        :key="s.valeur"
        :value="s.valeur"
      >
        {{ s.libelle }}
      </option>
    </select>
    <p
      class="fr-message fr-mt-1v"
      :class="{ 'fr-message--error': erreur, 'fr-message--valid': message }"
      aria-live="polite"
    >
      {{ erreur || message }}
    </p>
  </div>
</template>
