<script setup lang="ts">
import type { QuestionSource } from '~/utils/assistants'
import { candidatesFiables, libelleServie, libelleSeuil, reponsesFiables } from '~/utils/assistants'
import { messageErreur } from '~/utils/collectif'

/**
 * Les réponses fiables d'un assistant : celles que ses sources servent telles quelles quand la
 * question leur ressemble assez, et les questions validées qui pourraient le devenir. Lecture seule
 * ici ; marquer ou retirer passe par la collection, et n'est proposé qu'à qui la gère (le serveur
 * le dit dans `peut_gerer`, rien n'est deviné).
 */
const props = defineProps<{ id: string, seuil: number }>()
const { questionsQualite, marquerFiable } = useAssistants()
const uid = `fiables-${useId()}`

const fiables = ref<QuestionSource[]>([])
const candidates = ref<QuestionSource[]>([])
const chargement = ref(true)
const erreur = ref('')
const message = ref('')
const enCours = ref('')
const dit = ref('')

async function charger () {
  try {
    const [f, c] = await Promise.all([
      questionsQualite(props.id, { fiable: 'true', par_page: '200' }),
      questionsQualite(props.id, { fiable: 'false', relecture: 'valide', par_page: '200' }),
    ])
    fiables.value = reponsesFiables(f.questions)
    candidates.value = candidatesFiables(c.questions)
    erreur.value = ''
  }
  catch (e) {
    erreur.value = `Les réponses fiables n'ont pas pu être lues : ${messageErreur(e)}`
  }
  finally {
    chargement.value = false
  }
}
onMounted(charger)

async function basculer (q: QuestionSource, fiable: boolean) {
  enCours.value = q.id
  message.value = ''
  erreur.value = ''
  try {
    await marquerFiable(q.collection, q.id, fiable)
    dit.value = fiable ? 'La réponse est maintenant fiable : elle sera servie telle quelle.' : 'La réponse n\'est plus fiable : la question repasse par la recherche.'
    await charger()
  }
  catch (e) {
    erreur.value = `Le changement n'a pas pu être fait : ${messageErreur(e)}`
  }
  finally {
    enCours.value = ''
  }
}
</script>

<template>
  <div>
    <p class="fr-text--sm fr-mb-2w">
      {{ libelleSeuil(seuil) }} Elle l'est sans aucune recherche, et chaque service est compté.
    </p>
    <div
      v-if="dit"
      class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w"
      role="status"
    >
      <p>{{ dit }}</p>
    </div>
    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
      role="alert"
    >
      <p>{{ erreur }}</p>
    </div>
    <p
      v-if="chargement"
      class="fr-text--sm"
      aria-live="polite"
    >
      Chargement…
    </p>
    <template v-else>
      <section :aria-labelledby="`${uid}-liste`">
        <h2
          :id="`${uid}-liste`"
          class="fr-h5"
        >
          Réponses fiables ({{ fiables.length }})
        </h2>
        <div
          v-if="!fiables.length"
          class="fr-callout"
        >
          <p class="fr-callout__text fr-text--sm">
            Aucune réponse fiable pour l'instant. Choisissez ci-dessous une question validée dont la réponse est sûre.
          </p>
        </div>
        <ul
          v-else
          class="fiables__liste"
        >
          <li
            v-for="q in fiables"
            :key="q.id"
            class="fiables__item"
          >
            <p class="fr-text--bold fr-mb-1v">
              {{ q.question }}
            </p>
            <p class="fr-text--sm fr-mb-1w fiables__reponse">
              {{ q.reponse }}
            </p>
            <p class="fr-text--xs fr-mb-1w fiables__discret">
              <span class="fr-tag fr-tag--sm">{{ q.collection_titre }}</span>
              <span class="fr-badge fr-badge--sm fr-badge--no-icon fr-badge--success fr-ml-1w">{{ libelleServie(q.servie_fois) }}</span>
            </p>
            <button
              v-if="q.peut_gerer"
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary"
              :disabled="enCours === q.id"
              @click="basculer(q, false)"
            >
              Retirer<span class="fr-sr-only"> la réponse fiable « {{ q.question }} »</span>
            </button>
            <p
              v-else
              class="fr-text--xs fr-mb-0 fiables__discret"
            >
              Seules les personnes qui gèrent « {{ q.collection_titre }} » peuvent la retirer.
            </p>
          </li>
        </ul>
      </section>

      <section
        class="fr-mt-4w"
        :aria-labelledby="`${uid}-candidates`"
      >
        <h2
          :id="`${uid}-candidates`"
          class="fr-h5"
        >
          Questions validées qui pourraient le devenir ({{ candidates.length }})
        </h2>
        <p
          v-if="!candidates.length"
          class="fr-text--sm"
        >
          Aucune autre question validée avec une réponse de référence.
        </p>
        <ul
          v-else
          class="fiables__liste"
        >
          <li
            v-for="q in candidates"
            :key="q.id"
            class="fiables__item"
          >
            <p class="fr-text--bold fr-mb-1v">
              {{ q.question }}
            </p>
            <p class="fr-text--sm fr-mb-1w fiables__reponse">
              {{ q.reponse }}
            </p>
            <p class="fr-text--xs fr-mb-1w fiables__discret">
              <span class="fr-tag fr-tag--sm">{{ q.collection_titre }}</span>
            </p>
            <button
              v-if="q.peut_gerer"
              type="button"
              class="fr-btn fr-btn--sm fr-btn--secondary"
              :disabled="enCours === q.id"
              @click="basculer(q, true)"
            >
              Marquer fiable<span class="fr-sr-only"> la question « {{ q.question }} »</span>
            </button>
            <p
              v-else
              class="fr-text--xs fr-mb-0 fiables__discret"
            >
              Seules les personnes qui gèrent « {{ q.collection_titre }} » peuvent la marquer fiable.
            </p>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.fiables__liste { list-style: none; padding: 0; margin: 0; display: grid; gap: .75rem; }
.fiables__item { border: 1px solid var(--border-default-grey); border-left: 4px solid var(--border-plain-success); padding: .75rem 1rem; min-width: 0; }
.fiables__reponse { white-space: pre-wrap; overflow-wrap: anywhere; }
.fiables__discret { color: var(--text-mention-grey); }
</style>
