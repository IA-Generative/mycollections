<template>
  <div>
    <div v-if="indisponible" class="fr-callout">
      <p class="fr-callout__text">{{ indisponible }}</p>
    </div>
    <p v-else-if="!etat" class="fr-text--sm" aria-live="polite">Chargement…</p>
    <template v-else>
      <p class="fr-text--sm">
        Faites rédiger des paires question / réponse à partir des documents de la collection, du point de vue des
        personnes qui l'interrogeront. Elles servent à vérifier que l'assistant répond juste.
        <span style="color:var(--text-mention-grey)">Modèle : {{ etat.modele }}.</span>
      </p>
      <div class="fr-grid-row fr-grid-row--gutters">
        <div class="fr-col-12 fr-col-lg-5">
          <GenerationPersonas :collection="collection" :personas="etat.personas" @change="recharger" />
        </div>
        <div class="fr-col-12 fr-col-lg-7">
          <GenerationLancement :collection="collection" :personas="etat.personas" :runs="runs" :choisi="choisi"
                               @change="recharger" @choisir="id => choisi = id" />
        </div>
      </div>
      <GenerationPaires v-if="runChoisi" class="fr-mt-4w" :collection="collection" :run="runChoisi" />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { Run } from '~/utils/generation'
import { messageErreur } from '~/utils/collectif'

/** L'onglet « Questions générées » de la fiche : personas, lancement, suivi, relecture. */
const props = defineProps<{ collection: string }>()
const g = useGeneration()
const etat = ref<any>(null)
const runs = ref<Run[]>([])
const choisi = ref<string | null>(null)
const indisponible = ref('')
const runChoisi = computed(() => runs.value.find(r => r.id === choisi.value && r.etat === 'termine') || null)
let minuterie: ReturnType<typeof setTimeout> | null = null

async function recharger() {
  try {
    const [e, r] = await Promise.all([g.etat(props.collection), g.runs(props.collection)])
    const avant = runs.value.find(x => x.actif)
    etat.value = e
    runs.value = r.runs
    // Un run vient de finir : on montre ses paires.
    if (avant && runs.value.find(x => x.id === avant.id && x.etat === 'termine')) choisi.value = avant.id
    if (!choisi.value) choisi.value = runs.value.find(x => x.etat === 'termine')?.id || null
  } catch (e) {
    const m = messageErreur(e)
    indisponible.value = String(e).includes('503') ? m : `La génération n'a pas pu être lue : ${m}`
  }
  if (minuterie) clearTimeout(minuterie)
  if (runs.value.some(r => r.actif)) minuterie = setTimeout(recharger, 3000)
}
onMounted(recharger)
onBeforeUnmount(() => { if (minuterie) clearTimeout(minuterie) })
</script>
