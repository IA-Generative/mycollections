<template>
  <div class="rediger">
    <p v-if="indisponible" class="fr-message fr-message--info">{{ indisponible }}</p>
    <template v-else>
      <p class="fr-text--sm fr-mb-2w">
        L'IA lit des passages de la collection et rédige, pour chacun, une question que poserait la personne choisie,
        avec sa réponse de référence tirée du seul passage. Les questions arrivent dans le jeu « à relire » :
        validez celles qui sont justes, corrigez les autres. Comptez 2 à 5 minutes.
        <span v-if="modele" class="rediger__discret">Modèle : {{ libelleModele(modele) }}.</span>
      </p>
      <GenerationChoixPersonas v-model="candidats" :collection="collection" :desactive="enCours" />
      <div class="rediger__ligne fr-mt-2w">
        <div class="fr-input-group rediger__taille">
          <label class="fr-label" :for="`${uid}-taille`">Nombre de questions <span class="fr-hint-text">De 4 à 30.</span></label>
          <input :id="`${uid}-taille`" v-model.number="taille" class="fr-input" type="number" min="4" max="30" :disabled="enCours">
        </div>
        <button type="button" class="fr-btn fr-btn--sm fr-icon-sparkling-2-line fr-btn--icon-left" :disabled="enCours" @click="lancer">
          {{ enCours ? 'Rédaction en cours…' : 'Rédiger les questions' }}
        </button>
      </div>
      <div v-if="enCours" class="fr-mt-1w" aria-live="polite">
        <p class="fr-text--xs fr-mb-1v">{{ run ? `${libellePhase(run.phase)}…` : 'La rédaction démarre…' }}</p>
        <progress v-if="run" :value="progressionRun(run)" max="100" class="rediger__barre"
                  :aria-label="`Avancement de la rédaction : ${progressionRun(run)} %`" />
      </div>
      <p v-if="bilan" class="fr-text--sm fr-mt-1w" aria-live="polite">{{ bilan }}</p>
      <details v-if="personas.length" class="fr-mt-2w">
        <summary class="fr-text--sm rediger__resume">Gérer les personas enregistrés de la collection ({{ personas.length }})</summary>
        <GenerationPersonas class="fr-mt-1w" :collection="collection" :personas="personas" @change="relirePersonas" />
      </details>
      <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mt-1w" role="alert"><p>{{ erreur }}</p></div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { EXEMPLES_PERSONAS, PERSONNA_DEFAUT, candidatsInitiaux, libelleModele, libellePhase, preparerLancement, progressionRun, type CandidatPersona, type Run } from '~/utils/generation'
import { messageErreur } from '~/utils/collectif'

/**
 * « Faire rédiger par l'IA » : choisir les personas, lancer une génération et la suivre. Les
 * paires générées SONT des questions du jeu (origine « générée ») : à la fin, le jeu se recharge.
 */
const props = defineProps<{ collection: string }>()
const emit = defineEmits<{ fini: [], progression: [] }>()
const g = useGeneration()
const uid = `rediger-${useId()}`
const candidats = ref<CandidatPersona[]>([])
const taille = ref(8)
const enCours = ref(false)
const run = ref<Run | null>(null)
const erreur = ref('')
const bilan = ref('')
const indisponible = ref('')
const modele = ref('')
const personas = ref<any[]>([])
let minuterie: ReturnType<typeof setTimeout> | null = null

onMounted(async () => {
  try {
    const etat = await g.etat(props.collection)
    modele.value = etat.modele || ''
    personas.value = etat.personas || []
    candidats.value = candidatsInitiaux(personas.value, [PERSONNA_DEFAUT, ...EXEMPLES_PERSONAS])
    if (etat.run_actif) suivre(etat.run_actif)
  } catch (e) {
    indisponible.value = String(e).includes('503')
      ? `La rédaction automatique n'est pas disponible sur ce service : ${messageErreur(e)}`
      : `La rédaction automatique n'a pas pu être préparée : ${messageErreur(e)}`
  }
})
onBeforeUnmount(() => { if (minuterie) clearTimeout(minuterie) })

async function relirePersonas() {
  const etat = await g.etat(props.collection)
  personas.value = etat.personas || []
  candidats.value = candidatsInitiaux(personas.value, [PERSONNA_DEFAUT, ...EXEMPLES_PERSONAS])
}

function suivre(r: Run) {
  run.value = r
  enCours.value = true
  minuterie = setTimeout(async () => {
    try {
      const suite: Run = (await g.run(props.collection, r.id)).run
      if (suite.actif) {
        emit('progression')
        return suivre(suite)
      }
      enCours.value = false
      run.value = null
      if (suite.etat === 'erreur') erreur.value = suite.erreur || 'La rédaction a échoué.'
      else bilan.value = `${suite.paires_obtenues} question${suite.paires_obtenues > 1 ? 's' : ''} rédigée${suite.paires_obtenues > 1 ? 's' : ''}, ajoutée${suite.paires_obtenues > 1 ? 's' : ''} au jeu « à relire ».`
      emit('fini')
    } catch (e) {
      enCours.value = false
      erreur.value = `Le suivi de la rédaction a échoué : ${messageErreur(e)}`
    }
  }, 3000)
}

async function lancer() {
  erreur.value = ''
  bilan.value = ''
  const plan = preparerLancement(candidats.value)
  if (plan.erreur) {
    erreur.value = plan.erreur
    return
  }
  enCours.value = true
  try {
    const ids = [...plan.ids]
    for (const p of plan.aCreer) ids.push((await g.creerPersona(props.collection, p)).persona.id)
    const r = await g.lancer(props.collection, { personas: ids, taille: Math.min(30, Math.max(4, Number(taille.value) || 8)), distribution: { entites: 1 } })
    // Les personas créés sont désormais ceux de la collection : la liste les montre comme tels.
    await relirePersonas()
    suivre(r.run)
  } catch (e) {
    enCours.value = false
    erreur.value = messageErreur(e)
  }
}
</script>

<style scoped>
.rediger__ligne { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 1rem; }
.rediger__taille { max-width: 12rem; margin: 0; }
.rediger__barre { width: 100%; height: .5rem; }
.rediger__resume { cursor: pointer; }
.rediger__discret { color: var(--text-mention-grey); }
</style>
