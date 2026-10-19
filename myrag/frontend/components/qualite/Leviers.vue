<script setup lang="ts">
import { messageErreur } from '~/utils/collectif'
import { aLaRegleDeGarde, avancementTravaux, REGLE_DE_GARDE } from '~/utils/qualite'

/** Les leviers : réindexer (avec suivi), préciser les consignes, marquer des réponses fiables. */
const props = defineProps<{ collection: string, synthese: any, signale?: string }>()
const emit = defineEmits<{ voirFiables: [], change: [] }>()
const { get, post, patch } = useApi()
const fiche = ref<any>(null)
const sources = ref(0)
const confirmer = ref(false)
const travaux = ref<any[]>([])
const erreur = ref('')
let minuterie: ReturnType<typeof setTimeout> | null = null

const vd = computed(() => props.synthese?.derniere_terminee?.verdicts || {})
const sansSource = computed(() => vd.value.sans_source || 0)
const refusKo = computed(() => vd.value.refus_ko || 0)
const fiables = computed(() => props.synthese?.questions?.fiables || 0)
const extrait = computed(() => {
  const t = fiche.value?.system_prompt || ''
  return t.length > 500 ? `${t.slice(0, 500)}…` : t
})
const avancement = computed(() => {
  const a = avancementTravaux(travaux.value)
  return { ...a, fini: a.total > 0 && a.finis === a.total }
})

onMounted(async () => {
  try {
    fiche.value = await get(`/api/collections/${encodeURIComponent(props.collection)}`)
  }
  catch (e) {
    erreur.value = `La fiche n'a pas pu être lue : ${messageErreur(e)}`
  }
  try {
    const s = await get(`/api/ingest/${encodeURIComponent(props.collection)}/sources`)
    sources.value = new Set((s.sources || []).map((x: any) => x.filename)).size
  }
  catch { sources.value = 0 }
})
onBeforeUnmount(() => {
  if (minuterie) { clearTimeout(minuterie) }
})

async function suivre (ids: string[]) {
  try {
    travaux.value = await Promise.all(ids.map(id => get(`/api/ingest/jobs/${id}`)))
  }
  catch { /* on réessaie au tour suivant */ }
  if (!avancement.value.fini) {
    minuterie = setTimeout(suivre, 3000, ids)
  }
  else { emit('change') }
}

async function reindexer () {
  confirmer.value = false
  erreur.value = ''
  try {
    const r = await post(`/api/ingest/${encodeURIComponent(props.collection)}/reindex`, {})
    travaux.value = (r.jobs || []).map(() => ({ status: 'pending' }))
    suivre(r.jobs || [])
  }
  catch (e) {
    erreur.value = `La réindexation n'a pas abouti : ${messageErreur(e)}`
  }
}

async function ajouterRegle () {
  erreur.value = ''
  try {
    const consignes = (fiche.value?.system_prompt || '') + REGLE_DE_GARDE
    await patch(`/api/collections/${encodeURIComponent(props.collection)}/system-prompt`, { system_prompt: consignes })
    fiche.value = { ...fiche.value, system_prompt: consignes }
    emit('change')
  }
  catch (e) {
    erreur.value = `Les consignes n'ont pas pu être mises à jour : ${messageErreur(e)}`
  }
}
</script>

<template>
  <div class="leviers">
    <p class="fr-text--sm">
      Trois façons d'améliorer les réponses. Après chaque changement, mesurez à nouveau : la courbe montre son effet.
    </p>
    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
      role="alert"
    >
      <p>{{ erreur }}</p>
    </div>

    <div class="leviers__grille">
      <!-- Réindexation (maintenance) -->
      <section
        id="levier-decoupage"
        class="leviers__carte"
        :class="{ 'leviers__carte--signalee': signale === 'decoupage' }"
        aria-labelledby="levier-decoupage-titre"
      >
        <h3
          id="levier-decoupage-titre"
          class="fr-h6 fr-mb-1w"
        >
          Réindexer les documents
        </h3>
        <p class="fr-text--sm">
          La collection cherche des <em>passages</em> dans les documents : si l'indexation a été interrompue ou a mal
          tourné, les réponses pâtissent. Réindexer efface les passages actuels, puis renvoie chaque document conservé
          au moteur de recherche, qui le découpe de nouveau.
        </p>
        <p
          v-if="sansSource"
          class="fr-text--sm"
        >
          À la dernière mesure, <strong>{{ sansSource }} question{{ sansSource > 1 ? 's' : '' }}</strong> {{ sansSource > 1 ? 'n\'ont' : 'n\'a' }} trouvé aucun passage.
        </p>
        <template v-if="sources > 0">
          <div
            v-if="!confirmer"
            class="fr-btns-group fr-btns-group--sm"
          >
            <button
              type="button"
              class="fr-btn fr-btn--secondary"
              :disabled="!!travaux.length && !avancement.fini"
              @click="confirmer = true"
            >
              Réindexer les {{ sources }} document{{ sources > 1 ? 's' : '' }}
            </button>
          </div>
          <div
            v-else
            class="fr-alert fr-alert--warning fr-alert--sm fr-mb-1w"
          >
            <p>
              Les passages actuels sont effacés puis recréés : pendant quelques minutes, la collection répond mal.
            </p>
            <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-1w">
              <button
                type="button"
                class="fr-btn"
                @click="reindexer"
              >
                Réindexer maintenant
              </button>
              <button
                type="button"
                class="fr-btn fr-btn--tertiary"
                @click="confirmer = false"
              >
                Annuler
              </button>
            </div>
          </div>
          <div
            v-if="travaux.length"
            class="fr-mt-1w"
            aria-live="polite"
          >
            <p class="fr-text--xs fr-mb-1v">
              {{ avancement.fini ? 'Réindexation terminée' : 'Réindexation en cours' }} : {{ avancement.finis }} / {{ avancement.total }} document{{ avancement.total > 1 ? 's' : '' }}
              <template v-if="avancement.echecs">
                ({{ avancement.echecs }} en échec)
              </template>.
              <template v-if="avancement.fini">
                Mesurez à nouveau pour voir l'effet.
              </template>
            </p>
            <progress
              :value="avancement.pct"
              max="100"
              class="leviers__barre"
              :aria-label="`Avancement de la réindexation : ${avancement.pct} %`"
            />
          </div>
        </template>
        <p
          v-else-if="fiche"
          class="fr-text--sm"
        >
          Aucun fichier d'origine conservé : pour réindexer, <NuxtLink
            :to="`/c/${collection}/upload`"
            class="fr-link"
          >
            redéposez les documents
          </NuxtLink>.
        </p>
      </section>

      <!-- Consignes -->
      <section
        id="levier-consignes"
        class="leviers__carte"
        :class="{ 'leviers__carte--signalee': signale === 'consignes' }"
        aria-labelledby="levier-consignes-titre"
      >
        <h3
          id="levier-consignes-titre"
          class="fr-h6 fr-mb-1w"
        >
          Consignes données à l'assistant
        </h3>
        <p class="fr-text--sm">
          Le ton, la façon de citer, ce qu'il faut refuser. Une consigne précise (« donne la liste complète des
          pièces ») corrige souvent une réponse partielle.
        </p>
        <pre
          v-if="fiche?.system_prompt"
          class="fr-text--xs leviers__extrait"
        >{{ extrait }}</pre>
        <p
          v-if="refusKo"
          class="fr-text--sm"
        >
          À la dernière mesure, <strong>{{ refusKo }} question{{ refusKo > 1 ? 's' : '' }} hors sujet</strong> {{ refusKo > 1 ? 'ont' : 'a' }} reçu une réponse inventée.
        </p>
        <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-btns-group--icon-left">
          <NuxtLink
            :to="`/c/${collection}/prompt`"
            class="fr-btn fr-btn--secondary fr-icon-edit-line fr-btn--icon-left"
          >
            Modifier les consignes
          </NuxtLink>
          <button
            v-if="fiche && !aLaRegleDeGarde(fiche.system_prompt)"
            type="button"
            class="fr-btn fr-btn--tertiary"
            @click="ajouterRegle"
          >
            Ajouter une règle de garde
          </button>
        </div>
        <p
          v-if="fiche && aLaRegleDeGarde(fiche.system_prompt)"
          class="fr-text--xs fr-mb-0 leviers__discret"
        >
          Les consignes contiennent une règle de garde : les questions hors sujet doivent être refusées.
        </p>
      </section>

      <!-- Réponses fiables -->
      <section
        class="leviers__carte"
        aria-labelledby="levier-fiables-titre"
      >
        <h3
          id="levier-fiables-titre"
          class="fr-h6 fr-mb-1w"
        >
          Réponses fiables
        </h3>
        <p class="fr-text--sm">
          Pour les questions fréquentes, une réponse validée par vous peut être donnée telle quelle, sans passer par
          la recherche. Cochez « Réponse fiable » sur une question validée du jeu.
        </p>
        <p class="fr-text--sm">
          <strong>{{ fiables }}</strong> réponse{{ fiables > 1 ? 's' : '' }} fiable{{ fiables > 1 ? 's' : '' }} aujourd'hui.
        </p>
        <p class="fr-text--xs leviers__discret">
          Bientôt : ces réponses seront servies en priorité dans le bac à sable et l'assistant. Pour l'instant, elles
          servent de référence aux mesures.
        </p>
        <button
          type="button"
          class="fr-btn fr-btn--sm fr-btn--tertiary"
          @click="emit('voirFiables')"
        >
          Voir les réponses fiables
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.leviers__grille { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 1rem; }
.leviers__carte { border: 1px solid var(--border-default-grey); padding: 1rem 1.25rem; min-width: 0; }
.leviers__carte--signalee { border-color: var(--border-action-high-blue-france); box-shadow: inset 0 0 0 1px var(--border-action-high-blue-france); }
.leviers__extrait { white-space: pre-wrap; background: var(--background-alt-grey); padding: .5rem; max-height: 10rem; overflow-y: auto; }
.leviers__barre { width: 100%; height: .5rem; }
.leviers__discret { color: var(--text-mention-grey); }
</style>
