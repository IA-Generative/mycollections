<template>
  <div class="depot">
    <fieldset class="fr-fieldset" :aria-labelledby="`${uid}-legende`">
      <legend :id="`${uid}-legende`" class="fr-fieldset__legend">{{ titre }}
        <span class="fr-hint-text">Formats acceptés : {{ FORMATS_LISIBLES }}. 50 Mo au plus par fichier.</span>
      </legend>
      <div class="depot__choix">
        <div v-if="!dossierSeul" class="fr-upload-group">
          <label class="fr-label" :for="`${uid}-fichiers`">Un ou plusieurs fichiers</label>
          <input :id="`${uid}-fichiers`" type="file" class="fr-upload" multiple :accept="ACCEPT" :disabled="enCours" @change="choisir" />
        </div>
        <div class="fr-upload-group">
          <label class="fr-label" :for="`${uid}-dossier`">{{ dossierSeul ? 'Choisir un dossier' : 'Un dossier entier' }}
            <span class="fr-hint-text">Sous-dossiers compris ; les fichiers cachés et les formats inconnus sont écartés. Vous pouvez ajouter plusieurs dossiers.</span>
          </label>
          <input :id="`${uid}-dossier`" type="file" class="fr-upload" webkitdirectory multiple :disabled="enCours" @change="choisir" />
        </div>
      </div>
    </fieldset>

    <div v-if="depots.length || ecartes.length" class="fr-mt-2w">
      <p class="fr-text--sm fr-mb-1w" aria-live="polite">
        <strong>{{ depots.length }} fichier{{ depots.length > 1 ? 's' : '' }}</strong>
        <template v-if="documents"> — dont {{ documents }} lu{{ documents > 1 ? 's' : '' }} et découpé{{ documents > 1 ? 's' : '' }} par le moteur de recherche (PDF, Word…)</template>
        <template v-if="bilanDepot"> · {{ bilanDepot }}</template>
      </p>
      <div class="fr-table fr-table--sm fr-table--no-caption depot__liste">
        <table>
          <caption>Fichiers à déposer</caption>
          <thead><tr><th>Fichier</th><th>Taille</th><th>État</th><th><span class="fr-sr-only">Retirer</span></th></tr></thead>
          <tbody>
            <tr v-for="(d, i) in depots" :key="d.nomDepot">
              <td>{{ d.nomDepot }}</td>
              <td class="depot__taille">{{ taille(d.taille) }}</td>
              <td>
                <span class="fr-badge fr-badge--sm" :class="classe(d.etat)">{{ LIBELLES_DEPOT[d.etat] }}</span>
                <p v-if="d.message" class="fr-text--xs fr-mb-0 fr-mt-1v">{{ d.message }}</p>
              </td>
              <td>
                <button v-if="d.etat === 'attente' && !enCours" type="button"
                        class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-close-line fr-btn--icon-only"
                        :title="`Retirer ${d.nomDepot} de la liste`" @click="depots.splice(i, 1)">Retirer</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <details v-if="ecartes.length" class="fr-mt-1w">
        <summary class="fr-text--sm">{{ ecartes.length }} fichier{{ ecartes.length > 1 ? 's' : '' }} écarté{{ ecartes.length > 1 ? 's' : '' }}</summary>
        <ul class="fr-text--sm">
          <li v-for="e in ecartes" :key="e.nom + e.raison">{{ e.nom }} — {{ e.raison }}</li>
        </ul>
      </details>
    </div>

    <button v-if="!sansBouton" type="button" class="fr-btn fr-mt-3w" :disabled="!aDeposer || enCours || desactive" @click="deposer">
      {{ enCours ? 'Dépôt en cours…' : aDeposer > 1 ? `Ajouter les ${aDeposer} documents` : 'Ajouter le document' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ACCEPT, FORMATS_LISIBLES, LIBELLES_DEPOT, bilan, etatDuTravail, trier, type EtatDepot, type Nature } from '~/utils/depot'

/**
 * Déposer plusieurs fichiers ou un dossier entier dans une collection : chaque fichier a sa ligne
 * et son état, suivi jusqu'à l'indexation. Partagé par « Ajouter des documents » (fiche) et par
 * l'étape « Données » de l'assistant de création (source « Répertoire local »).
 */
const props = withDefaults(defineProps<{
  collection: string
  strategy?: string
  sensitivity?: string
  titre?: string
  dossierSeul?: boolean
  desactive?: boolean
  sansBouton?: boolean
}>(), { strategy: 'auto', sensitivity: 'public', titre: 'Documents à ajouter' })
const emit = defineEmits<{ lance: [], termine: [bilan: Record<EtatDepot, number>], selection: [n: number] }>()

interface Depot { fichier: File, nomDepot: string, taille: number, nature: Nature, etat: EtatDepot, message: string, job?: string }
const { uploadFile, get } = useApi()
const uid = `depot-${useId()}`
const depots = ref<Depot[]>([])
const ecartes = ref<{ nom: string, raison: string }[]>([])
const enCours = ref(false)
const aDeposer = computed(() => depots.value.filter(d => d.etat === 'attente').length)
const documents = computed(() => depots.value.filter(d => d.nature === 'document').length)
const bilanDepot = computed(() => depots.value.some(d => d.etat !== 'attente') ? bilan(depots.value.map(d => d.etat)) : '')
watch(aDeposer, n => emit('selection', n))

function taille(o: number) {
  return o < 1024 ? `${o} o` : o < 1048576 ? `${Math.round(o / 1024)} Ko` : `${(o / 1048576).toFixed(1).replace('.', ',')} Mo`
}
function classe(e: EtatDepot) {
  return { indexe: 'fr-badge--success', echec: 'fr-badge--error', envoi: 'fr-badge--info', indexation: 'fr-badge--info', attente: '' }[e]
}

function choisir(e: Event) {
  const input = e.target as HTMLInputElement
  const fichiers = Array.from(input.files || [])
  const { retenus, ecartes: ec } = trier(fichiers.map(f => ({ nom: f.name, taille: f.size, chemin: (f as any).webkitRelativePath || undefined, f })))
  const deja = new Set(depots.value.map(d => d.nomDepot))
  for (const r of retenus) {
    if (deja.has(r.nomDepot)) { ec.push({ nom: r.chemin || r.nom, raison: 'déjà dans la liste' }); continue }
    depots.value.push({ fichier: r.f, nomDepot: r.nomDepot, taille: r.taille, nature: r.nature, etat: 'attente', message: '' })
  }
  ecartes.value = [...ecartes.value, ...ec]
  input.value = ''
}

async function suivre(d: Depot) {
  for (let i = 0; i < 600 && d.job; i++) {
    try {
      const job = await get(`/api/ingest/jobs/${d.job}`)
      d.etat = etatDuTravail(job)
      if (d.etat !== 'indexation') { if (job.error && d.etat === 'echec') d.message = job.error; return }
    } catch { /* une lecture manquée n'arrête pas le suivi */ }
    await new Promise(r => setTimeout(r, 3000))
  }
}

/** Dépose ce qui est en attente, un fichier après l'autre ; rend la main quand tout est indexé ou en échec. */
async function deposer() {
  enCours.value = true
  emit('lance')
  const suivis: Promise<void>[] = []
  for (const d of depots.value.filter(x => x.etat === 'attente')) {
    d.etat = 'envoi'
    try {
      const fichier = d.nomDepot === d.fichier.name ? d.fichier : new File([d.fichier], d.nomDepot, { type: d.fichier.type })
      const r = await uploadFile(`/api/ingest/${props.collection}`, fichier, { strategy: props.strategy, sensitivity: props.sensitivity })
      d.job = r.job_id
      d.etat = 'indexation'
      if (r.total_chunks) d.message = `${r.total_chunks} passage${r.total_chunks > 1 ? 's' : ''}`
      suivis.push(suivre(d))
    } catch (e: any) {
      d.etat = 'echec'
      d.message = messageErreur(new Error(String(e?.message || e).replace(/^Upload error/, 'API error')))
    }
  }
  enCours.value = false
  await Promise.all(suivis)
  const b = { attente: 0, envoi: 0, indexation: 0, indexe: 0, echec: 0 } as Record<EtatDepot, number>
  for (const d of depots.value) b[d.etat]++
  emit('termine', b)
}

defineExpose({ deposer, aDeposer, enCours })
</script>

<style scoped>
.depot__choix { display: flex; flex-wrap: wrap; gap: 1rem 2rem; }
.depot__choix .fr-upload-group { flex: 1 1 16rem; min-width: 0; }
.depot__liste { max-height: 24rem; overflow-y: auto; }
.depot__taille { white-space: nowrap; font-variant-numeric: tabular-nums; }
</style>
