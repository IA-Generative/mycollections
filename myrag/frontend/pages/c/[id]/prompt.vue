<template>
  <div>
    <FilAriane :collection="id" :titre="titre" rubrique="Consignes données à l'assistant" />

    <h1 class="fr-h3">Consignes données à l'assistant — {{ titre }}</h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <!-- Left: Editor -->
      <div class="fr-col-6">
        <h3 class="fr-h5">Rédaction</h3>

        <!-- Template selector -->
        <div class="fr-select-group fr-mb-2w">
          <label class="fr-label">Modèle de consignes</label>
          <select class="fr-select" v-model="selectedTemplate" @change="applyTemplate">
            <option value="">— Choisir un modèle —</option>
            <option v-for="tpl in templates" :key="tpl.key" :value="tpl.key">
              {{ tpl.icon }} {{ tpl.name }}
            </option>
          </select>
        </div>

        <!-- Prompt editor -->
        <div class="fr-input-group">
          <label class="fr-label">Consignes
            <span class="fr-hint-text">Ce que l'assistant lit avant chaque question : le ton, la façon de citer, ce qu'il doit refuser.</span>
          </label>
          <textarea class="fr-input" v-model="prompt" rows="18"
                    style="font-family:monospace;font-size:0.85rem;"></textarea>
        </div>

        <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
          <button class="fr-btn" @click="savePrompt" :disabled="saving">
            {{ saving ? 'Enregistrement…' : 'Enregistrer' }}
          </button>
          <button class="fr-btn fr-btn--secondary" @click="resetPrompt">
            Restaurer
          </button>
        </div>

        <div v-if="saved" class="fr-alert fr-alert--success fr-mt-2w">
          <p>Consignes enregistrées.</p>
        </div>
        <div v-if="erreurEnregistrement" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w" role="alert">
          <p>{{ erreurEnregistrement }}</p>
        </div>
      </div>

      <!-- Right: Playground -->
      <div class="fr-col-6">
        <h3 class="fr-h5">Test rapide</h3>

        <div class="fr-input-group">
          <label class="fr-label">Question de test</label>
          <input class="fr-input" v-model="testQuestion"
                 placeholder="Conditions carte vie privée ?" />
        </div>

        <button class="fr-btn fr-btn--sm fr-mt-1w" @click="testPrompt" :disabled="testing">
          {{ testing ? 'Test…' : 'Tester' }}
        </button>

        <div v-if="testResponse" class="fr-mt-2w">
          <h4 class="fr-h6">Réponse</h4>
          <div class="fr-p-2w" style="background:#f6f6f6;border-radius:4px;white-space:pre-wrap;font-size:0.85rem;max-height:400px;overflow-y:auto;">
            {{ testResponse }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
const { get, patch, post } = useApi()
const erreurEnregistrement = ref('')

const prompt = ref('')
const originalPrompt = ref('')
const templates = ref<any[]>([])
const selectedTemplate = ref('')
const saving = ref(false)
const saved = ref(false)

const testQuestion = ref('')
const testResponse = ref('')
const testing = ref(false)

async function applyTemplate() {
  if (!selectedTemplate.value) return
  try {
    const tpl = await get(`/api/collections/templates/${selectedTemplate.value}`)
    prompt.value = tpl.prompt
  } catch (e) {}
}

async function savePrompt() {
  saving.value = true
  try {
    await patch(`/api/collections/${id}/system-prompt`, { system_prompt: prompt.value })
    originalPrompt.value = prompt.value
    saved.value = true
    erreurEnregistrement.value = ''
    setTimeout(() => saved.value = false, 3000)
  } catch (e) {
    // Avant : l'échec était avalé, la personne croyait ses consignes enregistrées.
    erreurEnregistrement.value = `Les consignes n'ont pas été enregistrées : ${messageErreur(e)}`
  }
  saving.value = false
}

function resetPrompt() {
  if (prompt.value !== originalPrompt.value && !window.confirm('Revenir aux consignes enregistrées ? Vos modifications non enregistrées seront perdues.')) return
  prompt.value = originalPrompt.value
}

async function testPrompt() {
  if (!testQuestion.value.trim()) return
  testing.value = true
  testResponse.value = ''
  try {
    // Avec le jeton de la session (avant : un fetch nu, refusé en 401 dès que l'authentification est active).
    const data: any = await post(`/api/playground/${id}/chat`, { question: testQuestion.value, system_prompt: prompt.value })
    testResponse.value = data.response || 'Pas de réponse'
  } catch (e: any) {
    testResponse.value = messageErreur(e)
  }
  testing.value = false
}

onMounted(async () => {
  try {
    const data = await get(`/api/collections/${id}/system-prompt`)
    prompt.value = data.system_prompt || ''
    originalPrompt.value = prompt.value

    const tplData = await get('/api/collections/templates')
    templates.value = tplData.templates || []
  } catch (e) {}
})
</script>
