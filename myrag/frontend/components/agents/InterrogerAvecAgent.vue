<template>
  <section class="agents" aria-labelledby="agents-titre">
    <h3 id="agents-titre" class="fr-h5 fr-mb-1w">Interroger avec un agent</h3>
    <p class="fr-text--sm agents-explication">
      Un agent de Mes agents travaille sur les passages de cette collection qui répondent à votre
      question. Votre question et ces passages partent de votre navigateur vers Mes agents, avec
      votre session — rien ne transite par le serveur de Mes collections.
    </p>

    <p v-if="!fiches.length" class="fr-text--sm agents-vide">
      Aucun agent accessible n'accepte une collection pour l'instant.
    </p>

    <template v-else>
      <!-- Les fiches sont une donnée non fiable (contrat) : interpolées, jamais en HTML. -->
      <fieldset class="fr-fieldset" aria-labelledby="agents-legende">
        <legend id="agents-legende" class="fr-fieldset__legend fr-text--regular">Agent</legend>
        <div v-for="f in fiches" :key="f.id" class="fr-fieldset__element">
          <div class="fr-radio-group">
            <input type="radio" :id="`agent-${f.id}`" name="agent" :value="f.id" v-model="choisi" :disabled="enCours" />
            <label class="fr-label" :for="`agent-${f.id}`">
              <span class="agents-nom">
                {{ f.name }}
                <span class="fr-badge fr-badge--sm fr-badge--no-icon" :class="f.origin === 'mine' ? 'fr-badge--green-emeraude' : 'fr-badge--blue-cumulus'">{{ libelleOrigine(f.origin) }}</span>
                <span v-if="f.status === 'draft'" class="fr-badge fr-badge--sm fr-badge--no-icon">Brouillon</span>
              </span>
              <span v-if="f.description" class="fr-hint-text">{{ f.description }}</span>
            </label>
          </div>
        </div>
      </fieldset>
      <p v-if="agent?.url" class="fr-text--xs fr-mb-2w">
        <a :href="agent.url" target="_blank" rel="noopener noreferrer" class="fr-link fr-text--xs">
          La fiche de « {{ agent.name }} » dans Mes agents
        </a>
      </p>

      <div class="fr-input-group">
        <label class="fr-label" for="agent-question">
          Votre question
          <span class="fr-hint-text">Au plus {{ QUESTION_MAX }} caractères. Entrée lance ; Maj+Entrée va à la ligne.</span>
        </label>
        <textarea id="agent-question" class="fr-input" v-model="question" rows="3" :maxlength="QUESTION_MAX"
                  :disabled="enCours" @keydown.enter.exact.prevent="peutLancer && lancer()"></textarea>
      </div>
      <div class="fr-btns-group fr-btns-group--inline fr-btns-group--icon-left">
        <button type="button" class="fr-btn fr-btn--icon-left fr-icon-send-plane-line" :disabled="!peutLancer" @click="lancer">
          {{ enCours ? 'En cours…' : 'Lancer' }}
        </button>
      </div>

      <!-- L'attente, dite : la recherche d'abord, l'agent ensuite (jusqu'à deux minutes). -->
      <p v-if="enCours" class="fr-text--sm agents-attente" role="status" aria-live="polite">⏳ {{ etape }}</p>
      <div v-else-if="erreur" class="fr-alert fr-alert--sm fr-mt-2w" :class="erreurGenre === 'vide' ? 'fr-alert--info' : 'fr-alert--error'" role="alert">
        <p>{{ erreur }}</p>
      </div>

      <div v-if="resultat" class="agents-reponse fr-mt-3w">
        <div class="agents-reponse__entete">
          <p class="fr-text--sm fr-mb-0"><strong>{{ resultat.agent.name }}</strong> a répondu à « {{ resultat.question }} »</p>
          <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary fr-btn--icon-left fr-icon-clipboard-line"
                  title="Copier la réponse et la liste des passages transmis" @click="copier">
            {{ copie ? 'Copié' : 'Copier' }}
          </button>
        </div>
        <!-- Markdown assaini (DOMPurify) : la réponse d'un modèle n'est jamais rendue telle quelle. -->
        <div class="agents-reponse__corps myrag-md" v-html="rendu"></div>

        <div class="agents-sources">
          <p class="fr-text--xs fr-mb-1w agents-sources__titre">
            {{ resultat.citees.size ? 'Passages cités par la réponse' : 'Passages transmis à l\'agent' }}
            <span v-if="!resultat.citees.size"> — la réponse n'en cite aucun par son numéro</span>
          </p>
          <div class="agents-sources__puces">
            <PlaygroundSourceChip v-for="s in sourcesCitees" :key="s.n" :source="s" />
          </div>
          <template v-if="resultat.citees.size && sourcesAutres.length">
            <p class="fr-text--xs fr-mb-1w fr-mt-1w agents-sources__titre">Autres passages transmis</p>
            <div class="agents-sources__puces">
              <PlaygroundSourceChip v-for="s in sourcesAutres" :key="s.n" :source="s" />
            </div>
          </template>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { renderMarkdownSafe } from '~/utils/sanitize'
import { libelleOrigine, texteACopier, QUESTION_MAX } from '~/utils/agents'
import { useMesAgents, type ResultatAgent } from '~/composables/useMesAgents'

const props = defineProps<{
  /** Le nom de la collection — ce que `scope` de la recherche attend. */
  collection: string
}>()

const agents = useMesAgents()
const { fiches } = agents

const choisi = ref<string>('')
const question = ref('')
const enCours = ref(false)
const etape = ref('')
const erreur = ref('')
const erreurGenre = ref<'masquer' | 'message' | 'vide'>('message')
const resultat = ref<ResultatAgent | null>(null)
const copie = ref(false)
let minuterieCopie: ReturnType<typeof setTimeout> | null = null

const agent = computed(() => fiches.value.find(f => f.id === choisi.value) || null)
const peutLancer = computed(() => !enCours.value && !!agent.value && question.value.trim().length > 0)
const rendu = computed(() => renderMarkdownSafe(resultat.value?.reponse || ''))
const sourcesCitees = computed(() => {
  const r = resultat.value
  if (!r) return []
  return r.citees.size ? r.sources.filter(s => r.citees.has(s.n)) : r.sources
})
const sourcesAutres = computed(() => {
  const r = resultat.value
  return r ? r.sources.filter(s => !r.citees.has(s.n)) : []
})

// Le premier agent coché d'office : un seul geste pour lancer quand il n'y en a qu'un.
watch(fiches, (l) => { if (!l.find(f => f.id === choisi.value)) choisi.value = l[0]?.id || '' }, { immediate: true })

async function lancer() {
  if (!peutLancer.value || !agent.value) return
  enCours.value = true
  erreur.value = ''
  resultat.value = null
  copie.value = false
  etape.value = 'Recherche des passages dans la collection…'
  // L'étape change d'elle-même : la recherche prend quelques secondes, l'agent jusqu'à deux minutes.
  const bascule = setTimeout(() => { etape.value = `« ${agent.value?.name} » travaille sur les passages trouvés — jusqu'à deux minutes.` }, 2500)
  try {
    const l = await agents.lancer(agent.value, question.value, props.collection)
    if (l.ok) {
      resultat.value = l.resultat
    } else {
      erreurGenre.value = l.genre
      erreur.value = l.genre === 'masquer'
        ? `${l.message} La fonction sera retirée de cette page au prochain chargement.`
        : l.message
    }
  } finally {
    clearTimeout(bascule)
    enCours.value = false
    etape.value = ''
  }
}

async function copier() {
  if (!resultat.value) return
  try {
    await navigator.clipboard.writeText(texteACopier(resultat.value.reponse, resultat.value.passages))
    copie.value = true
    if (minuterieCopie) clearTimeout(minuterieCopie)
    minuterieCopie = setTimeout(() => { copie.value = false }, 2000)
  } catch {
    erreurGenre.value = 'message'
    erreur.value = "Le presse-papiers n'est pas accessible : sélectionnez la réponse et copiez-la."
  }
}
</script>

<style scoped>
.agents-explication { color: var(--text-mention-grey); }
.agents-vide { color: var(--text-mention-grey); }
.agents-nom { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; }
.agents-attente { color: #555; padding: 0.4rem 0; }
.agents-reponse {
  padding: 0.8rem 1rem;
  border-radius: 6px;
  background: #f6f6f6;
  border-left: 3px solid #18753c;
}
.agents-reponse__entete {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}
.agents-reponse__corps { font-size: 0.95rem; line-height: 1.5; word-break: break-word; }
.agents-sources { margin-top: 0.8rem; padding-top: 0.6rem; border-top: 1px solid #e5e5e5; }
.agents-sources__titre { color: #555; }
.agents-sources__puces { display: flex; flex-wrap: wrap; }
/* Même habillage que les réponses du bac à sable (PlaygroundChatMessage). */
.myrag-md :deep(p:first-child) { margin-top: 0; }
.myrag-md :deep(p:last-child) { margin-bottom: 0; }
.myrag-md :deep(ul),
.myrag-md :deep(ol) { padding-left: 1.2rem; margin: 0.4rem 0; }
.myrag-md :deep(code) { background: #e8e8e8; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.85em; }
.myrag-md :deep(pre) { background: #282c34; color: #f0f0f0; padding: 0.6rem 0.8rem; border-radius: 4px; overflow-x: auto; font-size: 0.82em; }
.myrag-md :deep(pre code) { background: transparent; padding: 0; }
</style>
