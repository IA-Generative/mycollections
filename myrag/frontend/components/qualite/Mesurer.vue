<template>
  <div class="mesurer">
    <div class="mesurer__ligne">
      <button type="button" class="fr-btn fr-icon-play-line fr-btn--icon-left" :class="{ 'fr-btn--sm': petit }"
              :disabled="!!enCours || lancement || !validees || generationActive" @click="lancer">
        {{ enCours ? 'Mesure en cours…' : (validees ? `Mesurer avec ${validees} question${validees > 1 ? 's' : ''} validée${validees > 1 ? 's' : ''}` : 'Mesurer la qualité') }}
      </button>
      <span v-if="validees && !enCours" class="fr-text--xs mesurer__discret">
        {{ estimationMesure(validees) }}, environ {{ 2 * validees }} appels au modèle
      </span>
    </div>
    <p v-if="!validees" class="fr-text--xs fr-mt-1v fr-mb-0 mesurer__discret">
      Seules les questions validées sont mesurées : relisez et validez d'abord celles du jeu.
    </p>
    <p v-else-if="generationActive" class="fr-text--xs fr-mt-1v fr-mb-0 mesurer__discret">
      Une rédaction de questions est en cours : la mesure sera possible quand elle sera finie.
    </p>
    <div v-if="enCours" class="fr-mt-1w" aria-live="polite">
      <p class="fr-text--sm fr-mb-1v">
        {{ libellePhaseMesure(enCours.phase) }} — {{ enCours.nb_traitees }} / {{ enCours.nb_questions }} questions.
        Vous pouvez quitter la page : la mesure continue, et son résultat s'enregistre.
      </p>
      <progress :value="enCours.nb_traitees" :max="Math.max(1, enCours.nb_questions)" class="mesurer__barre"
                :aria-label="`Avancement de la mesure : ${enCours.nb_traitees} sur ${enCours.nb_questions}`" />
    </div>
    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mt-1w" role="alert"><p>{{ erreur }}</p></div>
  </div>
</template>

<script setup lang="ts">
import { estimationMesure, libellePhaseMesure, type Mesure } from '~/utils/qualite'
import { messageErreur } from '~/utils/collectif'

/**
 * Lancer une mesure et la suivre. La mesure tourne sur le serveur : quitter la page ne l'arrête
 * pas, et une mesure déjà lancée (ailleurs, ou avant un rechargement) est reprise au montage.
 */
const props = defineProps<{ collection: string, synthese: any, petit?: boolean }>()
const emit = defineEmits<{ fini: [mesure: Mesure] }>()
const api = useQualite(props.collection)
const enCours = ref<Mesure | null>(null)
const lancement = ref(false)
const erreur = ref('')
let minuterie: ReturnType<typeof setTimeout> | null = null

const validees = computed(() => props.synthese?.questions?.par_relecture?.valide || 0)
const generationActive = computed(() => !!props.synthese?.generation_active)

async function suivre() {
  if (!enCours.value) return
  try {
    const m: Mesure = (await api.mesure(enCours.value.id)).mesure
    if (m.actif) {
      enCours.value = m
      minuterie = setTimeout(suivre, 3000)
      return
    }
    enCours.value = null
    if (m.etat === 'erreur') erreur.value = m.erreur || 'La mesure a échoué.'
    emit('fini', m)
  } catch (e) {
    erreur.value = `Le suivi de la mesure a échoué : ${messageErreur(e)}`
    enCours.value = null
  }
}

async function lancer() {
  lancement.value = true
  erreur.value = ''
  try {
    enCours.value = (await api.mesurer({ seulement_validees: true })).mesure
    minuterie = setTimeout(suivre, 2000)
  } catch (e) {
    erreur.value = messageErreur(e)
  } finally {
    lancement.value = false
  }
}

watch(() => props.synthese?.mesure_active, (m) => {
  if (m && !enCours.value) {
    enCours.value = m
    minuterie = setTimeout(suivre, 2000)
  }
}, { immediate: true })
onBeforeUnmount(() => { if (minuterie) clearTimeout(minuterie) })
defineExpose({ lancer })
</script>

<style scoped>
.mesurer__ligne { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; }
.mesurer__discret { color: var(--text-mention-grey); }
.mesurer__barre { width: 100%; height: .5rem; }
</style>
