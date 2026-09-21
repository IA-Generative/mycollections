<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ titre }}</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Réglages</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Réglages — {{ titre }}</h1>

    <div v-if="loading" class="fr-callout"><p>Chargement…</p></div>

    <div v-else class="fr-col-8">
      <!-- État de partage : où cette collection est-elle servie ? -->
      <div class="fr-callout fr-mb-2w" :class="estServie ? 'fr-callout--green-emeraude' : ''">
        <h2 class="fr-callout__title fr-h6">Partage</h2>
        <p v-if="estServie" class="fr-callout__text fr-text--sm">
          Cette collection est <strong>partagée</strong> — disponible dans :
          <span v-for="t in partage.targets" :key="t.app" class="fr-badge fr-badge--sm fr-badge--success fr-ml-1v"
                :title="t.model_id">{{ appLabel(t.app) }}</span>
          <br />
          Nom dans l'assistant : <strong>{{ partage.alias_name || '—' }}</strong> ·
          Visible par : <strong>{{ visibiliteLabel(partage.visibility) }}</strong>
          <span v-if="partage.published_at"> · depuis le {{ partage.published_at.slice(0, 10) }}</span>
        </p>
        <p v-else class="fr-callout__text fr-text--sm">
          Cette collection <strong>n'est partagée dans aucune application</strong>
          ({{ etatLabel(partage.state) }}) : elle n'apparaît pas dans l'assistant.
        </p>
        <NuxtLink :to="`/c/${id}/publish`" class="fr-btn fr-btn--sm fr-btn--secondary fr-btn--icon-left fr-icon-share-forward-line fr-mt-1w"
                  title="Rendre la collection disponible dans Mon assistant, et choisir qui la voit.">
          {{ estServie ? 'Modifier le partage' : 'Partager dans Mon assistant' }}
        </NuxtLink>
      </div>

      <!-- Titre affiché -->
      <div class="fr-input-group">
        <label class="fr-label" for="titre-affiche">
          Titre affiché
          <span class="fr-hint-text">
            Ce que lisent vos collègues au catalogue et dans l'assistant — par exemple « Codes NATINF ».
            L'identifiant technique <code>{{ id }}</code>, lui, ne change pas : c'est celui que tapent les applications.
          </span>
        </label>
        <input id="titre-affiche" class="fr-input" type="text" maxlength="255" v-model="form.titre"
               :placeholder="titre" />
      </div>

      <!-- Description -->
      <div class="fr-input-group">
        <label class="fr-label">
          Description
          <span class="fr-hint-text">Ce texte apparaît dans le catalogue et aide les autres utilisateurs à trouver votre collection.</span>
        </label>
        <textarea class="fr-input" v-model="form.description" rows="2"
                  placeholder="Ex. : documentation juridique sur le droit des étrangers"></textarea>
        <div class="fr-mt-1w">
          <button class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-magic-line fr-btn--icon-left"
                  @click="guessDescription" :disabled="guessing">
            {{ guessing ? 'Analyse en cours…' : 'Proposer une description à partir des documents' }}
          </button>
          <span v-if="guessError" class="fr-text--sm fr-ml-2w" style="color:#ce0500;">
            {{ guessError }}
          </span>
        </div>
      </div>

      <!-- Type de collection (profil couplé) -->
      <div class="fr-select-group fr-mt-2w">
        <label class="fr-label">Type de collection
          <span class="fr-hint-text">Il règle ensemble la façon de découper les documents et les consignes données à l'assistant.</span>
        </label>
        <select class="fr-select" v-model="selectedProfile" @change="applyProfile">
          <option v-for="p in profiles" :key="p.key" :value="p.key">
            {{ p.icon }} {{ p.label }}
          </option>
        </select>
        <p class="fr-hint-text">{{ currentProfileDesc }}</p>
      </div>

      <!-- Reindex warning -->
      <div v-if="needsReindex" class="fr-alert fr-alert--warning fr-alert--sm fr-mt-2w">
        <p>
          <strong>Attention :</strong> vous avez modifié le type de collection (découpage des documents ou consignes).
          Les documents déjà ajoutés ne seront pas redécoupés automatiquement.
        </p>
        <div class="fr-btns-group fr-btns-group--inline fr-mt-1w">
          <button v-if="hasSourceFiles" class="fr-btn fr-btn--sm" @click="reindex" :disabled="reindexing">
            {{ reindexing ? 'Redécoupage en cours…' : 'Redécouper les documents selon le nouveau type' }}
          </button>
          <span v-else class="fr-text--sm" style="color:#666;">
            Aucun fichier d'origine enregistré —
            <NuxtLink :to="`/c/${id}/upload`" class="fr-link">ajoutez à nouveau vos documents</NuxtLink>.
          </span>
        </div>
        <div v-if="reindexResult" class="fr-mt-1w">
          <p class="fr-text--sm" style="color:#18753c;">
            Redécoupage lancé : {{ reindexResult.files_reindexed }} fichier(s) en cours de traitement.
          </p>
        </div>
      </div>

      <!-- Options -->
      <fieldset class="fr-fieldset fr-mt-2w">
        <legend class="fr-fieldset__legend">Options</legend>
        <div class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="graph" v-model="form.graph_enabled" />
            <label class="fr-label" for="graph">Activer les liens entre documents</label>
          </div>
          <details class="fr-mt-1w fr-ml-4w">
            <summary class="fr-text--sm" style="cursor:pointer;color:#000091;">En savoir plus sur les liens entre documents</summary>
            <div class="fr-callout fr-callout--green-emeraude fr-mt-1w">
              <p class="fr-callout__text fr-text--sm">
                Les <strong>liens entre documents</strong> cartographient les renvois entre les documents
                (renvois entre articles, références croisées). Ils permettent de naviguer visuellement
                et d'enrichir les réponses de l'assistant.
              </p>
            </div>
          </details>
        </div>
        <div v-if="form.graph_enabled" class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="ai_summary" v-model="form.ai_summary_enabled" />
            <label class="fr-label" for="ai_summary">Résumé automatique des articles longs dans la carte des liens</label>
          </div>
        </div>
        <div v-if="form.ai_summary_enabled" class="fr-fieldset__element fr-ml-4w">
          <div class="fr-input-group">
            <label class="fr-label">Longueur à partir de laquelle un article est résumé (en caractères)</label>
            <input class="fr-input" type="number" v-model.number="form.ai_summary_threshold" min="100" />
          </div>
        </div>
      </fieldset>

      <!-- Sensibilité + portée -->
      <div class="fr-grid-row fr-grid-row--gutters fr-mt-2w" style="align-items:flex-start;">
        <div class="fr-col-6">
          <div class="fr-select-group">
            <label class="fr-label">
              Sensibilité
              <span class="fr-hint-text">Niveau de classification des documents</span>
            </label>
            <select class="fr-select" v-model="form.sensitivity">
              <option value="public">Données ouvertes</option>
              <option value="internal">Interne au ministère</option>
              <option value="personal">Données personnelles</option>
              <option value="confidential">Confidentiel</option>
              <option value="restricted">Diffusion restreinte</option>
            </select>
          </div>
        </div>
        <div class="fr-col-6">
          <div class="fr-select-group">
            <label class="fr-label">
              Portée
              <span class="fr-hint-text">Qui pourra ouvrir cette collection dans Mes collections</span>
            </label>
            <select class="fr-select" v-model="form.scope">
              <option value="public">Tout le ministère</option>
              <option value="group">Un ou plusieurs groupes</option>
              <option value="private">Privé (pour évaluation)</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Contact -->
      <div class="fr-input-group fr-mt-3w">
        <label class="fr-label">Responsable / contact</label>
        <input class="fr-input" v-model="form.contact_name" placeholder="Nom du responsable" />
      </div>
      <div class="fr-input-group fr-mt-1w">
        <label class="fr-label">Email de contact</label>
        <input class="fr-input" type="email" v-model="form.contact_email" placeholder="responsable@example.com" />
      </div>

      <!-- Actions -->
      <div class="fr-btns-group fr-btns-group--inline fr-mt-4w">
        <NuxtLink :to="`/c/${id}`" class="fr-btn fr-btn--secondary">← Retour</NuxtLink>
        <button class="fr-btn" @click="save" :disabled="saving">
          {{ saving ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
      </div>

      <div v-if="savedMsg" class="fr-alert fr-mt-2w" :class="savedClass">
        <p>{{ savedMsg }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { titre, retenir } = useTitreCollection(id, { charger: false })
const { get, post, patch } = useApi()
const { user } = useAuth()

const loading = ref(true)
const saving = ref(false)
const savedMsg = ref('')
const savedClass = ref('fr-alert--success')
const isNew = ref(false)
const selectedProfile = ref('generique')
const initialStrategy = ref('')
const initialPrompt = ref('')
const guessing = ref(false)
const guessError = ref('')

const hasSourceFiles = ref(false)
const reindexing = ref(false)
const reindexResult = ref<any>(null)

const needsReindex = computed(() => {
  if (!initialStrategy.value) return false
  return form.value.strategy !== initialStrategy.value
    || form.value.prompt_template !== initialPrompt.value
})

const profiles = [
  { key: 'generique', icon: '📄', label: 'Générique', strategy: 'auto', prompt: 'generic', graph: false, desc: 'Pour tout type de document sans spécialisation. Découpage automatique.' },
  { key: 'juridique', icon: '⚖️', label: 'Juridique (codes, lois)', strategy: 'article', prompt: 'juridique', graph: true, desc: 'Découpage par article avec hiérarchie Livre/Titre/Chapitre. Citations d\'articles dans les réponses.' },
  { key: 'faq', icon: '❓', label: 'FAQ / Questions-réponses', strategy: 'qr', prompt: 'faq', graph: false, desc: 'Découpage par question/réponse. Réponses directes avec source.' },
  { key: 'technique', icon: '🔧', label: 'Documentation technique', strategy: 'section', prompt: 'technique', graph: false, desc: 'Découpage par section/chapitre. Références croisées entre sections.' },
  { key: 'multimedia', icon: '🎬', label: 'Multimédia (images, audio, vidéo)', strategy: 'auto', prompt: 'multimedia', graph: false, desc: 'Transcriptions audio, descriptions d\'images. Citations avec minutage.' },
  { key: 'multi', icon: '📚', label: 'Collection multi-thématique', strategy: 'auto', prompt: 'multi_thematique', graph: false, desc: 'Grande collection couvrant plusieurs domaines avec des documents variés.' },
]

const currentProfileDesc = computed(() => {
  return profiles.find(p => p.key === selectedProfile.value)?.desc || ''
})

const form = ref({
  titre: '',
  description: '',
  strategy: 'auto',
  sensitivity: 'public',
  scope: 'group',
  prompt_template: 'generic',
  graph_enabled: false,
  ai_summary_enabled: false,
  ai_summary_threshold: 1000,
  contact_name: '',
  contact_email: '',
})

// Etat de partage renvoye par GET /api/collections/{id} (cle `publication`).
const partage = ref<{ state: string, targets: any[], alias_name?: string,
                      visibility?: string, published_at?: string }>({ state: 'draft', targets: [] })
const estServie = computed(() => (partage.value.targets || []).length > 0)

function appLabel(app: string) {
  return { assistant: 'Mon assistant' }[app] || app
}

function etatLabel(s: string) {
  return { draft: 'brouillon, jamais partagée', disabled: 'partage désactivé',
           archived: 'archivée' }[s] || 'brouillon'
}

function visibiliteLabel(v?: string) {
  return { all: 'tous les utilisateurs connectés', group: 'groupes autorisés',
           users: 'utilisateurs nommés' }[v || ''] || v || '—'
}

function applyProfile() {
  const p = profiles.find(pr => pr.key === selectedProfile.value)
  if (p) {
    form.value.strategy = p.strategy
    form.value.prompt_template = p.prompt
    form.value.graph_enabled = p.graph
  }
}

onMounted(async () => {
  try {
    const config = await get(`/api/collections/${id}`)
    partage.value = config.publication || { state: 'draft', targets: [] }
    retenir(config)
    form.value = {
      titre: config.titre || '',
      description: config.description || '',
      strategy: config.strategy || 'auto',
      sensitivity: config.sensitivity || 'public',
      scope: config.scope || 'group',
      prompt_template: config.prompt_template || 'generic',
      graph_enabled: config.graph_enabled || false,
      ai_summary_enabled: config.ai_summary_enabled || false,
      ai_summary_threshold: config.ai_summary_threshold || 1000,
      contact_name: config.contact_name || '',
      contact_email: config.contact_email || '',
    }
    initialStrategy.value = form.value.strategy
    initialPrompt.value = form.value.prompt_template
    // Match profile from saved config
    const match = profiles.find(p => p.strategy === form.value.strategy && p.prompt === form.value.prompt_template)
    if (match) selectedProfile.value = match.key
  } catch {
    isNew.value = true
  }

  // Pre-fill contact from Keycloak profile if empty (same logic as wizard step 2)
  if (user.value?.profile) {
    const p = user.value.profile
    if (!form.value.contact_name) {
      form.value.contact_name = p.name || p.preferred_username || ''
    }
    if (!form.value.contact_email) {
      form.value.contact_email = p.email || ''
    }
  }

  // Check if source files exist for reindex
  try {
    const sources = await get(`/api/ingest/${id}/sources`)
    hasSourceFiles.value = (sources.sources?.length || 0) > 0
  } catch {}

  loading.value = false
})

/**
 * Ask the collection itself (via the RAG playground) to summarise its
 * own content. Useful when an orphan OpenRAG partition is adopted and
 * no description was ever written — we prompt the LLM to introspect.
 */
async function guessDescription() {
  guessing.value = true
  guessError.value = ''
  try {
    const result = await post(`/api/playground/${id}/chat`, {
      question:
        "Decris en 1 ou 2 phrases factuelles le contenu general de cette collection " +
        "pour qu'un autre utilisateur comprenne a quoi elle sert. " +
        "Pas d'introduction, pas de conclusion, pas de meta-commentaire. " +
        "Si tu n'as aucune information exploitable, reponds simplement 'Contenu non determinable'.",
      top_k: 5,
      temperature: 0.1,
    })
    const text = (result?.response || '').trim()
    if (!text || text.toLowerCase().startsWith('contenu non determinable')) {
      guessError.value = "Pas assez de contenu dans les documents pour en déduire une description."
    } else {
      form.value.description = text
    }
  } catch (e: any) {
    guessError.value = e?.message || 'Échec de la génération.'
  } finally {
    guessing.value = false
  }
}

async function reindex() {
  reindexing.value = true
  reindexResult.value = null
  try {
    const result = await post(`/api/ingest/${id}/reindex?strategy=${form.value.strategy}&sensitivity=${form.value.sensitivity}`, {})
    reindexResult.value = result
  } catch (e: any) {
    savedMsg.value = `Erreur pendant le redécoupage : ${e.message}`
    savedClass.value = 'fr-alert--error'
  }
  reindexing.value = false
}

async function save() {
  saving.value = true
  savedMsg.value = ''
  try {
    if (isNew.value) {
      await post('/api/collections', { name: id, ...form.value })
      isNew.value = false
    } else {
      await patch(`/api/collections/${id}`, form.value)
    }
    retenir({ name: id, titre: form.value.titre })
    savedMsg.value = 'Configuration sauvegardee. Retour a la liste dans un instant…'
    savedClass.value = 'fr-alert--success'
    // Leave the success banner visible briefly, then send the user back
    // to the home page listing all collections.
    setTimeout(() => { navigateTo('/') }, 1500)
  } catch (e: any) {
    savedMsg.value = `Erreur : ${e.message}`
    savedClass.value = 'fr-alert--error'
    setTimeout(() => { savedMsg.value = '' }, 4000)
  }
  saving.value = false
}
</script>
