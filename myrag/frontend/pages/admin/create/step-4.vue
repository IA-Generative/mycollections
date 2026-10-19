<script setup lang="ts">
import { messageErreur } from '~/utils/collectif'
import { renderMarkdownSafe } from '~/utils/sanitize'

/**
 * Étape 4 de l'assistant : le début du jeu de questions de la collection, et une première mesure.
 * Mêmes composants que la page Qualité (docs/qualite.md) : rien ne se perd en quittant l'étape.
 */
const route = useRoute()
const collection = route.query.collection as string
const api = useQualite(collection)
const { post } = useApi()
const synthese = ref<any>(null)
const ouvert = ref<string | null>(null)
const filtre = ref<Record<string, string> | undefined>(undefined)
const jeu = ref<any>(null)
const question = ref('')
const reponse = ref('')
const sources = ref<string[]>([])
const enTest = ref(false)

const echecs = computed(() => {
  const v = synthese.value?.derniere_terminee?.verdicts
  return v ? v.non_conformes + v.partielles + v.refus_ko + v.sans_source : 0
})

async function recharger () {
  try { synthese.value = await api.synthese() }
  catch { /* la mesure reste masquée */ }
}
onMounted(recharger)

function mesureFinie () {
  recharger()
  jeu.value?.charger()
}
function questionChange () {
  recharger()
  jeu.value?.charger()
}
function voirEchecs () {
  // Le jeu filtre sur un verdict : le plus grave présent d'abord.
  const v = synthese.value?.derniere_terminee?.verdicts || {}
  const verdict = v.non_conformes ? 'non_conforme' : v.refus_ko ? 'refus_ko' : v.partielles ? 'partiel' : 'sans_source'
  filtre.value = { verdict }
  nextTick(() => document.getElementById('etape4-jeu')?.scrollIntoView({ behavior: 'smooth' }))
}
function levier (nom: 'decoupage' | 'consignes') {
  window.open(`/c/${encodeURIComponent(collection)}/qualite?onglet=leviers#levier-${nom}`, '_blank', 'noopener')
}

async function tester () {
  enTest.value = true
  reponse.value = ''
  sources.value = []
  try {
    const d = await post(`/api/playground/${encodeURIComponent(collection)}/chat`, { question: question.value })
    reponse.value = d.response || 'Pas de réponse.'
    sources.value = d.source_names || []
  }
  catch (e) {
    reponse.value = messageErreur(e)
  }
  finally {
    enTest.value = false
  }
}
</script>

<template>
  <div>
    <nav
      role="navigation"
      class="fr-breadcrumb"
      aria-label="vous êtes ici :"
    >
      <ol class="fr-breadcrumb__list">
        <li>
          <NuxtLink
            class="fr-breadcrumb__link"
            to="/admin"
          >
            Administration
          </NuxtLink>
        </li>
        <li>
          <NuxtLink
            class="fr-breadcrumb__link"
            to="/admin/create"
          >
            Créer
          </NuxtLink>
        </li>
        <li>
          <a
            class="fr-breadcrumb__link"
            aria-current="page"
          >Questions et qualité</a>
        </li>
      </ol>
    </nav>

    <h1 class="fr-h3">
      Vos questions, votre qualité — {{ collection }}
    </h1>
    <p class="fr-text--lg fr-mb-4w">
      Étape 4 sur 5 — Vérifiez que la collection répond juste, avant de la partager
    </p>

    <WizardStepper :current-step="4" />

    <div class="etape4">
      <div class="fr-callout fr-mb-4w">
        <h2 class="fr-callout__title fr-h6">
          Ce que vous faites ici
        </h2>
        <p class="fr-callout__text fr-text--sm">
          Vous constituez le <strong>jeu de questions</strong> de votre collection : celles que poseront vraiment les gens,
          avec la bonne réponse. Il sert à <strong>mesurer la qualité</strong> aujourd'hui, puis à la suivre dans le temps et
          à l'améliorer (redécouper les documents, préciser les consignes, marquer des réponses fiables). Vous le
          retrouverez dans la page « Qualité » de la collection. Cette étape est facultative.
        </p>
      </div>

      <section
        class="fr-mb-6w"
        aria-labelledby="etape4-jeu"
      >
        <h2
          id="etape4-jeu"
          class="fr-h5"
        >
          1. Constituer le jeu de questions
        </h2>
        <p class="fr-text--sm">
          Faites rédiger des questions d'après les documents, ajoutez les vôtres ou importez un fichier. Relisez-les :
          question et réponse se modifient en place, d'un clic. Seules les questions <strong>validées</strong> sont mesurées.
        </p>
        <QualiteJeuDeQuestions
          ref="jeu"
          :collection="collection"
          :filtre="filtre"
          @change="recharger"
          @ouvrir="i => ouvert = i"
        />
      </section>

      <section
        class="fr-mb-6w"
        aria-labelledby="etape4-mesure"
      >
        <h2
          id="etape4-mesure"
          class="fr-h5"
        >
          2. Mesurer la qualité maintenant
        </h2>
        <p class="fr-text--sm">
          Chaque question validée est posée à la collection ; un juge IA compare sa réponse à la vôtre et dit si elle est
          conforme, partielle ou fausse — et pour une question hors sujet, si la collection a bien refusé.
        </p>
        <QualiteMesurer
          v-if="synthese"
          :collection="collection"
          :synthese="synthese"
          @fini="mesureFinie"
        />
        <div
          v-if="synthese?.derniere_terminee"
          class="etape4__synthese fr-mt-3w"
        >
          <QualiteSynthese
            :synthese="synthese"
            titre="Synthèse de la dernière mesure"
          />
          <div
            v-if="echecs"
            class="fr-mt-2w"
          >
            <p class="fr-text--sm fr-mb-1w">
              <strong>À regarder :</strong> {{ echecs }} question{{ echecs > 1 ? 's' : '' }} mal répondue{{ echecs > 1 ? 's' : '' }}.
              Ouvrez-en une : le volet montre la réponse obtenue, la raison du verdict et quoi faire.
            </p>
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--secondary"
              @click="voirEchecs"
            >
              Afficher les plus graves dans le jeu
            </button>
          </div>
        </div>
      </section>

      <details class="fr-mb-6w etape4__libre">
        <summary class="fr-h6 fr-mb-0">
          Poser une question libre à la collection
        </summary>
        <div class="fr-mt-2w">
          <div class="fr-input-group">
            <label
              class="fr-label"
              for="etape4-question"
            >Votre question</label>
            <textarea
              id="etape4-question"
              v-model="question"
              class="fr-input"
              rows="2"
              @keydown.enter.exact.prevent="!enTest && question.trim() && tester()"
            />
          </div>
          <button
            type="button"
            class="fr-btn fr-btn--sm"
            :disabled="enTest || !question.trim()"
            @click="tester"
          >
            {{ enTest ? 'Question posée…' : 'Poser la question' }}
          </button>
          <div
            v-if="reponse"
            class="fr-mt-2w etape4__reponse"
            v-html="renderMarkdownSafe(reponse)"
          />
          <p
            v-if="reponse"
            class="fr-text--xs fr-mt-1w etape4__discret"
          >
            {{ sources.length ? `Sources : ${sources.join(', ')}` : 'Aucun passage trouvé par la recherche.' }}
          </p>
        </div>
      </details>

      <section
        class="fr-callout fr-callout--green-emeraude fr-mb-4w"
        aria-labelledby="etape4-ensuite"
      >
        <h2
          id="etape4-ensuite"
          class="fr-callout__title fr-h6"
        >
          3. Et ensuite
        </h2>
        <p class="fr-callout__text fr-text--sm">
          Tout cela vous attend dans la page Qualité de la collection : mesurer à nouveau après chaque changement,
          suivre la courbe, enrichir le jeu avec les avis des usagers, marquer des réponses fiables.
        </p>
        <NuxtLink
          :to="`/c/${collection}/qualite`"
          class="fr-link fr-mt-1w"
          target="_blank"
        >
          Ouvrir la page Qualité (nouvel onglet)
        </NuxtLink>
      </section>

      <div class="fr-btns-group fr-btns-group--inline">
        <NuxtLink
          :to="`/admin/create/step-3?collection=${collection}`"
          class="fr-btn fr-btn--secondary"
        >
          ← Précédent
        </NuxtLink>
        <NuxtLink
          :to="`/admin/create/step-5?collection=${collection}`"
          class="fr-btn"
        >
          Suivant →
        </NuxtLink>
      </div>
    </div>

    <QualiteVolet
      :collection="collection"
      :ident="ouvert"
      @fermer="ouvert = null"
      @change="questionChange"
      @levier="levier"
    />
  </div>
</template>

<style scoped>
.etape4 { max-width: 64rem; }
.etape4__synthese { border: 1px solid var(--border-default-grey); padding: 1rem 1.25rem; }
.etape4__libre summary { cursor: pointer; }
.etape4__reponse { background: var(--background-alt-grey); padding: .75rem; font-size: .875rem; max-height: 24rem; overflow-y: auto; }
.etape4__reponse :deep(p), .etape4__reponse :deep(ul), .etape4__reponse :deep(ol) { margin: 0 0 .5rem; }
.etape4__discret { color: var(--text-mention-grey); }
</style>
