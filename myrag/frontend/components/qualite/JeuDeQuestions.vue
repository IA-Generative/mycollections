<template>
  <div class="jeu">
    <!-- Les gestes : rédiger, ajouter, importer, exporter -->
    <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-btns-group--icon-left jeu__gestes">
      <button type="button" class="fr-btn fr-icon-sparkling-2-line" :class="panneau === 'rediger' ? '' : 'fr-btn--secondary'"
              :aria-expanded="panneau === 'rediger'" @click="basculer('rediger')">Faire rédiger par l'IA</button>
      <button type="button" class="fr-btn fr-btn--secondary fr-icon-add-line" :aria-expanded="panneau === 'ajouter'"
              @click="basculer('ajouter')">Ajouter une question</button>
      <label class="fr-btn fr-btn--tertiary fr-icon-upload-line jeu__importer">
        Importer (JSON, CSV)
        <input type="file" accept=".json,.csv,application/json,text/csv" class="fr-sr-only" @change="importer">
      </label>
      <button v-if="total" type="button" class="fr-btn fr-btn--tertiary fr-icon-download-line" @click="exporter('json')">Exporter en JSON</button>
      <button v-if="total" type="button" class="fr-btn fr-btn--tertiary fr-icon-download-line" @click="exporter('csv')">Exporter en CSV</button>
    </div>

    <div v-show="panneau === 'rediger'" class="jeu__panneau">
      <QualiteRediger v-if="redigerVu" :collection="collection" @fini="rechargerTout" @progression="charger" />
    </div>

    <form v-if="panneau === 'ajouter'" class="jeu__panneau" @submit.prevent="ajouter">
      <div class="fr-input-group">
        <label class="fr-label" :for="`${uid}-q`">Question <span class="fr-hint-text">Telle que la poserait un usager.</span></label>
        <textarea :id="`${uid}-q`" v-model="nouvelle.question" class="fr-input" rows="2" required minlength="3" maxlength="2000" />
      </div>
      <div class="fr-checkbox-group fr-checkbox-group--sm fr-mb-2w">
        <input :id="`${uid}-hs`" v-model="nouvelle.hors_sujet" type="checkbox">
        <label class="fr-label" :for="`${uid}-hs`">Question hors sujet : la collection doit refuser d'y répondre</label>
      </div>
      <div v-if="!nouvelle.hors_sujet" class="fr-input-group">
        <label class="fr-label" :for="`${uid}-r`">Réponse de référence <span class="fr-hint-text">La bonne réponse, celle à laquelle la réponse de la collection sera comparée.</span></label>
        <textarea :id="`${uid}-r`" v-model="nouvelle.reponse" class="fr-input" rows="4" maxlength="8000" />
      </div>
      <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
        <button type="submit" class="fr-btn" :disabled="!nouvelle.question.trim()">Ajouter au jeu (validée)</button>
        <button type="button" class="fr-btn fr-btn--tertiary" @click="panneau = ''">Annuler</button>
      </div>
    </form>

    <div v-if="message" class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w" role="status"><p>{{ message }}</p></div>
    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w" role="alert"><p>{{ erreur }}</p></div>

    <!-- Filtres -->
    <div class="jeu__filtres">
      <div class="fr-select-group">
        <label class="fr-label" :for="`${uid}-f-rel`">État</label>
        <select :id="`${uid}-f-rel`" v-model="filtres.relecture" class="fr-select">
          <option value="">Tous ({{ comptes.total || 0 }})</option>
          <option value="brut">À relire ({{ comptes.par_relecture?.brut || 0 }})</option>
          <option value="valide">Validées ({{ comptes.par_relecture?.valide || 0 }})</option>
          <option value="rejete">Rejetées ({{ comptes.par_relecture?.rejete || 0 }})</option>
        </select>
      </div>
      <div class="fr-select-group">
        <label class="fr-label" :for="`${uid}-f-ver`">Dernier verdict</label>
        <select :id="`${uid}-f-ver`" v-model="filtres.verdict" class="fr-select">
          <option value="">Tous</option>
          <option v-for="v in VERDICTS" :key="v" :value="v">{{ libelleVerdict(v === 'jamais' ? null : v) }} ({{ comptes.par_verdict?.[v] || 0 }})</option>
        </select>
      </div>
      <div class="fr-select-group">
        <label class="fr-label" :for="`${uid}-f-ori`">Origine</label>
        <select :id="`${uid}-f-ori`" v-model="filtres.origine" class="fr-select">
          <option value="">Toutes</option>
          <option v-for="(n, o) in comptes.par_origine || {}" :key="o" :value="o">{{ libelleOrigine(String(o)) }} ({{ n }})</option>
        </select>
      </div>
      <div class="fr-checkbox-group fr-checkbox-group--sm jeu__fiables">
        <input :id="`${uid}-f-fia`" v-model="filtres.fiable" type="checkbox">
        <label class="fr-label" :for="`${uid}-f-fia`">Réponses fiables seulement ({{ comptes.fiables || 0 }})</label>
      </div>
      <div class="fr-search-bar jeu__recherche" role="search">
        <label class="fr-label" :for="`${uid}-f-q`">Chercher dans les questions</label>
        <input :id="`${uid}-f-q`" v-model="texte" class="fr-input" type="search" placeholder="Chercher dans les questions" maxlength="100">
      </div>
    </div>

    <p v-if="chargement && !questions.length" class="fr-text--sm" aria-live="polite">Chargement…</p>
    <div v-else-if="!questions.length" class="fr-callout fr-mt-2w">
      <p class="fr-callout__text fr-text--sm">
        {{ comptes.total ? 'Aucune question ne correspond à ces filtres.' : 'Le jeu est vide. Faites rédiger des questions d\'après les documents, ajoutez les vôtres ou importez un fichier.' }}
      </p>
    </div>

    <ul v-else class="jeu__liste" :aria-busy="chargement">
      <li v-for="q in questions" :key="q.id" class="jeu__item" :class="`jeu__item--${q.relecture}`">
        <div class="jeu__badges">
          <span class="fr-badge fr-badge--sm fr-badge--no-icon" :class="classeRelecture(q.relecture)">{{ libelleRelecture(q.relecture) }}</span>
          <span v-if="q.dernier_verdict" class="fr-badge fr-badge--sm" :class="classeVerdict(q.dernier_verdict)">{{ libelleVerdict(q.dernier_verdict) }}</span>
          <span class="fr-tag fr-tag--sm">{{ libelleOrigine(q.origine) }}</span>
          <span v-if="q.persona" class="fr-tag fr-tag--sm">{{ q.persona }}</span>
          <span v-if="q.hors_sujet" class="fr-badge fr-badge--sm fr-badge--no-icon fr-badge--purple-glycine">Hors sujet : doit refuser</span>
          <span v-if="q.fiable" class="fr-badge fr-badge--sm fr-badge--no-icon fr-badge--green-emeraude">Réponse fiable</span>
        </div>

        <div class="jeu__champs">
          <QualiteChampEditable :valeur="q.question" :libelle="'Question'" :max="2000" class="jeu__question"
                                @enregistrer="v => modifier(q, { question: v })" />
          <QualiteChampEditable v-if="!q.hors_sujet" :valeur="q.reponse" :libelle="'Réponse de référence'" :max="8000"
                                vide="Aucune réponse de référence : ajoutez-la avant de valider."
                                @enregistrer="v => modifier(q, { reponse: v })" />
        </div>
        <p v-if="q.contextes?.length" class="fr-text--xs fr-mb-1v jeu__discret">
          Tirée de : {{ [...new Set(q.contextes.map(c => c.fichier))].join(', ') }}
        </p>

        <div class="jeu__actions">
          <button v-if="q.relecture !== 'valide'" type="button" class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-check-line fr-btn--icon-left"
                  :disabled="!q.hors_sujet && !q.reponse.trim()" :title="!q.hors_sujet && !q.reponse.trim() ? 'Ajoutez une réponse de référence pour valider' : ''"
                  @click="modifier(q, { relecture: 'valide' })">Valider</button>
          <button v-if="q.relecture !== 'rejete'" type="button" class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-close-line fr-btn--icon-left"
                  @click="modifier(q, { relecture: 'rejete' })">Rejeter</button>
          <div v-if="q.relecture === 'valide' && !q.hors_sujet" class="fr-checkbox-group fr-checkbox-group--sm jeu__fiable">
            <input :id="`${uid}-fi-${q.id}`" type="checkbox" :checked="q.fiable" @change="modifier(q, { fiable: !q.fiable })">
            <label class="fr-label" :for="`${uid}-fi-${q.id}`">Réponse fiable</label>
          </div>
          <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-eye-line fr-btn--icon-left" @click="emit('ouvrir', q.id)">Détail et conseils</button>
          <button v-if="confirmer !== q.id" type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-delete-line fr-btn--icon-left"
                  @click="confirmer = q.id">Supprimer</button>
          <template v-else>
            <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary" @click="supprimer(q)">Confirmer la suppression</button>
            <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline" @click="confirmer = ''">Garder</button>
          </template>
        </div>
      </li>
    </ul>

    <nav v-if="pages > 1" class="fr-pagination fr-mt-2w" aria-label="Pages du jeu de questions">
      <ul class="fr-pagination__list">
        <li><button type="button" class="fr-pagination__link fr-pagination__link--prev fr-pagination__link--lg-label" :disabled="page <= 1" @click="page--">Page précédente</button></li>
        <li><span class="fr-pagination__link" aria-current="page">{{ page }} / {{ pages }}</span></li>
        <li><button type="button" class="fr-pagination__link fr-pagination__link--next fr-pagination__link--lg-label" :disabled="page >= pages" @click="page++">Page suivante</button></li>
      </ul>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { classeRelecture, libelleRelecture } from '~/utils/generation'
import { classeVerdict, libelleOrigine, libelleVerdict, lireImport, type Question } from '~/utils/qualite'
import { messageErreur } from '~/utils/collectif'

/**
 * Le jeu de questions de référence : chaque question porte sa réponse (modifiable en place), son
 * origine, son état de relecture et son dernier verdict. Le même composant sert l'étape 4 de
 * l'assistant et la page Qualité (docs/qualite.md).
 */
const props = defineProps<{ collection: string, filtre?: Record<string, string> }>()
const emit = defineEmits<{ change: [], ouvrir: [id: string] }>()
const api = useQualite(props.collection)
const uid = `jeu-${useId()}`
const VERDICTS = ['conforme', 'partiel', 'non_conforme', 'refus_ok', 'refus_ko', 'sans_source', 'erreur', 'jamais']

const questions = ref<Question[]>([])
const comptes = ref<any>({})
const total = ref(0)
const page = ref(1)
const pages = ref(1)
const chargement = ref(false)
const erreur = ref('')
const message = ref('')
const panneau = ref<'' | 'rediger' | 'ajouter'>('')
const redigerVu = ref(false)
const confirmer = ref('')
const texte = ref('')
const filtres = reactive({ relecture: '', verdict: '', origine: '', fiable: false, q: '' })
const nouvelle = reactive({ question: '', reponse: '', hors_sujet: false })

function appliquerFiltre(f?: Record<string, string>) {
  filtres.relecture = f?.relecture || ''
  filtres.verdict = f?.verdict || ''
  filtres.origine = f?.origine || ''
  filtres.fiable = f?.fiable === 'true'
}
appliquerFiltre(props.filtre)
watch(() => props.filtre, f => appliquerFiltre(f))

function basculer(p: 'rediger' | 'ajouter') {
  panneau.value = panneau.value === p ? '' : p
  if (p === 'rediger') redigerVu.value = true
}

async function charger() {
  chargement.value = true
  const params: Record<string, string> = { page: String(page.value), par_page: '25' }
  if (filtres.relecture) params.relecture = filtres.relecture
  if (filtres.verdict) params.verdict = filtres.verdict
  if (filtres.origine) params.origine = filtres.origine
  if (filtres.fiable) params.fiable = 'true'
  if (filtres.q) params.q = filtres.q
  try {
    const r = await api.questions(params)
    questions.value = r.questions
    comptes.value = r.comptes
    total.value = r.comptes?.total || 0
    pages.value = Math.max(1, r.pages || 1)
    if (page.value > pages.value) page.value = pages.value
  } catch (e) {
    erreur.value = `Le jeu de questions n'a pas pu être lu : ${messageErreur(e)}`
  } finally {
    chargement.value = false
  }
}
function rechargerTout() {
  charger()
  emit('change')
}

let delai: ReturnType<typeof setTimeout> | null = null
watch(texte, (t) => {
  if (delai) clearTimeout(delai)
  delai = setTimeout(() => { filtres.q = t.trim() }, 300)
})
watch(() => [filtres.relecture, filtres.verdict, filtres.origine, filtres.fiable, filtres.q], () => {
  if (page.value !== 1) page.value = 1
  else charger()
})
watch(page, charger)
onMounted(charger)

function remplacer(q: Question) {
  questions.value = questions.value.map(x => (x.id === q.id ? q : x))
}

async function modifier(q: Question, champs: Record<string, unknown>) {
  erreur.value = ''
  message.value = ''
  try {
    remplacer((await api.modifier(q.id, champs)).question)
    // Les comptes (validées, fiables…) et la synthèse changent : on les relit.
    if ('relecture' in champs || 'fiable' in champs || 'question' in champs || 'reponse' in champs) rechargerComptes()
  } catch (e) {
    erreur.value = messageErreur(e)
  }
}
async function rechargerComptes() {
  try { comptes.value = (await api.questions({ par_page: '1' })).comptes } catch { /* sans effet sur la liste */ }
  emit('change')
}

async function supprimer(q: Question) {
  confirmer.value = ''
  try {
    await api.supprimer(q.id)
    await charger()
    emit('change')
  } catch (e) {
    erreur.value = messageErreur(e)
  }
}

async function ajouter() {
  erreur.value = ''
  message.value = ''
  try {
    await api.creer({ question: nouvelle.question, reponse: nouvelle.hors_sujet ? '' : nouvelle.reponse, hors_sujet: nouvelle.hors_sujet,
      relecture: (nouvelle.hors_sujet || nouvelle.reponse.trim()) ? 'valide' : 'brut' })
    message.value = 'Question ajoutée au jeu.'
    Object.assign(nouvelle, { question: '', reponse: '', hors_sujet: false })
    rechargerTout()
  } catch (e) {
    erreur.value = messageErreur(e)
  }
}

async function importer(ev: Event) {
  const input = ev.target as HTMLInputElement
  const fichier = input.files?.[0]
  input.value = ''
  if (!fichier) return
  erreur.value = ''
  message.value = ''
  const lu = lireImport(await fichier.text(), fichier.name)
  if ('erreur' in lu) {
    erreur.value = lu.erreur
    return
  }
  try {
    const b = await api.importer(lu.questions)
    const parts = [`${b.crees} question${b.crees > 1 ? 's' : ''} importée${b.crees > 1 ? 's' : ''}`]
    if (b.doublons) parts.push(`${b.doublons} déjà dans le jeu`)
    if (b.ignores) parts.push(`${b.ignores} ignorée${b.ignores > 1 ? 's' : ''} (sans question lisible)`)
    message.value = `${parts.join(', ')}.`
    rechargerTout()
  } catch (e) {
    erreur.value = `L'import a échoué : ${messageErreur(e)}`
  }
}

async function exporter(format: 'json' | 'csv') {
  try { await api.exporter(format) } catch (e) { erreur.value = `L'export a échoué : ${messageErreur(e)}` }
}

defineExpose({ charger })
</script>

<style scoped>
.jeu__gestes { margin-bottom: .5rem; }
.jeu__importer { cursor: pointer; }
.jeu__panneau { border: 1px solid var(--border-default-grey); background: var(--background-alt-grey); padding: 1rem 1.25rem; margin-bottom: 1.5rem; }
.jeu__filtres { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .75rem 1rem; margin-bottom: 1rem; }
.jeu__filtres .fr-select-group { margin: 0; min-width: 10rem; }
.jeu__recherche { flex: 1 1 14rem; min-width: 0; }
.jeu__fiables { margin: 0 0 .5rem; }
.jeu__liste { list-style: none; padding: 0; margin: 0; display: grid; gap: .75rem; }
.jeu__item { border: 1px solid var(--border-default-grey); border-left-width: 4px; padding: .75rem 1rem; display: grid; gap: .5rem; min-width: 0; }
.jeu__item--valide { border-left-color: var(--border-plain-success); }
.jeu__item--brut { border-left-color: var(--border-plain-info); }
.jeu__item--rejete { border-left-color: var(--border-default-grey); opacity: .75; }
.jeu__badges { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.jeu__badges .fr-tag { margin: 0; }
.jeu__champs { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); gap: .75rem; }
@media (max-width: 48em) { .jeu__champs { grid-template-columns: minmax(0, 1fr); } }
.jeu__question :deep(.champ__texte) { font-weight: 700; }
.jeu__actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
.jeu__actions .fr-btn { margin: 0; }
.jeu__fiable { margin: 0 .5rem; }
.jeu__discret { color: var(--text-mention-grey); }
</style>
