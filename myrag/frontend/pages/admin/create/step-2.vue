<script setup lang="ts">
import type { Categorie } from '~/types/collection'
import type { ReglesNommage } from '~/utils/collectionName'
import { isConflictError, motifRefus, REGLES_PAR_DEFAUT, slugifyCollectionName } from '~/utils/collectionName'
import { SENSIBILITES } from '~/utils/libelles'
import { identifiantPropose, reglagesAvancesDefaut, replierReglagesAvances } from '~/utils/wizard'

/**
 * Étape 2 de l'assistant : décrire la collection. Visibles : titre, identifiant proposé (lecture
 * seule), description, catégorie, qui peut l'interroger, responsable, courriel. Le reste (type de
 * collection, sensibilité, liens entre documents, identifiant choisi à la main) est replié sous
 * « Réglages avancés », qui s'ouvre seul si une valeur diffère du défaut ou porte une erreur.
 */
const route = useRoute()
const router = useRouter()
const { get, post } = useApi()
const { user } = useAuth()
const { lister: listerCategories } = useCategories()

const source = (route.query.source as string) || 'file'
const defaut = reglagesAvancesDefaut(source)

// Types de collection : découpage et consignes réglés ensemble.
const profiles = [
  { key: 'generique', label: 'Générique (détection automatique)', strategy: 'auto', prompt: 'generic', graph: false, desc: 'Découpage et consignes automatiques, adaptés à tout type de document.' },
  { key: 'juridique', label: 'Code juridique (articles et citations)', strategy: 'article', prompt: 'juridique', graph: true, desc: 'Un passage par article, avec sa place dans le code ; l\'assistant cite les numéros d\'articles.' },
  { key: 'faq', label: 'FAQ, questions-réponses', strategy: 'qr', prompt: 'faq', graph: false, desc: 'Un passage par question ; l\'assistant répond directement, avec la source.' },
  { key: 'rapport', label: 'Rapport, document structuré', strategy: 'section', prompt: 'technique', graph: false, desc: 'Un passage par section ; l\'assistant cite les sections et les pages.' },
  { key: 'corpus', label: 'Plusieurs documents variés', strategy: 'auto', prompt: 'multi_thematique', graph: false, desc: 'Le type de chaque document est détecté ; l\'assistant croise les sources.' },
  { key: 'multimedia', label: 'Images, audio, vidéo', strategy: 'auto', prompt: 'multimedia', graph: false, desc: 'Transcriptions et descriptions ; l\'assistant cite les fichiers et les minutages.' },
]
const profilInitial = profiles.find(p => p.key === defaut.profil) || profiles[0]!
const selectedProfile = ref(profilInitial.key)
const currentProfileDesc = computed(() => profiles.find(p => p.key === selectedProfile.value)?.desc || '')

const form = ref({
  titre: '',
  name: '',
  description: '',
  categorie: '',
  strategy: profilInitial.strategy,
  sensitivity: defaut.sensitivity,
  prompt_template: profilInitial.prompt,
  scope: 'group',
  graph_enabled: profilInitial.graph,
  ai_summary_enabled: defaut.ai_summary_enabled,
  contact_name: '',
  contact_email: '',
  scope_groups: [] as string[],
})

function applyProfile () {
  const p = profiles.find(pr => pr.key === selectedProfile.value)
  if (p) {
    form.value.strategy = p.strategy
    form.value.prompt_template = p.prompt
    form.value.graph_enabled = p.graph
  }
}
function onGraphToggle () {
  if (!form.value.graph_enabled) {
    form.value.ai_summary_enabled = false
  }
}

// ─── Identifiant ─────────────────────────────────────────────────────────────
const regles = ref<ReglesNommage>(REGLES_PAR_DEFAUT)
const identifiantManuel = ref(false)
const pris = ref(new Set<string>())
const nameStatus = ref('') // '' | 'available' | 'taken'
const messageRefus = ref('')
let minuterie: ReturnType<typeof setTimeout> | null = null

/** Tant que l'identifiant n'est pas choisi à la main, il suit le titre ; s'il est pris, un suffixe libre. */
function proposerIdentifiant () {
  if (identifiantManuel.value) {
    return
  }
  form.value.name = identifiantPropose(form.value.titre, pris.value, regles.value)
  nameStatus.value = ''
  programmerVerification()
}

function programmerVerification () {
  if (minuterie) {
    clearTimeout(minuterie)
  }
  minuterie = setTimeout(() => {
    if (form.value.name.trim() && !form.value.name.endsWith('-')) {
      checkNameAvailability(false)
    }
  }, 500)
}

async function checkNameAvailability (reecrire = true) {
  if (!form.value.name.trim()) {
    return
  }
  const name = slugifyCollectionName(form.value.name)
  if (reecrire) {
    form.value.name = name
  }
  const motif = motifRefus(name, regles.value)
  if (motif) {
    nameStatus.value = 'taken'
    messageRefus.value = regles.value.motifs[motif] || 'Identifiant refusé.'
    return
  }
  try {
    const { available, message } = await get('/api/collections/check-name', { name })
    if (available) {
      nameStatus.value = 'available'
      messageRefus.value = ''
    }
    else if (!identifiantManuel.value) {
      // Proposé et pris : on retient qu'il l'est, et on propose le suffixe libre suivant.
      pris.value = new Set([...pris.value, name])
      proposerIdentifiant()
    }
    else {
      nameStatus.value = 'taken'
      messageRefus.value = `${message || 'Cet identifiant est déjà pris.'} Précisez le contenu (un périmètre, une année, un service).`
    }
  }
  catch {
    // La vérification a échoué : on ne bloque pas, la création reste protégée par le serveur (409).
    nameStatus.value = ''
  }
}

// ─── Réglages avancés ────────────────────────────────────────────────────────
const erreurs = computed(() => ({ name: nameStatus.value === 'taken' ? messageRefus.value : '' }))
const replie = computed(() => replierReglagesAvances({
  profil: selectedProfile.value,
  sensitivity: form.value.sensitivity,
  graph_enabled: form.value.graph_enabled,
  ai_summary_enabled: form.value.ai_summary_enabled,
  identifiant_manuel: identifiantManuel.value,
}, erreurs.value, defaut))
const avancesOuverts = ref(false)
// Le repli s'ouvre seul quand il cache un choix ou une erreur ; la personne peut le refermer.
watch(replie, (r) => {
  if (!r) {
    avancesOuverts.value = true
  }
}, { immediate: true })

// ─── Qui peut l'interroger ───────────────────────────────────────────────────
const groupSearch = ref('')
const groupResults = ref<{ name: string, path: string }[]>([])
const userGroups = ref<{ name: string, path: string }[]>([])
function searchGroups () {
  const q = groupSearch.value.trim().toLowerCase()
  groupResults.value = q
    ? userGroups.value.filter(g => (g.name || '').toLowerCase().includes(q) || (g.path || '').toLowerCase().includes(q)).filter(g => !form.value.scope_groups.includes(g.path))
    : []
}
function addGroup (g: { path: string }) {
  if (!form.value.scope_groups.includes(g.path)) {
    form.value.scope_groups.push(g.path)
  }
  groupSearch.value = ''
  groupResults.value = []
}

// ─── Doublons ────────────────────────────────────────────────────────────────
const categories = ref<Categorie[]>([])
const allCollections = ref<any[]>([])
const duplicateWarning = ref<any>(null)
const VERSION_FINALE = /-v\d+$/
const NUMERO_FINAL = /-\d+$/
const CHIFFRES_FINAUX = /\d+$/
/** « ceseda-v2 » et « ceseda » se ressemblent ; « test-drive » et « test » non. */
function normalizeCollectionName (s: string): string {
  return s.toLowerCase().replace(VERSION_FINALE, '').replace(NUMERO_FINAL, '').replace(CHIFFRES_FINAUX, '')
}
function checkDuplicates () {
  if (!form.value.name.trim()) {
    return
  }
  const name = form.value.name.toLowerCase()
  const similar = allCollections.value.find(c => c.name.toLowerCase() === name)
    || allCollections.value.find(c => normalizeCollectionName(c.name) === normalizeCollectionName(name))
  duplicateWarning.value = similar
    ? { message: similar.name.toLowerCase() === name ? `Une collection « ${similar.name} » existe déjà.` : `Une collection proche, « ${similar.name} », existe déjà.`, existing: similar }
    : null
}

const creating = ref(false)
const error = ref('')
const pret = computed(() => !!form.value.name.trim() && !!form.value.titre.trim() && nameStatus.value !== 'taken')

async function createAndNext () {
  creating.value = true
  error.value = ''
  const corps: Record<string, unknown> = { ...form.value }
  if (!form.value.categorie) {
    delete corps.categorie // « Non classée »
  }
  try {
    await post('/api/collections', corps)
    router.push(`/admin/create/step-3?collection=${form.value.name}&source=${source}`)
  }
  catch (e: any) {
    if (isConflictError(e)) {
      nameStatus.value = 'taken'
      messageRefus.value = `L'identifiant « ${form.value.name} » est déjà pris. Précisez le contenu (un périmètre, une année, un service).`
      error.value = messageRefus.value
    }
    else {
      error.value = messageErreur(e)
    }
  }
  creating.value = false
}

onMounted(async () => {
  get('/api/collections/regles-nommage')
    .then((r) => {
      regles.value = { ...REGLES_PAR_DEFAUT, ...r }
    })
    .catch(() => {})
  listerCategories()
    .then((r) => {
      categories.value = r
    })
    .catch(() => {})
  try {
    allCollections.value = (await get('/api/collections')).collections || []
    pris.value = new Set(allCollections.value.map(c => c.name))
  }
  catch {}
  // Groupes proposés : chemins complets seulement, les seuls que l'API sait comparer.
  userGroups.value = groupPaths(user.value?.profile?.groups).map((g: string) => ({ name: g.split('/').pop() || g, path: g }))
  if (user.value?.profile) {
    const p = user.value.profile
    form.value.contact_name ||= p.name || p.preferred_username || ''
    form.value.contact_email ||= p.email || ''
  }
})
</script>

<template>
  <WizardEtape
    :numero="2"
    titre="Décrivez votre collection"
    chapeau="Une collection utile doit pouvoir être retrouvée et comprise en quelques secondes."
  >
    <template #formulaire>
      <!-- Doublon : l'alerte reste, avant le formulaire. -->
      <div
        v-if="duplicateWarning"
        class="fr-alert fr-alert--warning fr-mb-4w"
      >
        <h2 class="fr-alert__title fr-h6">
          Une collection proche existe déjà
        </h2>
        <p>{{ duplicateWarning.message }}</p>
        <p
          v-if="duplicateWarning.existing?.contact_name"
          class="fr-mt-1w"
        >
          <strong>Responsable :</strong> {{ duplicateWarning.existing.contact_name }}
          <a
            v-if="duplicateWarning.existing.contact_email"
            :href="`mailto:${duplicateWarning.existing.contact_email}`"
            class="fr-link"
          >
            {{ duplicateWarning.existing.contact_email }}
          </a>
        </p>
        <p class="fr-text--sm fr-mt-1w">
          Compléter une collection vaut mieux que la dupliquer : les sources ne se contredisent pas et les efforts ne se dispersent pas.
        </p>
        <ul class="fr-btns-group fr-btns-group--inline-sm fr-btns-group--sm fr-mt-2w">
          <li>
            <NuxtLink
              :to="`/c/${duplicateWarning.existing?.name}`"
              class="fr-btn fr-btn--secondary fr-btn--sm"
            >
              Voir la collection existante
            </NuxtLink>
          </li>
          <li>
            <button
              type="button"
              class="fr-btn fr-btn--tertiary fr-btn--sm"
              @click="duplicateWarning = null"
            >
              Je crée quand même la mienne
            </button>
          </li>
        </ul>
      </div>

      <div class="fr-input-group">
        <label
          class="fr-label"
          for="titre"
        >
          Titre de la collection *
          <span class="fr-hint-text">Ce que liront vos collègues dans l'assistant. Soyez précis et différenciant : reprenez le nom habituel du document.</span>
        </label>
        <input
          id="titre"
          v-model="form.titre"
          class="fr-input"
          maxlength="255"
          placeholder="Ex. : Codes NATINF"
          required
          @input="proposerIdentifiant"
          @blur="checkDuplicates"
        >
      </div>

      <div
        class="fr-input-group"
        :class="{ 'fr-input-group--error': nameStatus === 'taken', 'fr-input-group--valid': nameStatus === 'available' }"
      >
        <label
          class="fr-label"
          for="name-propose"
        >
          Identifiant
          <span class="fr-hint-text">Proposé d'après le titre. Il ne changera plus une fois la collection créée. Pour le choisir vous-même : « Réglages avancés ».</span>
        </label>
        <input
          id="name-propose"
          :value="form.name"
          class="fr-input"
          readonly
          aria-readonly="true"
        >
        <p
          v-if="nameStatus === 'available'"
          class="fr-valid-text"
        >
          Cet identifiant est disponible.
        </p>
        <p
          v-if="nameStatus === 'taken'"
          class="fr-error-text"
        >
          {{ messageRefus || 'Cet identifiant est déjà pris.' }}
        </p>
      </div>

      <div class="fr-input-group">
        <label
          class="fr-label"
          for="desc"
        >
          Description
          <span class="fr-hint-text">Dites à quoi elle sert, ce qu'elle couvre et ce qu'elle ne couvre pas.</span>
        </label>
        <textarea
          id="desc"
          v-model="form.description"
          class="fr-input"
          rows="3"
          placeholder="Ex. : à utiliser pour retrouver la qualification d'une infraction et la peine encourue."
        />
      </div>

      <div class="fr-grid-row fr-grid-row--gutters">
        <div class="fr-col-12 fr-col-md-6">
          <div class="fr-select-group">
            <label
              class="fr-label"
              for="categorie"
            >Catégorie
              <span class="fr-hint-text">Où la ranger dans le catalogue.</span>
            </label>
            <select
              id="categorie"
              v-model="form.categorie"
              class="fr-select"
            >
              <option value="">
                Non classée
              </option>
              <option
                v-for="c in categories"
                :key="c.cle"
                :value="c.cle"
              >
                {{ c.libelle }}
              </option>
            </select>
          </div>
        </div>
        <div class="fr-col-12 fr-col-md-6">
          <div class="fr-select-group">
            <label
              class="fr-label"
              for="scope"
            >Qui peut l'interroger ?
              <span class="fr-hint-text">Vous pourrez l'ouvrir plus largement ensuite.</span>
            </label>
            <select
              id="scope"
              v-model="form.scope"
              class="fr-select"
            >
              <option value="public">
                Tout le ministère
              </option>
              <option value="group">
                Un ou plusieurs groupes
              </option>
              <option value="private">
                Moi seulement, pour l'instant
              </option>
            </select>
          </div>
        </div>
      </div>

      <div
        v-if="form.scope === 'group'"
        class="fr-input-group"
      >
        <label
          class="fr-label"
          for="groupes"
        >Groupes autorisés
          <span class="fr-hint-text">Cherchez parmi vos groupes.</span>
        </label>
        <input
          id="groupes"
          v-model="groupSearch"
          class="fr-input"
          placeholder="Rechercher un groupe…"
          autocomplete="off"
          @input="searchGroups"
        >
        <ul
          v-if="groupResults.length"
          class="etape2-groupes"
        >
          <li
            v-for="g in groupResults"
            :key="g.path"
          >
            <button
              type="button"
              class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
              @click="addGroup(g)"
            >
              {{ g.path }}
            </button>
          </li>
        </ul>
        <ul
          v-if="form.scope_groups.length"
          class="fr-tags-group fr-mt-1w"
        >
          <li
            v-for="(g, i) in form.scope_groups"
            :key="g"
          >
            <button
              type="button"
              class="fr-tag fr-tag--sm fr-tag--dismiss"
              :aria-label="`Retirer ${g}`"
              @click="form.scope_groups.splice(i, 1)"
            >
              {{ g }}
            </button>
          </li>
        </ul>
        <p
          v-else
          class="fr-text--sm fr-mt-1w etape2-discret"
        >
          Aucun groupe choisi.
        </p>
      </div>
      <p
        v-if="form.scope === 'private'"
        class="fr-text--sm etape2-discret"
      >
        Vous seul la verrez : utile pour la tester avant de l'ouvrir.
      </p>

      <div class="fr-grid-row fr-grid-row--gutters">
        <div class="fr-col-12 fr-col-md-6">
          <div class="fr-input-group">
            <label
              class="fr-label"
              for="responsable"
            >Responsable
              <span class="fr-hint-text">Le service ou la personne que vos collègues contacteront.</span>
            </label>
            <input
              id="responsable"
              v-model="form.contact_name"
              class="fr-input"
              placeholder="Service ou personne à contacter"
            >
          </div>
        </div>
        <div class="fr-col-12 fr-col-md-6">
          <div class="fr-input-group">
            <label
              class="fr-label"
              for="courriel"
            >Courriel de contact</label>
            <input
              id="courriel"
              v-model="form.contact_email"
              class="fr-input"
              type="email"
              placeholder="service@fake-domain.name"
            >
          </div>
        </div>
      </div>

      <!-- Réglages avancés : valeurs par défaut posées ; le repli s'ouvre seul s'il cache un choix ou une erreur. -->
      <section class="fr-accordion fr-mt-2w">
        <h2 class="fr-accordion__title">
          <button
            type="button"
            class="fr-accordion__btn"
            :aria-expanded="avancesOuverts ? 'true' : 'false'"
            aria-controls="reglages-avances"
            @click="avancesOuverts = !avancesOuverts"
          >
            Réglages avancés (facultatif)
          </button>
        </h2>
        <div
          id="reglages-avances"
          class="fr-collapse"
          :class="{ 'fr-collapse--expanded': avancesOuverts }"
        >
          <p class="fr-text--sm">
            Des valeurs raisonnables sont déjà choisies ; vous pourrez y revenir depuis les réglages de la collection.
          </p>
          <div class="fr-select-group">
            <label
              class="fr-label"
              for="profil"
            >Type de collection
              <span class="fr-hint-text">Il règle ensemble la façon de découper les documents et les consignes données à l'assistant.</span>
            </label>
            <select
              id="profil"
              v-model="selectedProfile"
              class="fr-select"
              @change="applyProfile"
            >
              <option
                v-for="p in profiles"
                :key="p.key"
                :value="p.key"
              >
                {{ p.label }}
              </option>
            </select>
            <p class="fr-hint-text fr-mt-1v">
              {{ currentProfileDesc }}
            </p>
          </div>
          <div class="fr-select-group">
            <label
              class="fr-label"
              for="sensibilite"
            >Sensibilité des documents</label>
            <select
              id="sensibilite"
              v-model="form.sensitivity"
              class="fr-select"
            >
              <option
                v-for="s in SENSIBILITES"
                :key="s.valeur"
                :value="s.valeur"
              >
                {{ s.libelle }}
              </option>
            </select>
          </div>
          <fieldset class="fr-fieldset">
            <legend class="fr-fieldset__legend fr-text--regular">
              Options
            </legend>
            <div class="fr-fieldset__element">
              <div class="fr-checkbox-group">
                <input
                  id="graph"
                  v-model="form.graph_enabled"
                  type="checkbox"
                  @change="onGraphToggle"
                >
                <label
                  class="fr-label"
                  for="graph"
                >Liens entre documents
                  <span class="fr-hint-text">Cartographier les renvois entre documents (utile pour un code juridique).</span>
                </label>
              </div>
            </div>
            <div
              v-if="form.graph_enabled"
              class="fr-fieldset__element"
            >
              <div class="fr-checkbox-group">
                <input
                  id="ai_summary"
                  v-model="form.ai_summary_enabled"
                  type="checkbox"
                >
                <label
                  class="fr-label"
                  for="ai_summary"
                >Résumé IA des articles longs dans la carte des liens
                  <span class="fr-hint-text">Le texte d'origine n'est jamais modifié.</span>
                </label>
              </div>
            </div>
            <div class="fr-fieldset__element">
              <div class="fr-checkbox-group">
                <input
                  id="identifiant-manuel"
                  v-model="identifiantManuel"
                  type="checkbox"
                  @change="identifiantManuel || proposerIdentifiant()"
                >
                <label
                  class="fr-label"
                  for="identifiant-manuel"
                >Choisir l'identifiant moi-même</label>
              </div>
            </div>
          </fieldset>
          <div
            v-if="identifiantManuel"
            class="fr-input-group"
            :class="{ 'fr-input-group--error': nameStatus === 'taken' }"
          >
            <label
              class="fr-label"
              for="name"
            >Identifiant
              <span class="fr-hint-text">Minuscules, chiffres et tirets. C'est ce que taperont les applications : <code>openrag-{{ form.name || 'identifiant' }}</code>.</span>
            </label>
            <input
              id="name"
              v-model="form.name"
              class="fr-input"
              placeholder="codes-natinf"
              @input="nameStatus = ''; programmerVerification()"
              @blur="checkDuplicates"
            >
          </div>
        </div>
      </section>

      <div
        v-if="error"
        class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"
        role="alert"
      >
        <p>{{ error }}</p>
      </div>
    </template>

    <template #encadre>
      <h2 class="fr-callout__title fr-h6">
        Les étapes
      </h2>
      <ol class="fr-callout__text fr-text--sm">
        <li><strong>Titre :</strong> donnez un nom explicite pour retrouver la collection facilement.</li>
        <li><strong>Description :</strong> expliquez son contexte d'utilisation et ce qu'on peut lui demander.</li>
        <li><strong>Catégorie et accès :</strong> rangez-la dans le catalogue et dites qui peut l'interroger.</li>
        <li><strong>Responsable :</strong> la personne que vos collègues contacteront pour contribuer.</li>
      </ol>
      <p class="fr-text--xs fr-mb-0">
        Une collection proche existe déjà ? Nous vous le dirons avant de créer la vôtre.
      </p>
    </template>

    <template #actions>
      <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-md">
        <li>
          <NuxtLink
            to="/"
            class="fr-btn fr-btn--tertiary-no-outline"
          >
            Annuler
          </NuxtLink>
        </li>
        <li>
          <NuxtLink
            to="/admin/create"
            class="fr-btn fr-btn--secondary"
          >
            Étape précédente
          </NuxtLink>
        </li>
        <li>
          <button
            type="button"
            class="fr-btn"
            :disabled="creating || !pret"
            @click="createAndNext"
          >
            {{ creating ? 'Création…' : 'Étape suivante' }}
          </button>
        </li>
      </ul>
    </template>
  </WizardEtape>
</template>

<style scoped>
.etape2-groupes { list-style: none; margin: .5rem 0 0; padding: 0; border: 1px solid var(--border-default-grey); max-height: 10rem; overflow-y: auto; }
.etape2-discret { color: var(--text-mention-grey); }
</style>
