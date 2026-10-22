<script setup lang="ts">
import { ACCEPT, etatDepot, FORMATS_LISIBLES, libelleEtatDepot, passages } from '~/utils/depot'

const route = useRoute()
const router = useRouter()
const collection = route.query.collection as string
const source = (route.query.source as string) || ''
const { uploadFile, post, get } = useApi()

const tab = ref<'file' | 'url'>('file')
const file = ref<File | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploaded = ref(false)
const uploadedName = ref('')
const job = ref<any>(null)
const remoteUrl = ref('')
const remoteCheck = ref<{ status: string, contentType?: string, size?: number, message?: string, githubConverted?: boolean } | null>(null)
const uploadError = ref('')
const decoupageOuvert = ref(false)
// --- Répertoire local ---
const zone = ref<{ deposer: () => Promise<void> } | null>(null)
const dossierPret = ref(false)
const dossierLance = ref(false)

// --- Drive picker state ---
interface DriveItem { id: string, title: string, type: 'FOLDER' | 'FILE', size?: number, updated_at?: string }
const driveReady = ref(false)
const driveLoading = ref(false)
const driveIndexing = ref(false)
const driveError = ref('')
const driveUrl = ref('')
const driveItems = ref<DriveItem[]>([])
const drivePath = ref<DriveItem[]>([]) // breadcrumb stack (folders traversed)

const ERREUR_API = /^API error \d+: (.*)$/s
const DEPOT_GITHUB = /^https?:\/\/github\.com\/[^/]+\/[^/]+\/?$/
const ARBRE_GITHUB = /^https?:\/\/github\.com\/[^/]+\/[^/]+\/tree\//
const FICHIER_GITHUB = /^https?:\/\/github\.com\/([^/]+)\/([^/]+)\/blob\/(.+)$/

function parseApiError (raw: string, fallback: string): string {
  // useApi throws "API error <code>: <body>" — pull out the backend detail
  // so we show a readable sentence instead of JSON noise.
  const m = ERREUR_API.exec(raw || '')
  if (!m) {
    return raw || fallback
  }
  try {
    const body = JSON.parse(m[1])
    return body.detail || body.message || m[1]
  }
  catch {
    return m[1]
  }
}

async function loadDriveFolder (parentId: string | null) {
  driveLoading.value = true
  driveError.value = ''
  try {
    const params: Record<string, string> = {}
    if (parentId) {
      params.parent_id = parentId
    }
    const res = await get('/api/sources/drive/folders', params)
    driveItems.value = res.items || []
    driveReady.value = true
  }
  catch (e: any) {
    driveError.value = parseApiError(e?.message, 'Erreur de chargement Drive')
    driveReady.value = false
  }
  finally {
    driveLoading.value = false
  }
}

async function enterFolder (item: DriveItem) {
  drivePath.value = [...drivePath.value, item]
  await loadDriveFolder(item.id)
}

async function goBack (index: number) {
  // index === -1 → back to root
  drivePath.value = index >= 0 ? drivePath.value.slice(0, index + 1) : []
  const parent = drivePath.value.at(-1)
  await loadDriveFolder(parent?.id || null)
}

async function indexDriveFolder () {
  if (!drivePath.value.length) {
    return
  }
  const folder = drivePath.value.at(-1)
  driveIndexing.value = true
  driveError.value = ''
  try {
    await post('/api/sources/drive/add', {
      collection,
      folder_id: folder.id,
      folder_title: folder.title,
    })
    // Redirect to step 4 — the import runs async server-side; step-4 can poll /api/ingest/jobs
    router.push({ path: '/admin/create/step-4', query: { collection, source: 'drive' } })
  }
  catch (e: any) {
    driveError.value = parseApiError(e?.message, 'Erreur lors du lancement de l\'import Drive')
  }
  finally {
    driveIndexing.value = false
  }
}
const previewContent = ref<string | null>(null)
const previewLoading = ref(false)
const previewTruncated = ref(false)
const previewMaxChars = 4000

const isReadyToUpload = computed(() => {
  if (tab.value === 'file') {
    return !!file.value
  }
  if (tab.value === 'url') {
    return remoteCheck.value?.status === 'ok'
  }
  return false
})

const champFichier = ref<HTMLInputElement | null>(null)

function onFile (e: Event) {
  file.value = (e.target as HTMLInputElement).files?.[0] || null
}

function formatSize (bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} o`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} Ko`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
}

function isPreviewableText (contentType: string): boolean {
  return contentType.startsWith('text/') || ['application/json', 'application/xml', 'application/javascript'].includes(contentType)
}

/**
 * Detect GitHub URLs and normalize them.
 * - Repo root (github.com/user/repo) → error, not a file
 * - Blob URL (github.com/user/repo/blob/branch/file) → raw.githubusercontent.com/...
 * - Already raw → pass through
 */
function isGithubRepoUrl (url: string): boolean {
  return DEPOT_GITHUB.test(url) || ARBRE_GITHUB.test(url)
}

function normalizeGithubUrl (url: string): string {
  const match = url.match(FICHIER_GITHUB)
  if (match) {
    return `https://raw.githubusercontent.com/${match[1]}/${match[2]}/${match[3]}`
  }
  return url
}

async function handleMainAction () {
  if (tab.value === 'file') {
    await uploadLocalFile()
  }
  else {
    await uploadRemoteUrl()
  }
}

async function uploadLocalFile () {
  if (!file.value) {
    return
  }
  uploading.value = true
  uploadProgress.value = 0

  const progressInterval = setInterval(() => {
    if (uploadProgress.value < 90) {
      uploadProgress.value += 10
    }
  }, 200)

  try {
    const result = await uploadFile(`/api/ingest/${collection}`, file.value, {
      strategy: 'auto',
      sensitivity: 'public',
    })
    clearInterval(progressInterval)
    uploadProgress.value = 100
    uploadedName.value = file.value.name
    uploading.value = false
    uploaded.value = true
    job.value = result

    pollJob(result.job_id)
  }
  catch {
    clearInterval(progressInterval)
    uploading.value = false
    uploadError.value = 'Erreur lors du chargement du fichier. Vérifiez que le service répond, puis réessayez.'
  }
}

async function uploadRemoteUrl () {
  uploading.value = true
  uploadProgress.value = 0

  const progressInterval = setInterval(() => {
    if (uploadProgress.value < 90) {
      uploadProgress.value += 15
    }
  }, 300)

  try {
    const result = await post(`/api/ingest/${collection}/from-url`, {
      url: remoteUrl.value,
      strategy: 'auto',
      sensitivity: 'public',
    })
    clearInterval(progressInterval)
    uploadProgress.value = 100
    uploadedName.value = remoteUrl.value.split('/').pop() || remoteUrl.value
    uploading.value = false
    uploaded.value = true

    if (result?.job_id) {
      job.value = result
      pollJob(result.job_id)
    }
  }
  catch {
    clearInterval(progressInterval)
    uploading.value = false
    uploadError.value = 'Erreur lors du chargement. Vérifiez que le service répond, puis réessayez.'
  }
}

function pollJob (jobId: string) {
  const pollInterval = setInterval(async () => {
    try {
      const j = await get(`/api/ingest/jobs/${jobId}`)
      job.value = j
      if (j.status === 'done' || j.status === 'done_with_errors') {
        clearInterval(pollInterval)
      }
    }
    catch {}
  }, 2000)
}

watch(remoteUrl, () => {
  remoteCheck.value = null
  previewContent.value = null
  previewTruncated.value = false
})

async function loadPreview (url: string, contentType: string) {
  // Only preview text-based formats
  if (!isPreviewableText(contentType)) {
    previewContent.value = null
    return
  }
  previewLoading.value = true
  try {
    const resp = await get(`/api/sources/preview-url?url=${encodeURIComponent(url)}&max_chars=${previewMaxChars}`)
    if (resp?.content) {
      previewContent.value = resp.content
      previewTruncated.value = resp.truncated || false
    }
  }
  catch {
    previewContent.value = null
  }
  finally {
    previewLoading.value = false
  }
}

async function checkRemoteUrl () {
  if (!remoteUrl.value) {
    return
  }

  // Reject GitHub repo/tree URLs (not a file)
  if (isGithubRepoUrl(remoteUrl.value)) {
    remoteCheck.value = {
      status: 'error',
      message: 'Cette URL pointe vers un dépôt ou dossier GitHub, pas un fichier. Utilisez l\'URL d\'un fichier spécifique (bouton "Raw" ou lien vers un fichier dans le dépôt).',
    }
    return
  }

  // Auto-convert GitHub blob URLs to raw
  const normalized = normalizeGithubUrl(remoteUrl.value)
  const wasConverted = normalized !== remoteUrl.value
  if (wasConverted) {
    remoteUrl.value = normalized
  }

  remoteCheck.value = { status: 'checking' }

  try {
    const resp = await get(`/api/sources/check-url?url=${encodeURIComponent(remoteUrl.value)}`)
    if (resp?.accessible) {
      remoteCheck.value = {
        status: 'ok',
        contentType: resp.content_type || 'inconnu',
        size: resp.content_length || undefined,
        githubConverted: wasConverted,
      }
      loadPreview(remoteUrl.value, resp.content_type || '')
    }
    else {
      const detail = resp?.error
        ? `Erreur : ${resp.error}`
        : resp?.status_code
          ? `Le serveur a répondu HTTP ${resp.status_code}.`
          : 'Le document n\'est pas accessible.'
      remoteCheck.value = { status: 'error', message: `${detail} Vérifiez l'URL et que le fichier est public.` }
    }
  }
  catch {
    remoteCheck.value = { status: 'error', message: 'Impossible de vérifier cette adresse pour le moment.' }
  }
}

function next () {
  router.push(`/admin/create/step-4?collection=${collection}`)
}

// Résana : le choix du dossier vit dans DepotChoixResana ; le bouton d'import reste en bas, comme ailleurs.
const choixResana = ref<{ importer: () => Promise<void> } | null>(null)
const resanaPret = ref(false)
const resanaLance = ref(false)

onMounted(async () => {
  if (source === 'drive') {
    try {
      const cfg = await get('/api/config')
      driveUrl.value = cfg.drive_url || ''
    }
    catch { /* non-blocking — link just won't appear */ }
    loadDriveFolder(null)
  }
})
</script>

<template>
  <WizardEtape
    :numero="3"
    titre="Déposez vos documents"
    chapeau="Tels quels, sans les préparer. L'assistant les lit, les découpe en passages et les indexe pendant que vous continuez."
  >
    <template #formulaire>
      <div
        v-if="!collection"
        class="fr-alert fr-alert--warning fr-mb-4w"
      >
        <p>
          Aucune collection indiquée. <NuxtLink to="/admin/create">
            Retour à l'étape 1
          </NuxtLink>
        </p>
      </div>

      <div v-else>
        <!-- Drive folder picker (when source=drive) -->
        <div
          v-if="source === 'drive'"
          class="fr-card fr-mb-4w"
        >
          <div class="fr-card__body">
            <div class="fr-card__content">
              <h3 class="fr-h5">
                ☁️ Choisir un dossier Drive à indexer
              </h3>

              <div
                v-if="!driveReady"
                class="fr-alert fr-alert--warning fr-alert--sm fr-mt-2w"
              >
                <p>{{ driveError || 'Chargement du service Drive…' }}</p>
                <p
                  v-if="driveError && driveUrl"
                  class="fr-mt-1w"
                >
                  <a
                    :href="driveUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Ouvrir Drive dans un nouvel onglet ↗
                  </a>
                </p>
              </div>

              <div v-else>
                <!-- Breadcrumb -->
                <nav
                  class="fr-breadcrumb"
                  aria-label="Chemin Drive"
                >
                  <ol class="fr-breadcrumb__list">
                    <li>
                      <a
                        class="fr-breadcrumb__link"
                        href="#"
                        @click.prevent="goBack(-1)"
                      >Racine</a>
                    </li>
                    <li
                      v-for="(f, idx) in drivePath"
                      :key="f.id"
                    >
                      <a
                        class="fr-breadcrumb__link"
                        href="#"
                        @click.prevent="goBack(idx)"
                      >{{ f.title }}</a>
                    </li>
                  </ol>
                </nav>

                <!-- Items list -->
                <ul
                  class="fr-mt-2w"
                  style="list-style:none;padding:0;"
                >
                  <li
                    v-for="item in driveItems"
                    :key="item.id"
                    class="fr-mb-1w"
                  >
                    <button
                      v-if="item.type === 'FOLDER'"
                      class="fr-btn fr-btn--tertiary fr-btn--sm fr-icon-folder-2-line fr-btn--icon-left"
                      :disabled="driveLoading"
                      @click="enterFolder(item)"
                    >
                      {{ item.title || '(sans nom)' }}
                    </button>
                    <span
                      v-else
                      class="fr-text--sm"
                      style="color:#666;"
                    >
                      <span
                        class="fr-icon-file-line"
                        aria-hidden="true"
                      />
                      {{ item.title || '(sans nom)' }}
                      <span
                        v-if="item.size"
                        style="color:#999;"
                      > — {{ formatSize(item.size) }}</span>
                    </span>
                  </li>
                  <li
                    v-if="!driveItems.length && !driveLoading"
                    class="fr-text--sm"
                    style="color:#666;"
                  >
                    (Dossier vide)
                  </li>
                </ul>

                <!-- Index current folder button -->
                <div
                  v-if="drivePath.length"
                  class="fr-mt-3w"
                >
                  <p class="fr-text--sm fr-mb-1w">
                    <strong>Dossier courant :</strong> {{ drivePath[drivePath.length - 1].title }}
                    ({{ driveItems.filter(i => i.type === 'FILE').length }} fichier(s) visible(s))
                  </p>
                  <button
                    class="fr-btn"
                    :disabled="driveIndexing"
                    @click="indexDriveFolder"
                  >
                    {{ driveIndexing ? 'Import en cours…' : 'Indexer ce dossier →' }}
                  </button>
                </div>
                <p
                  v-else
                  class="fr-text--sm fr-mt-2w"
                  style="color:#666;"
                >
                  Ouvrez un dossier pour pouvoir l'indexer.
                </p>

                <div
                  v-if="driveError"
                  class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"
                >
                  <p>{{ driveError }}</p>
                  <p
                    v-if="driveUrl"
                    class="fr-mt-1w"
                  >
                    <a
                      :href="driveUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Ouvrir Drive dans un nouvel onglet ↗
                    </a>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Répertoire local : un dossier entier (ou plusieurs), chaque fichier suivi jusqu'à l'indexation -->
        <div
          v-if="source === 'directory'"
          class="fr-card fr-mb-4w"
        >
          <div class="fr-card__body">
            <div class="fr-card__content">
              <h3 class="fr-h5">
                📁 Choisir le dossier à indexer
              </h3>
              <p class="fr-text--sm">
                Les fichiers texte sont découpés automatiquement ; les PDF, Word et autres documents sont lus et découpés
                par le moteur de recherche. Vous pourrez en ajouter d'autres plus tard, depuis la fiche de la collection.
              </p>
              <DepotZone
                ref="zone"
                :collection="collection"
                titre="Dossier à indexer"
                dossier-seul
                sans-bouton
                @selection="n => dossierPret = n > 0"
                @lance="dossierLance = true"
              />
            </div>
          </div>
        </div>

        <template v-if="source === 'resana'">
          <DepotChoixResana
            v-if="!resanaLance"
            ref="choixResana"
            :collection="collection"
            @pret="resanaPret = $event"
            @lance="resanaLance = true"
          />
          <DepotEtatResana
            v-else
            :collection="collection"
          />
        </template>

        <!-- Source selector (upload file / URL) — hidden when Drive picker or a folder is active -->
        <div
          v-if="source !== 'drive' && source !== 'directory' && source !== 'resana'"
          class="fr-card fr-mb-4w"
        >
          <div class="fr-card__body">
            <div class="fr-card__content">
              <div class="fr-segmented fr-segmented--sm fr-mt-2w fr-mb-2w">
                <div class="fr-segmented__elements">
                  <div class="fr-segmented__element">
                    <input
                      id="tab-file"
                      v-model="tab"
                      type="radio"
                      name="upload-mode"
                      value="file"
                      :disabled="uploaded"
                    >
                    <label
                      class="fr-label"
                      for="tab-file"
                    >📄 Fichier local</label>
                  </div>
                  <div class="fr-segmented__element">
                    <input
                      id="tab-url"
                      v-model="tab"
                      type="radio"
                      name="upload-mode"
                      value="url"
                      :disabled="uploaded"
                    >
                    <label
                      class="fr-label"
                      for="tab-url"
                    >🌐 URL distante</label>
                  </div>
                </div>
              </div>

              <!-- Mode: Fichier local -->
              <div v-if="tab === 'file' && !uploaded">
                <div class="fr-upload-group fr-mt-2w">
                  <label
                    class="fr-label"
                    for="depot-fichier"
                  >
                    Déposer un fichier depuis votre ordinateur
                    <span class="fr-hint-text">Formats acceptés : {{ FORMATS_LISIBLES }}. Pour déposer plusieurs fichiers ou un dossier entier, utilisez ensuite « Ajouter des documents » sur la fiche de la collection.</span>
                  </label>
                  <!-- Le champ natif écrit « Choose File » dans la langue du navigateur : on le masque et un
                       bouton DSFR en français l'ouvre. Il reste dans l'arbre d'accessibilité (label ci-dessus). -->
                  <input
                    id="depot-fichier"
                    ref="champFichier"
                    type="file"
                    class="fr-sr-only"
                    :accept="ACCEPT"
                    @change="onFile"
                  >
                  <button
                    type="button"
                    class="fr-btn fr-btn--secondary fr-icon-upload-line fr-btn--icon-left fr-mt-1w"
                    @click="champFichier?.click()"
                  >
                    Choisir un fichier
                  </button>
                </div>

                <div
                  v-if="file"
                  class="fr-mt-2w"
                >
                  <p class="fr-text--sm">
                    Fichier sélectionné : <strong>{{ file.name }}</strong> ({{ formatSize(file.size) }})
                  </p>
                </div>
              </div>

              <!-- Mode: URL distante -->
              <div v-if="tab === 'url' && !uploaded">
                <div class="fr-input-group fr-mt-2w">
                  <label class="fr-label">
                    URL d'un fichier unique accessible en ligne
                    <span class="fr-hint-text">Lien direct vers un fichier : {{ FORMATS_LISIBLES }}.</span>
                  </label>
                  <input
                    v-model="remoteUrl"
                    class="fr-input"
                    placeholder="https://example.gouv.fr/documents/rapport.pdf"
                  >
                </div>

                <!-- Vérification -->
                <div
                  v-if="remoteUrl && (!remoteCheck || remoteCheck.status === 'error')"
                  class="fr-mt-1w"
                >
                  <button
                    class="fr-btn fr-btn--tertiary fr-btn--sm"
                    @click="checkRemoteUrl"
                  >
                    Vérifier l'accessibilité
                  </button>
                </div>

                <div
                  v-if="remoteCheck && remoteCheck.status === 'checking'"
                  class="fr-mt-1w"
                >
                  <p
                    class="fr-text--sm"
                    style="color:#666;"
                  >
                    Vérification en cours…
                  </p>
                </div>

                <div
                  v-if="remoteCheck && remoteCheck.status === 'error'"
                  class="fr-alert fr-alert--error fr-alert--sm fr-mt-1w"
                >
                  <p>{{ remoteCheck.message }}</p>
                </div>

                <!-- Verification OK: info + preview -->
                <div
                  v-if="remoteCheck && remoteCheck.status === 'ok'"
                  class="fr-mt-2w"
                >
                  <div class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w">
                    <p>
                      Document accessible — <strong>{{ remoteCheck.contentType }}</strong>
                      <span v-if="remoteCheck.size"> — {{ formatSize(remoteCheck.size) }}</span>
                    </p>
                    <p
                      v-if="remoteCheck.githubConverted"
                      class="fr-text--sm fr-mt-1v"
                    >
                      L'URL GitHub a été convertie automatiquement vers le fichier brut (raw).
                    </p>
                  </div>

                  <details
                    class="fr-mb-1w"
                    open
                  >
                    <summary
                      class="fr-text--sm"
                      style="cursor:pointer;font-weight:bold;"
                    >
                      Aperçu du document
                    </summary>
                    <div class="myrag-preview-frame fr-mt-1w">
                      <!-- Text preview fetched via backend -->
                      <div
                        v-if="previewContent !== null"
                        class="myrag-preview-content"
                      >
                        <pre>{{ previewContent }}</pre>
                        <p
                          v-if="previewTruncated"
                          class="fr-text--xs"
                          style="color:#666;text-align:center;margin-top:0.5rem;"
                        >
                          ... affichage limité aux {{ previewMaxChars }} premiers caractères
                        </p>
                      </div>
                      <div
                        v-else-if="previewLoading"
                        style="text-align:center;padding:2rem;color:#666;"
                      >
                        Chargement de l'aperçu…
                      </div>
                      <div
                        v-else
                        class="myrag-preview-placeholder"
                      >
                        <p
                          class="fr-text--sm"
                          style="text-align:center;color:#666;padding:2rem;"
                        >
                          Aperçu non disponible pour le format <strong>{{ remoteCheck.contentType }}</strong>.<br>
                          Le document sera téléchargé et indexé directement.
                        </p>
                      </div>
                    </div>
                  </details>
                </div>
              </div>

              <!-- Upload progress bar (shown during upload for both modes) -->
              <div
                v-if="uploading"
                class="fr-mt-2w"
              >
                <progress
                  style="width:100%;"
                  :value="uploadProgress"
                  max="100"
                />
                <p class="fr-text--sm">
                  Envoi en cours... {{ uploadProgress }}%
                </p>
              </div>

              <!-- Upload done confirmation -->
              <div
                v-if="uploaded"
                class="fr-alert fr-alert--success fr-alert--sm fr-mt-2w"
              >
                <p>
                  <strong>{{ uploadedName }}</strong> est déposé.
                  Il est indexé en tâche de fond : vous pouvez passer à l'étape suivante.
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- Le document déposé, suivi jusqu'à ce qu'il soit prêt ; l'étape suivante n'attend pas. -->
        <div
          v-if="job"
          class="etape3-suivi fr-mb-4w"
          aria-live="polite"
        >
          <div class="etape3-suivi__ligne">
            <span class="etape3-suivi__nom">{{ uploadedName || 'Votre document' }}</span>
            <span class="fr-text--sm etape3-discret">
              <template v-if="passages(job.total_chunks)">{{ passages(job.total_chunks) }} · </template>{{ libelleEtatDepot(etatDepot(job)) }}
            </span>
          </div>
          <p
            v-if="etatDepot(job) === 'decoupage'"
            class="fr-badge fr-badge--info fr-badge--no-icon fr-mt-1w fr-mb-0"
          >
            Indexation en cours, vous pouvez continuer
          </p>
        </div>

        <!-- Upload error -->
        <div
          v-if="uploadError"
          class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
        >
          <p>{{ uploadError }}</p>
        </div>

        <p
          v-if="source === 'directory'"
          class="fr-hint-text fr-mt-1w"
        >
          <span v-if="!dossierPret && !dossierLance">Choisissez un dossier pour continuer.</span>
          <span v-else-if="!dossierLance">Cliquez sur « Déposer le dossier » : les fichiers partent un par un.</span>
          <span v-else>L'indexation se poursuit : vous pouvez passer à l'étape suivante sans attendre.</span>
        </p>
        <p
          v-else-if="source === 'resana'"
          class="fr-hint-text fr-mt-1w"
        >
          <span v-if="!resanaLance">Choisissez un espace puis un dossier pour continuer.</span>
          <span v-else>L'import se poursuit : vous pouvez passer à l'étape suivante sans attendre.</span>
        </p>
        <p
          v-else-if="!uploaded && !uploading"
          class="fr-hint-text fr-mt-1w"
        >
          <span v-if="tab === 'file' && !file">Sélectionnez un fichier pour continuer.</span>
          <span v-else-if="tab === 'url' && (!remoteCheck || remoteCheck.status !== 'ok')">Saisissez une adresse et vérifiez qu'elle est accessible.</span>
          <span v-else>Cliquez sur « Déposer le document » : il est lu, découpé et indexé pendant que vous continuez.</span>
        </p>

        <!-- Le découpage, expliqué sans jargon et replié. -->
        <section class="fr-accordion fr-mt-4w">
          <h2 class="fr-accordion__title">
            <button
              type="button"
              class="fr-accordion__btn"
              :aria-expanded="decoupageOuvert ? 'true' : 'false'"
              aria-controls="etape3-decoupage"
              @click="decoupageOuvert = !decoupageOuvert"
            >
              Comment sont découpés les documents ?
            </button>
          </h2>
          <div
            id="etape3-decoupage"
            class="fr-collapse"
            :class="{ 'fr-collapse--expanded': decoupageOuvert }"
          >
            <p class="fr-text--sm">
              Le découpage suit le type de collection choisi à l'étape précédente : par article pour un code, par question pour une FAQ,
              par section pour un rapport. Vous pourrez le voir et le changer depuis les réglages et la page Qualité de la collection.
            </p>
          </div>
        </section>
      </div>
    </template>

    <template #encadre>
      <h2 class="fr-callout__title fr-h6">
        Ce qui se passe
      </h2>
      <ol class="fr-callout__text fr-text--sm">
        <li><strong>Lecture :</strong> chaque fichier est converti en texte, même un PDF.</li>
        <li><strong>Découpage :</strong> le texte est coupé en passages courts, pour que l'assistant cite le bon endroit.</li>
        <li><strong>Indexation :</strong> les passages deviennent interrogeables en quelques minutes, en tâche de fond.</li>
      </ol>
      <p class="fr-text--xs fr-mb-0">
        Rien n'est définitif : vous pourrez ajouter, remplacer ou retirer des documents à tout moment.
      </p>
    </template>

    <template
      v-if="collection"
      #actions
    >
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
            :to="`/admin/create/step-2?source=${source}`"
            class="fr-btn fr-btn--secondary"
          >
            Étape précédente
          </NuxtLink>
        </li>
        <li v-if="source === 'directory'">
          <button
            v-if="dossierLance"
            type="button"
            class="fr-btn"
            @click="next"
          >
            Étape suivante
          </button>
          <button
            v-else
            type="button"
            class="fr-btn"
            :disabled="!dossierPret"
            @click="zone?.deposer()"
          >
            Déposer le dossier
          </button>
        </li>
        <li v-else-if="source === 'resana'">
          <button
            v-if="resanaLance"
            type="button"
            class="fr-btn"
            @click="next"
          >
            Étape suivante
          </button>
          <button
            v-else
            type="button"
            class="fr-btn"
            :disabled="!resanaPret"
            @click="choixResana?.importer()"
          >
            Importer le dossier
          </button>
        </li>
        <li v-else-if="uploaded">
          <button
            type="button"
            class="fr-btn"
            @click="next"
          >
            Étape suivante
          </button>
        </li>
        <li v-else>
          <button
            type="button"
            class="fr-btn"
            :disabled="!isReadyToUpload || uploading"
            @click="handleMainAction"
          >
            {{ uploading ? 'Envoi en cours…' : 'Déposer le document' }}
          </button>
        </li>
      </ul>
    </template>
  </WizardEtape>
</template>

<style scoped>
.etape3-suivi { padding: .75rem 1rem; border: 1px solid var(--border-default-grey); }
.etape3-suivi__ligne { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .5rem 1rem; }
.etape3-suivi__nom { font-weight: 500; overflow-wrap: anywhere; }
.etape3-discret { color: var(--text-mention-grey); }
.myrag-preview-frame {
  max-height: 320px;
  overflow: hidden;
  border-radius: 4px;
}

.myrag-preview-content {
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #f6f6f6;
  max-height: 300px;
  overflow-y: auto;
}

.myrag-preview-content pre {
  margin: 0;
  padding: 1rem;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.8rem;
  line-height: 1.5;
}

.myrag-preview-placeholder {
  border: 1px dashed #ccc;
  border-radius: 4px;
  background: #f9f9f9;
}
</style>
