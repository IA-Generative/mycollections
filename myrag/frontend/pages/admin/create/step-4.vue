<script setup lang="ts">
import type { Validation, VerdictTechnique } from '~/utils/wizard'
import { messageErreur } from '~/utils/collectif'
import { bilanVerification, chargeAuJeu, lienEtape, plierQuestion, questionsSuggerees, trouverQuestion, verdictTechnique } from '~/utils/wizard'

/**
 * Étape 4 de l'assistant : vérifier, en conversation, que la collection répond — dans l'esprit du
 * bac à sable. À gauche, la conversation ; à droite, des questions à essayer, qui s'écrivent dans
 * le champ avant de partir. Sous chaque réponse : le verdict technique (trouvée, répondue ?) et
 * l'avis de la personne (« Oui, ça répond » / « Non »), qui entre au jeu de questions. Rien ne
 * bloque « Étape suivante » ; rien ne fait sortir de l'assistant.
 */
const route = useRoute()
const collection = route.query.collection as string
const source = (route.query.source as string) || ''
const { get, post, patch } = useApi()

const racineQualite = `/api/collections/${encodeURIComponent(collection)}/qualite/questions`

// La mention « en cours de vérification » est expliquée une fois, pas répétée en tête de chaque réponse.
const { messages, isLoading, sendMessage } = useChat(collection, { sansMention: true })
const draft = ref('')
const { enFrappe, taper, mouvementReduit } = useFrappe(draft)
const messagesEl = ref<HTMLElement | null>(null)
const chatEl = ref<HTMLElement | null>(null)

interface Essai {
  question: string
  tourId?: string
  verdict: VerdictTechnique | null
  reponse: string
  questionId?: string
  validation: Validation
  enValidation: boolean
  erreur: string
}
/** Un essai par question posée (clé : la question pliée) ; reposer remplace le verdict, garde l'avis. */
const essais = ref<Map<string, Essai>>(new Map())
const suggestions = ref<string[]>([])
const suggestionsChargees = ref(false)

const liste = computed(() => [...essais.value.values()])
const bilan = computed(() => bilanVerification(liste.value))
const essaiDe = (texte: string) => essais.value.get(plierQuestion(texte))
const essaiDuTour = (tourId?: string) => (tourId ? liste.value.find(e => e.tourId === tourId) : undefined)
const occupe = computed(() => isLoading.value || enFrappe.value)
const canSend = computed(() => !occupe.value && draft.value.trim().length > 0)

function scrollToBottom () {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
    const el = chatEl.value
    if (el && el.getBoundingClientRect().bottom > window.innerHeight) {
      el.scrollIntoView({ behavior: mouvementReduit() ? 'auto' : 'smooth', block: 'end' })
    }
  })
}

/** La question entre au jeu « à relire » ; déjà au jeu (409) : on retrouve sa fiche pour y noter l'avis. */
async function inscrireAuJeu (question: string): Promise<string | undefined> {
  const corps = chargeAuJeu(question)
  if (!corps) {
    return undefined
  }
  try {
    return (await post(racineQualite, corps))?.question?.id
  }
  catch {
    try {
      const r = await get(racineQualite, { q: question.slice(0, 100), par_page: '50' })
      return trouverQuestion((r?.questions || []) as { id: string, question: string }[], question)?.id
    }
    catch {
      return undefined
    }
  }
}

async function poser (texte: string) {
  const q = texte.trim()
  if (!q || occupe.value) {
    return
  }
  const cle = plierQuestion(q)
  const existant = essais.value.get(cle)
  if (!existant) {
    essais.value.set(cle, { question: q, verdict: null, reponse: '', validation: null, enValidation: false, erreur: '' })
  }
  // On mute l'objet tel que la Map le rend (réactif), pas celui qu'on vient de construire.
  const essai = essais.value.get(cle)!
  const envoi = sendMessage(q)
  draft.value = ''
  scrollToBottom()
  const m = await envoi
  scrollToBottom()
  if (!m || m.error) {
    essai.erreur = m?.content || ''
    return
  }
  essai.tourId = m.turnId
  essai.reponse = m.content
  essai.verdict = verdictTechnique({ response: m.content, source_names: m.sourceNames, sources: m.sources })
  essai.validation = existant?.validation ?? null
  essai.questionId ||= await inscrireAuJeu(q)
}

async function poserDepuisSuggestion (texte: string) {
  if (occupe.value) {
    return
  }
  await taper(texte, scrollToBottom)
  await poser(texte)
}

async function valider (essai: Essai, v: 'oui' | 'non') {
  if (essai.enValidation) {
    return
  }
  essai.enValidation = true
  essai.erreur = ''
  try {
    essai.questionId ||= await inscrireAuJeu(essai.question)
    if (!essai.questionId) {
      throw new Error('question absente du jeu')
    }
    const corps = v === 'oui'
      ? { relecture: 'valide', reponse: essai.reponse }
      : { commentaire: `Jugée insuffisante à la création (étape 4) : ${essai.verdict?.libelle || 'réponse insatisfaisante'}` }
    await patch(`${racineQualite}/${encodeURIComponent(essai.questionId)}`, corps)
    essai.validation = v
  }
  catch (e) {
    essai.validation = v
    essai.erreur = `Votre avis est noté ici, mais n'a pas pu être enregistré dans le jeu de questions (${messageErreur(e)}). Vous le redonnerez depuis la page Qualité.`
  }
  finally {
    essai.enValidation = false
  }
}

async function chargerSuggestions () {
  try {
    const qs = questionsSuggerees(await get(`/api/playground/${encodeURIComponent(collection)}/suggestions`))
    // Les questions déjà posées restent affichées ; les nouvelles complètent.
    suggestions.value = [...new Set([...suggestions.value.filter(s => essaiDe(s)), ...qs])]
  }
  catch { /* pas de suggestion : la personne tape ses questions */ }
  suggestionsChargees.value = true
}

onMounted(chargerSuggestions)
</script>

<template>
  <WizardEtape
    :numero="4"
    titre="Vérifiez que la collection répond"
    chapeau="Posez-lui quelques questions, comme le feraient vos collègues, et dites si les réponses vous conviennent. Tout reste ici : rien ne vous fait quitter l'assistant."
  >
    <template #formulaire>
      <div
        v-if="!collection"
        class="fr-alert fr-alert--warning"
      >
        <p>
          Aucune collection indiquée. <NuxtLink to="/admin/create">
            Retour à l'étape 1
          </NuxtLink>
        </p>
      </div>
      <template v-else>
        <div class="etape4">
          <!-- Gauche : la conversation -->
          <section
            ref="chatEl"
            class="etape4__chat"
            aria-label="Conversation avec la collection"
          >
            <div
              v-if="!messages.length"
              class="etape4__vide fr-text--sm"
            >
              <template v-if="suggestions.length">
                Choisissez une question à droite, ou tapez la vôtre ci-dessous.
              </template>
              <template v-else-if="!suggestionsChargees">
                Préparation de quelques questions à essayer…
              </template>
              <template v-else>
                Tapez une question que poseraient vos collègues.
              </template>
            </div>
            <div
              v-if="messages.length"
              ref="messagesEl"
              class="etape4__messages"
            >
              <template
                v-for="m in messages"
                :key="m.turnId || m.content"
              >
                <PlaygroundChatMessage
                  :message="m"
                  sans-avis
                  titre-trace="Comment la collection a cherché"
                />
                <WizardValidationReponse
                  v-if="m.role === 'assistant' && !m.error && essaiDuTour(m.turnId)"
                  :verdict="essaiDuTour(m.turnId)!.verdict"
                  :validation="essaiDuTour(m.turnId)!.validation"
                  :en-cours="essaiDuTour(m.turnId)!.enValidation"
                  :erreur="essaiDuTour(m.turnId)!.erreur"
                  @valider="valider(essaiDuTour(m.turnId)!, $event)"
                />
              </template>
              <div
                v-if="isLoading"
                class="fr-text--sm etape4__attente"
                role="status"
              >
                ⏳ La collection cherche<span
                  class="etape4__points"
                  aria-hidden="true"
                ><span>.</span><span>.</span><span>.</span></span>
              </div>
            </div>

            <div
              class="etape4__saisie"
              :class="{ 'etape4__saisie--frappe': enFrappe }"
            >
              <div class="fr-input-group fr-mb-1w">
                <label
                  class="fr-label fr-sr-only"
                  for="etape4-question"
                >Votre question</label>
                <textarea
                  id="etape4-question"
                  v-model="draft"
                  class="fr-input"
                  rows="2"
                  placeholder="Votre question…"
                  :readonly="enFrappe"
                  @keydown.enter.exact.prevent="canSend && poser(draft)"
                />
              </div>
              <button
                type="button"
                class="fr-btn fr-btn--sm"
                :disabled="!canSend"
                @click="poser(draft)"
              >
                {{ isLoading ? 'Envoi…' : 'Poser' }}
              </button>
            </div>
          </section>

          <!-- Droite : des questions à essayer -->
          <aside
            class="etape4__banque"
            aria-label="Questions à essayer"
          >
            <h2 class="fr-h6 fr-mb-1v">
              Questions à essayer
            </h2>
            <p class="fr-text--xs fr-mb-2w etape4-discret">
              Proposées d'après vos documents. Chaque question posée rejoint le jeu de questions de la collection.
            </p>
            <p
              v-if="!suggestions.length"
              class="fr-text--sm etape4-discret"
            >
              {{ suggestionsChargees ? 'Aucune suggestion pour le moment : tapez vos questions à gauche.' : 'Chargement…' }}
            </p>
            <WizardQuestionSuggeree
              v-for="s in suggestions"
              :key="s"
              :texte="s"
              :verdict="essaiDe(s)?.verdict"
              :validation="essaiDe(s)?.validation ?? null"
              :posee="!!essaiDe(s)?.verdict"
              :loading="occupe"
              @poser="poserDepuisSuggestion(s)"
            />
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-mt-1w"
              :disabled="occupe"
              @click="chargerSuggestions"
            >
              Proposer d'autres questions
            </button>
          </aside>
        </div>

        <div
          class="etape4-bilan fr-mt-3w"
          aria-live="polite"
        >
          <p class="fr-text--sm fr-mb-1v">
            <strong>{{ bilan.phrase }}</strong>
          </p>
          <p class="fr-text--xs fr-mb-0 etape4-discret">
            Vous retrouverez ces questions, et la mesure de la qualité des réponses, sur la page Qualité de la collection
            une fois l'assistant terminé. Tant que la collection n'est pas publiée à tous, ses réponses dans le chat MirAI
            porteront la mention « en cours de vérification » ; elle est masquée ici.
          </p>
        </div>
      </template>
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
            :to="lienEtape(3, collection, source)"
            class="fr-btn fr-btn--secondary"
          >
            Étape précédente
          </NuxtLink>
        </li>
        <li>
          <NuxtLink
            :to="lienEtape(5, collection, source)"
            class="fr-btn"
          >
            {{ source === 'resana' ? 'Étape suivante' : 'Continuer vers la publication' }}
          </NuxtLink>
        </li>
      </ul>
    </template>
  </WizardEtape>
</template>

<style scoped>
.etape4 { display: grid; grid-template-columns: 1fr 380px; gap: 1.5rem; align-items: start; }
@media (max-width: 1200px) { .etape4 { grid-template-columns: 1fr; } }
.etape4__chat { display: flex; flex-direction: column; min-width: 0; }
.etape4__vide { padding: .6rem .8rem; background: var(--background-alt-grey); border-left: 3px solid var(--border-default-grey); margin-bottom: 1rem; color: var(--text-mention-grey); }
.etape4__messages { max-height: 560px; overflow-y: auto; padding-right: .3rem; margin-bottom: 1rem; }
.etape4__saisie { position: sticky; bottom: 0; background: #fff; padding-top: .4rem; }
.etape4__saisie--frappe .fr-input { box-shadow: inset 0 -2px 0 0 var(--border-active-blue-france), 0 0 0 3px var(--background-action-low-blue-france); transition: box-shadow .2s; }
.etape4__attente { color: var(--text-mention-grey); padding: .4rem 0; }
.etape4__points span { animation: etape4-point 1.2s infinite; opacity: .2; }
.etape4__points span:nth-child(2) { animation-delay: .2s; }
.etape4__points span:nth-child(3) { animation-delay: .4s; }
@keyframes etape4-point { 0%, 80%, 100% { opacity: .2; } 40% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .etape4__points span { animation: none; opacity: 1; } }
.etape4__banque { background: var(--background-alt-grey); border: 1px solid var(--border-default-grey); border-radius: 6px; padding: .8rem .9rem; position: sticky; top: 1rem; max-height: calc(100vh - 2rem); overflow-y: auto; }
@media (max-width: 1200px) { .etape4__banque { position: static; max-height: none; } }
.etape4-discret { color: var(--text-mention-grey); }
</style>
