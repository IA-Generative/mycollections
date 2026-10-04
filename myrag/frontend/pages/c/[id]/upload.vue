<template>
  <div>
    <FilAriane :collection="id" :titre="titre" rubrique="Ajouter des documents" />

    <h1 class="fr-h3">Ajouter des documents — {{ titre }}</h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-8">
        <!-- File upload -->
        <div class="fr-upload-group">
          <label class="fr-label" for="file">Document à ajouter</label>
          <input id="file" type="file" class="fr-upload" @change="onFileChange"
                 accept=".pdf,.txt,.md,.docx,.pptx,.doc,.eml,.png,.jpeg,.jpg" />
        </div>

        <!-- Strategy -->
        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label" for="strategy">Découpage du document
            <span class="fr-hint-text">Comment le document est coupé en passages, que l'assistant retrouve et cite.</span>
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
        <button class="fr-btn fr-mt-4w" @click="upload" :disabled="!file || uploading">
          {{ uploading ? 'Envoi en cours…' : 'Ajouter le document' }}
        </button>

        <!-- Result -->
        <div v-if="result" class="fr-alert fr-alert--success fr-mt-4w">
          <p>Document reçu et découpé en {{ result.total_chunks }} passage(s) : son ajout à la collection se poursuit.</p>
          <p class="fr-text--sm">Suivi du traitement : <a :href="`${baseUrl}/api/ingest/jobs/${result.job_id}`" target="_blank">{{ result.job_id }}</a></p>
        </div>

        <div v-if="error" class="fr-alert fr-alert--error fr-mt-4w">
          <p>{{ error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
const { uploadFile, baseUrl } = useApi()

const file = ref<File | null>(null)
const strategy = ref('auto')
const sensitivity = ref('public')
const uploading = ref(false)
const result = ref<any>(null)
const error = ref('')

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  file.value = input.files?.[0] || null
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  result.value = null
  error.value = ''

  try {
    result.value = await uploadFile(`/api/ingest/${id}`, file.value, {
      strategy: strategy.value,
      sensitivity: sensitivity.value,
    })
  } catch (e: any) {
    error.value = e.message
  } finally {
    uploading.value = false
  }
}
</script>
