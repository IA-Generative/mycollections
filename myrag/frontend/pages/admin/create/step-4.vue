<script setup lang="ts">
import type { VerdictTechnique } from '~/utils/wizard'
import { messageErreur } from '~/utils/collectif'
import { renderMarkdownSafe } from '~/utils/sanitize'
import { chargeAuJeu, NB_QUESTIONS_TEST, questionsSuggerees, verdictTechnique } from '~/utils/wizard'

/**
 * Étape 4 de l'assistant : un test technique, pas encore la qualité. Trois questions (suggérées
 * depuis le jeu ou les titres des documents, modifiables), la réponse et ses passages, un verdict
 * simple « répond / ne répond pas ». Chaque question posée entre au jeu de questions « à relire » :
 * on la retrouve dans la page Qualité, où se mesure vraiment la qualité (docs/qualite.md).
 */
const route = useRoute()
const collection = route.query.collection as string
const { get, post } = useApi()

interface Essai {
  question: string
  enCours: boolean
  reponse: string
  passages: string[]
  verdict: VerdictTechnique | null
  erreur: string
}
const essai = (question = ''): Essai => ({ question, enCours: false, reponse: '', passages: [], verdict: null, erreur: '' })
/** Un essai par question, chacun SON objet (un `fill` partagerait le même entre les trois lignes). */
function essaisVides (): Essai[] {
  const liste: Essai[] = []
  for (let i = 0; i < NB_QUESTIONS_TEST; i++) {
    liste.push(essai())
  }
  return liste
}
const essais = ref<Essai[]>(essaisVides())
const suggestionsChargees = ref(false)

const poses = computed(() => essais.value.filter(e => e.verdict))
const repondues = computed(() => poses.value.filter(e => e.verdict?.cle === 'repond').length)

async function poser (e: Essai) {
  if (!e.question.trim() || e.enCours) {
    return
  }
  e.enCours = true
  e.erreur = ''
  e.verdict = null
  try {
    const d = await post(`/api/playground/${encodeURIComponent(collection)}/chat`, { question: e.question.trim() })
    e.reponse = d.response || ''
    e.passages = d.source_names || []
    e.verdict = verdictTechnique(d)
  }
  catch (err) {
    e.erreur = messageErreur(err)
  }
  finally {
    e.enCours = false
  }
  // La question posée entre au jeu « à relire » ; une question déjà au jeu (409) n'est pas un échec.
  const corps = chargeAuJeu(e.question)
  if (corps) {
    try {
      await post(`/api/collections/${encodeURIComponent(collection)}/qualite/questions`, corps)
    }
    catch { /* déjà au jeu, ou droit manquant : le test reste valable */ }
  }
}

async function poserTout () {
  for (const e of essais.value) {
    if (e.question.trim() && !e.verdict) {
      await poser(e)
    }
  }
}

onMounted(async () => {
  try {
    const qs = questionsSuggerees(await get(`/api/playground/${encodeURIComponent(collection)}/suggestions`))
    qs.forEach((q, i) => {
      essais.value[i]!.question = q
    })
  }
  catch { /* pas de suggestion : la personne tape ses questions */ }
  suggestionsChargees.value = true
})
</script>

<template>
  <WizardEtape
    :numero="4"
    titre="Vérifiez que la collection répond"
    chapeau="Un test rapide : posez trois questions et regardez si la collection y répond, en citant ses passages."
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
        <ol class="etape4-essais">
          <li
            v-for="(e, i) in essais"
            :key="i"
            class="etape4-essai"
          >
            <div class="etape4-essai__ligne">
              <div class="fr-input-group fr-mb-0 etape4-essai__champ">
                <label
                  class="fr-label fr-sr-only"
                  :for="`etape4-q${i}`"
                >Question {{ i + 1 }}</label>
                <input
                  :id="`etape4-q${i}`"
                  v-model="e.question"
                  class="fr-input"
                  type="text"
                  :placeholder="suggestionsChargees ? 'Tapez une question que poseraient vos collègues' : 'Chargement des suggestions…'"
                  @keydown.enter.prevent="poser(e)"
                >
              </div>
              <button
                type="button"
                class="fr-btn fr-btn--secondary"
                :disabled="e.enCours || !e.question.trim()"
                @click="poser(e)"
              >
                {{ e.enCours ? 'Question posée…' : 'Poser' }}
              </button>
            </div>
            <div
              v-if="e.verdict || e.erreur"
              class="etape4-essai__resultat"
              aria-live="polite"
            >
              <p
                v-if="e.erreur"
                class="fr-error-text fr-mt-0"
              >
                {{ e.erreur }}
              </p>
              <template v-else-if="e.verdict">
                <p
                  class="fr-badge fr-badge--sm fr-mb-0"
                  :class="e.verdict.cle === 'repond' ? 'fr-badge--success' : 'fr-badge--warning'"
                >
                  {{ e.verdict.libelle }}
                </p>
                <p
                  v-if="e.verdict.aide"
                  class="fr-text--xs fr-mb-0 etape4-discret"
                >
                  {{ e.verdict.aide }}
                </p>
                <details class="fr-mt-1v">
                  <summary class="fr-text--sm">
                    Voir la réponse et ses passages
                  </summary>
                  <!-- Réponse de la collection : passée par renderMarkdownSafe (DOMPurify) avant v-html. -->
                  <div
                    class="etape4-reponse fr-mt-1w"
                    v-html="renderMarkdownSafe(e.reponse || 'Pas de réponse.')"
                  />
                  <p class="fr-text--xs fr-mt-1v fr-mb-0 etape4-discret">
                    {{ e.passages.length ? `Passages : ${e.passages.join(', ')}` : 'Aucun passage trouvé.' }}
                  </p>
                </details>
              </template>
            </div>
          </li>
        </ol>

        <div class="etape4-bilan">
          <button
            type="button"
            class="fr-btn fr-btn--sm"
            :disabled="essais.every(e => !e.question.trim() || e.verdict || e.enCours)"
            @click="poserTout"
          >
            Poser les trois questions
          </button>
          <p
            v-if="poses.length"
            class="fr-text--sm fr-mb-0"
            aria-live="polite"
          >
            <strong>{{ repondues }} sur {{ poses.length }}</strong> question{{ poses.length > 1 ? 's' : '' }} avec une réponse.
            Elles sont dans le jeu de questions, à relire depuis la page Qualité.
          </p>
        </div>
      </template>
    </template>

    <template #encadre>
      <h2 class="fr-callout__title fr-h6">
        Et la qualité ?
      </h2>
      <p class="fr-callout__text fr-text--sm">
        Ce test dit seulement si vos documents sont lus et retrouvés. Pour mesurer la justesse des réponses, préciser les
        consignes ou marquer des réponses fiables, la page Qualité vous attend sur la fiche de la collection, après la publication.
      </p>
      <NuxtLink
        :to="`/c/${encodeURIComponent(collection)}/qualite`"
        class="fr-link fr-text--sm"
        target="_blank"
      >
        Ouvrir la page Qualité (nouvel onglet)
      </NuxtLink>
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
            :to="`/admin/create/step-3?collection=${collection}`"
            class="fr-btn fr-btn--secondary"
          >
            Étape précédente
          </NuxtLink>
        </li>
        <li>
          <NuxtLink
            :to="`/admin/create/step-5?collection=${collection}`"
            class="fr-btn"
          >
            Continuer vers la publication
          </NuxtLink>
        </li>
      </ul>
    </template>
  </WizardEtape>
</template>

<style scoped>
.etape4-essais { margin: 0; padding-left: 1.25rem; display: flex; flex-direction: column; gap: .75rem; }
.etape4-essai { padding: 0; }
.etape4-essai__ligne { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .75rem; }
.etape4-essai__champ { flex: 1 1 18rem; min-width: 0; }
.etape4-essai__resultat { margin-top: .5rem; display: flex; flex-direction: column; gap: .25rem; }
.etape4-reponse { background: var(--background-alt-grey); padding: .75rem; font-size: .875rem; max-height: 16rem; overflow-y: auto; }
.etape4-reponse :deep(p), .etape4-reponse :deep(ul), .etape4-reponse :deep(ol) { margin: 0 0 .5rem; }
/* Les intertitres d'une réponse restent du texte de réponse, pas des titres de page. */
.etape4-reponse :deep(h1), .etape4-reponse :deep(h2), .etape4-reponse :deep(h3), .etape4-reponse :deep(h4), .etape4-reponse :deep(h5), .etape4-reponse :deep(h6) { font-size: 1rem; line-height: 1.5rem; margin: .5rem 0 .25rem; }
.etape4-bilan { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem 1.5rem; margin-top: 1rem; }
.etape4-discret { color: var(--text-mention-grey); }
</style>
