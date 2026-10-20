<script setup lang="ts">
import type { QuestionSource } from '~/utils/assistants'
import { libelleSeuil, lienQualite, resumeQualiteSource } from '~/utils/assistants'
import { messageErreur } from '~/utils/collectif'
import { classeRelecture, libelleRelecture } from '~/utils/generation'
import { classeVerdict, libelleVerdict } from '~/utils/qualite'

/**
 * La qualité d'un assistant : une carte par source (la synthèse de sa collection, les composants de
 * la page Qualité) et le jeu de questions réuni, en lecture et filtrable. Rien ne s'écrit ici :
 * corriger une question se fait sur la page Qualité de la collection, par qui la gère.
 */
const props = defineProps<{ id: string }>()
const { qualite, questionsQualite } = useAssistants()
const uid = `qa-${useId()}`

const bilan = ref<any>(null)
const questions = ref<QuestionSource[]>([])
const total = ref(0)
const page = ref(1)
const pages = ref(1)
const chargement = ref(true)
const erreur = ref('')
const filtres = reactive({ relecture: '', fiable: '', q: '' })
const texte = ref('')

async function chargerBilan () {
  try {
    bilan.value = await qualite(props.id)
  }
  catch (e) {
    erreur.value = `La qualité n'a pas pu être lue : ${messageErreur(e)}`
  }
}

async function chargerQuestions () {
  const params: Record<string, string> = { page: String(page.value), par_page: '25' }
  if (filtres.relecture) {
    params.relecture = filtres.relecture
  }
  if (filtres.fiable) {
    params.fiable = filtres.fiable
  }
  if (filtres.q) {
    params.q = filtres.q
  }
  try {
    const r = await questionsQualite(props.id, params)
    questions.value = r.questions
    total.value = r.total
    pages.value = Math.max(1, r.pages || 1)
    if (page.value > pages.value) {
      page.value = pages.value
    }
  }
  catch (e) {
    erreur.value = `Le jeu de questions n'a pas pu être lu : ${messageErreur(e)}`
  }
  finally {
    chargement.value = false
  }
}

let delai: ReturnType<typeof setTimeout> | null = null
watch(texte, (t) => {
  if (delai) {
    clearTimeout(delai)
  }
  delai = setTimeout(() => {
    filtres.q = t.trim()
  }, 300)
})
watch(() => [filtres.relecture, filtres.fiable, filtres.q], () => {
  if (page.value !== 1) {
    page.value = 1
  }
  else {
    chargerQuestions()
  }
})
watch(page, chargerQuestions)
onMounted(() => {
  chargerBilan()
  chargerQuestions()
})
onBeforeUnmount(() => {
  if (delai) {
    clearTimeout(delai)
  }
})
</script>

<template>
  <div>
    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
      role="alert"
    >
      <p>{{ erreur }}</p>
    </div>

    <section :aria-labelledby="`${uid}-sources`">
      <h2
        :id="`${uid}-sources`"
        class="fr-h5"
      >
        Qualité de chaque source
      </h2>
      <p
        v-if="bilan"
        class="fr-text--sm"
      >
        {{ libelleSeuil(bilan.seuil_fiable) }}
      </p>
      <p
        v-if="bilan && !bilan.sources.length"
        class="fr-text--sm"
      >
        Aucune source de cet assistant n'est lisible par vous.
      </p>
      <div
        v-if="bilan?.sources.length"
        class="qa__cartes"
      >
        <article
          v-for="s in bilan.sources"
          :key="s.collection"
          class="qa__carte"
        >
          <h3 class="fr-h6 fr-mb-1w">
            {{ s.collection_titre }}
          </h3>
          <QualiteSynthese
            :synthese="s.synthese"
            titre="Aujourd'hui"
          />
          <p class="fr-text--sm fr-mt-2w fr-mb-1w">
            {{ resumeQualiteSource(s) }}
          </p>
          <NuxtLink
            v-if="s.peut_gerer"
            :to="lienQualite(s.collection)"
            class="fr-link fr-text--sm"
          >
            Ouvrir la page Qualité de « {{ s.collection_titre }} »
          </NuxtLink>
          <p
            v-else
            class="fr-text--xs fr-mb-0 qa__discret"
          >
            La page Qualité de cette collection est réservée à celles et ceux qui la gèrent.
          </p>
        </article>
      </div>
    </section>

    <section
      class="fr-mt-4w"
      :aria-labelledby="`${uid}-jeu`"
    >
      <h2
        :id="`${uid}-jeu`"
        class="fr-h5"
      >
        Questions de référence des sources ({{ total }})
      </h2>
      <div class="qa__filtres">
        <div class="fr-select-group">
          <label
            class="fr-label"
            :for="`${uid}-etat`"
          >État</label>
          <select
            :id="`${uid}-etat`"
            v-model="filtres.relecture"
            class="fr-select"
          >
            <option value="">
              Tous
            </option>
            <option value="brut">
              À relire
            </option>
            <option value="valide">
              Validées
            </option>
            <option value="rejete">
              Rejetées
            </option>
          </select>
        </div>
        <div class="fr-select-group">
          <label
            class="fr-label"
            :for="`${uid}-fiable`"
          >Réponses fiables</label>
          <select
            :id="`${uid}-fiable`"
            v-model="filtres.fiable"
            class="fr-select"
          >
            <option value="">
              Toutes les questions
            </option>
            <option value="true">
              Fiables seulement
            </option>
            <option value="false">
              Non fiables
            </option>
          </select>
        </div>
        <div class="fr-input-group qa__recherche">
          <label
            class="fr-label"
            :for="`${uid}-texte`"
          >Chercher dans les questions</label>
          <input
            :id="`${uid}-texte`"
            v-model="texte"
            class="fr-input"
            type="search"
            maxlength="100"
          >
        </div>
      </div>

      <p
        v-if="chargement"
        class="fr-text--sm"
        aria-live="polite"
      >
        Chargement…
      </p>
      <div
        v-else-if="!questions.length"
        class="fr-callout"
      >
        <p class="fr-callout__text fr-text--sm">
          {{ total === 0 && !filtres.relecture && !filtres.fiable && !filtres.q ? 'Les sources n\'ont pas encore de questions de référence.' : 'Aucune question ne correspond à ces filtres.' }}
        </p>
      </div>
      <ul
        v-else
        class="qa__liste"
      >
        <li
          v-for="q in questions"
          :key="q.id"
          class="qa__item"
        >
          <div class="qa__badges">
            <span class="fr-tag fr-tag--sm">{{ q.collection_titre }}</span>
            <span
              class="fr-badge fr-badge--sm fr-badge--no-icon"
              :class="classeRelecture(q.relecture)"
            >{{ libelleRelecture(q.relecture) }}</span>
            <span
              v-if="q.dernier_verdict"
              class="fr-badge fr-badge--sm"
              :class="classeVerdict(q.dernier_verdict)"
            >{{ libelleVerdict(q.dernier_verdict) }}</span>
            <span
              v-if="q.hors_sujet"
              class="fr-badge fr-badge--sm fr-badge--no-icon fr-badge--purple-glycine"
            >Hors sujet : doit refuser</span>
            <span
              v-if="q.fiable"
              class="fr-badge fr-badge--sm fr-badge--no-icon fr-badge--green-emeraude"
            >Réponse fiable</span>
          </div>
          <p class="fr-text--bold fr-mb-1v">
            {{ q.question }}
          </p>
          <p
            v-if="q.reponse"
            class="fr-text--sm fr-mb-0 qa__reponse"
          >
            {{ q.reponse }}
          </p>
        </li>
      </ul>

      <nav
        v-if="pages > 1"
        class="fr-pagination fr-mt-2w"
        aria-label="Pages du jeu de questions"
      >
        <ul class="fr-pagination__list">
          <li>
            <button
              type="button"
              class="fr-pagination__link fr-pagination__link--prev fr-pagination__link--lg-label"
              :disabled="page <= 1"
              @click="page--"
            >
              Page précédente
            </button>
          </li>
          <li>
            <span
              class="fr-pagination__link"
              aria-current="page"
            >{{ page }} / {{ pages }}</span>
          </li>
          <li>
            <button
              type="button"
              class="fr-pagination__link fr-pagination__link--next fr-pagination__link--lg-label"
              :disabled="page >= pages"
              @click="page++"
            >
              Page suivante
            </button>
          </li>
        </ul>
      </nav>
    </section>
  </div>
</template>

<style scoped>
.qa__cartes { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr)); gap: 1rem; }
.qa__carte { border: 1px solid var(--border-default-grey); padding: 1rem 1.25rem; min-width: 0; }
.qa__discret { color: var(--text-mention-grey); }
.qa__filtres { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .75rem 1rem; margin-bottom: 1rem; }
.qa__filtres .fr-select-group, .qa__filtres .fr-input-group { margin: 0; }
.qa__filtres .fr-select-group { min-width: 10rem; }
.qa__recherche { flex: 1 1 14rem; min-width: 0; }
.qa__liste { list-style: none; padding: 0; margin: 0; display: grid; gap: .75rem; }
.qa__item { border: 1px solid var(--border-default-grey); padding: .75rem 1rem; min-width: 0; }
.qa__badges { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; margin-bottom: .5rem; }
.qa__badges .fr-tag { margin: 0; }
.qa__reponse { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
