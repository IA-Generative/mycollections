<template>
  <div>
    <FilAriane :collection="id" :titre="titre" rubrique="Ajouter des documents" />

    <h1 class="fr-h3">Ajouter des documents — {{ titre }}</h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-12 fr-col-lg-8">
        <!-- Fichiers ou dossier -->
        <fieldset class="fr-fieldset" aria-labelledby="depot-legende">
          <legend id="depot-legende" class="fr-fieldset__legend">Documents à ajouter
            <span class="fr-hint-text">Formats acceptés : {{ FORMATS_LISIBLES }}. 50 Mo au plus par fichier.</span>
          </legend>
          <div class="depot-choix">
            <div class="fr-upload-group">
              <label class="fr-label" for="fichiers">Un ou plusieurs fichiers</label>
              <input id="fichiers" type="file" class="fr-upload" multiple :accept="ACCEPT" :disabled="enCours" @change="choisir" />
            </div>
            <div class="fr-upload-group">
              <label class="fr-label" for="dossier">Un dossier entier
                <span class="fr-hint-text">Sous-dossiers compris ; les fichiers cachés et les formats inconnus sont écartés.</span>
              </label>
              <input id="dossier" type="file" class="fr-upload" webkitdirectory multiple :disabled="enCours" @change="choisir" />
            </div>
          </div>
        </fieldset>

        <div v-if="depots.length || ecartes.length" class="fr-mt-2w">
          <p class="fr-text--sm fr-mb-1w" aria-live="polite">
            <strong>{{ depots.length }} fichier{{ depots.length > 1 ? 's' : '' }}</strong> à déposer
            <template v-if="depots.some(d => d.nature === 'document')">
              — dont {{ depots.filter(d => d.nature === 'document').length }} lu{{ depots.filter(d => d.nature === 'document').length > 1 ? 's' : '' }} et découpé{{ depots.filter(d => d.nature === 'document').length > 1 ? 's' : '' }} par le moteur de recherche (PDF, Word…)
            </template>
            <template v-if="bilanDepot"> · {{ bilanDepot }}</template>
          </p>
          <div class="fr-table fr-table--sm fr-table--no-caption depot-liste">
            <table>
              <caption>Fichiers à déposer</caption>
              <thead><tr><th>Fichier</th><th>Taille</th><th>État</th></tr></thead>
              <tbody>
                <tr v-for="d in depots" :key="d.nomDepot">
                  <td>{{ d.nomDepot }}</td>
                  <td class="depot-taille">{{ taille(d.taille) }}</td>
                  <td>
                    <span class="fr-badge fr-badge--sm" :class="{ 'fr-badge--success': d.etat === 'indexe', 'fr-badge--error': d.etat === 'echec', 'fr-badge--info': d.etat === 'envoi' || d.etat === 'indexation' }">{{ LIBELLES_DEPOT[d.etat] }}</span>
                    <p v-if="d.message" class="fr-text--xs fr-mb-0 fr-mt-1v">{{ d.message }}</p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <details v-if="ecartes.length" class="fr-mt-1w">
            <summary class="fr-text--sm">{{ ecartes.length }} fichier{{ ecartes.length > 1 ? 's' : '' }} écarté{{ ecartes.length > 1 ? 's' : '' }}</summary>
            <ul class="fr-text--sm">
              <li v-for="e in ecartes" :key="e.nom">{{ e.nom }} — {{ e.raison }}</li>
            </ul>
          </details>
        </div>

        <!-- Strategy -->
        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label" for="strategy">Découpage du document
            <span class="fr-hint-text">Comment un fichier texte (.txt, .md, .csv) est coupé en passages, que l'assistant retrouve et cite. Les PDF, Word et autres documents sont découpés par le moteur de recherche.</span>
          </label>
          <select id="strategy" class="fr-select" v-model="strategy">
            <option value="auto">Automatique (détection du type)</option>
            <option value="article">Par article (code juridique)</option>
            <option value="section">Par section (rapport)</option>
            <option value="qr">Par question-réponse (FAQ)</option>
            <option value="length">Par longueur fixe</option>
          </select>
        </div>

        <!-- Sensitivity -->
        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label" for="sensitivity">Sensibilité</label>
          <select id="sensitivity" class="fr-select" v-model="sensitivity">
            <option value="public">Public</option>
            <option value="internal">Interne</option>
            <option value="restricted">Restreint</option>
            <option value="confidential">Confidentiel</option>
          </select>
        </div>

        <!-- Submit -->
        <button class="fr-btn fr-mt-4w" @click="deposer" :disabled="!aDeposer || enCours || rechercheIndisponible">
          {{ enCours ? 'Dépôt en cours…' : aDeposer > 1 ? `Ajouter les ${aDeposer} documents` : 'Ajouter le document' }}
        </button>
        <p v-if="rechercheIndisponible" class="fr-message fr-message--info fr-mt-1w">
          L'ajout de documents reviendra avec la recherche. Le bandeau en haut de la page vous préviendra.
        </p>
        <div v-if="error" class="fr-alert fr-alert--error fr-mt-4w">
          <p>{{ error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ACCEPT, FORMATS_LISIBLES, LIBELLES_DEPOT, bilan, etatDuTravail, trier, type EtatDepot, type Nature } from '~/utils/depot'

const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
const { uploadFile } = useApi()
// Le document irait au moteur de recherche : pendant une panne, l'envoi échouerait.
const { rechercheIndisponible } = useEtatService()

interface Depot { fichier: File, nomDepot: string, taille: number, nature: Nature, etat: EtatDepot, message: string, job?: string }
const strategy = ref('auto')
const sensitivity = ref('public')
const depots = ref<Depot[]>([])
const ecartes = ref<{ nom: string, raison: string }[]>([])
const enCours = ref(false)
const error = ref('')
const aDeposer = computed(() => depots.value.filter(d => d.etat === 'attente').length)
const bilanDepot = computed(() => depots.value.some(d => d.etat !== 'attente') ? bilan(depots.value.map(d => d.etat)) : '')
const { get } = useApi()

function taille(o: number) {
  return o < 1024 ? `${o} o` : o < 1048576 ? `${Math.round(o / 1024)} Ko` : `${(o / 1048576).toFixed(1).replace('.', ',')} Mo`
}

function choisir(e: Event) {
  const input = e.target as HTMLInputElement
  const fichiers = Array.from(input.files || [])
  const { retenus, ecartes: ec } = trier(fichiers.map(f => ({ nom: f.name, taille: f.size, chemin: (f as any).webkitRelativePath || undefined, f })))
  // Une nouvelle sélection s'ajoute à la liste ; un nom déjà présent n'est pas déposé deux fois.
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
    } catch { /* on réessaie : une lecture manquée n'arrête pas le suivi */ }
    await new Promise(r => setTimeout(r, 3000))
  }
}

async function deposer() {
  enCours.value = true
  error.value = ''
  const suivis: Promise<void>[] = []
  for (const d of depots.value.filter(x => x.etat === 'attente')) {
    d.etat = 'envoi'
    try {
      const fichier = d.nomDepot === d.fichier.name ? d.fichier : new File([d.fichier], d.nomDepot, { type: d.fichier.type })
      const r = await uploadFile(`/api/ingest/${id}`, fichier, { strategy: strategy.value, sensitivity: sensitivity.value })
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
}
</script>

<style scoped>
.depot-choix { display: flex; flex-wrap: wrap; gap: 1rem 2rem; }
.depot-choix .fr-upload-group { flex: 1 1 16rem; min-width: 0; }
.depot-liste { max-height: 24rem; overflow-y: auto; }
.depot-taille { white-space: nowrap; font-variant-numeric: tabular-nums; }
</style>
