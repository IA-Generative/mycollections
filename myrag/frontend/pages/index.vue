<script setup lang="ts">
import type { Categorie, Collection } from '~/types/collection'
import type { BilanPartage, Exemple } from '~/utils/accueil'
import { impactDuPartage, indicateurs, messageImpact, nombre, porteNonClassees, portes, tuilesAccueil } from '~/utils/accueil'
import { BANDEAU, bandeauAffiche, CLE_BANDEAUX_FERMES, lireFermes } from '~/utils/bandeau'
import { entreeEntraide } from '~/utils/navigation'

/**
 * L'accueil, compact (2026-10-20) : un bandeau d'information qu'on peut fermer, le titre et une
 * phrase, ce que mes collections ont rendu possible (collègues aidés, note des usagers), quatre
 * tuiles basses, les catégories et l'entraide. Tout tient sur un petit écran de portable.
 * Ce que la page dit vient de utils/accueil.ts et utils/bandeau.ts (testés).
 */
const { get } = useApi()
const { capacites } = useCapacites()
const { lister: listerCategories } = useCategories()

const collections = ref<Collection[]>([])
const categories = ref<Categorie[]>([])
const bilan = ref<BilanPartage | null>(null)
const exemple = ref<Exemple | null>(null)
const catalogueCharge = ref(false)

const chiffres = computed(() => catalogueCharge.value ? indicateurs(collections.value, categories.value) : null)
const tuiles = computed(() => tuilesAccueil(capacites.value, exemple.value, chiffres.value))
const impact = computed(() => impactDuPartage(bilan.value, collections.value))
const message = computed(() => impact.value ? messageImpact(impact.value) : null)
const entraide = computed(() => entreeEntraide(capacites.value))
const puces = computed(() => {
  const nonClassees = porteNonClassees(collections.value, categories.value)
  return [...portes(collections.value, categories.value), ...(nonClassees ? [nonClassees] : [])]
})

// Le bandeau d'information : fermé, il ne revient pas (préférence de ce navigateur seulement).
const fermes = ref<string[]>([])
const bandeauVisible = computed(() => bandeauAffiche(BANDEAU, fermes.value))
function fermerBandeau () {
  if (!BANDEAU) {
    return
  }
  fermes.value = [...fermes.value, BANDEAU.id]
  try {
    localStorage.setItem(CLE_BANDEAUX_FERMES, JSON.stringify(fermes.value))
  }
  catch { /* stockage indisponible : fermé pour cette visite */ }
}

onMounted(() => {
  try {
    fermes.value = lireFermes(localStorage.getItem(CLE_BANDEAUX_FERMES))
  }
  catch { /* stockage indisponible : le bandeau s'affiche */ }
  get('/api/accueil/exemple')
    .then((r) => {
      exemple.value = r.exemple || null
    })
    .catch(() => {})
  get('/api/accueil/mes-collections')
    .then((r) => {
      bilan.value = r
    })
    .catch(() => {})
  listerCategories()
    .then((r) => {
      categories.value = r
    })
    .catch(() => {})
  get('/api/collections')
    .then((r) => {
      collections.value = r.collections || []
      catalogueCharge.value = true
    })
    .catch(() => {})
})
</script>

<template>
  <div class="accueil">
    <!-- Bandeau d'information éditorial, que chacun peut fermer. -->
    <div
      v-if="bandeauVisible && BANDEAU"
      class="fr-notice fr-notice--info fr-mb-2w accueil-bandeau"
      role="region"
      aria-label="Information"
    >
      <div class="fr-notice__body">
        <p>
          <span class="fr-notice__title">{{ BANDEAU.titre }}</span>
          <span class="fr-notice__desc">{{ BANDEAU.texte }}</span>
          <NuxtLink
            v-if="BANDEAU.lien"
            :to="BANDEAU.lien.vers"
            class="fr-notice__link"
          >
            {{ BANDEAU.lien.libelle }}
          </NuxtLink>
        </p>
        <button
          type="button"
          class="fr-btn--close fr-btn"
          title="Masquer le message"
          @click="fermerBandeau"
        >
          Masquer le message
        </button>
      </div>
    </div>

    <h1 class="fr-h3 fr-mb-1v">
      Que souhaitez-vous faire ?
    </h1>
    <p class="fr-mb-2w accueil-chapeau">
      Découvrez les collections de vos collègues, partagez les vôtres sans rien préparer, entraidez-vous.
    </p>

    <!-- Ce que mes collections ont rendu possible : la raison de continuer. -->
    <section
      v-if="impact && message"
      class="accueil-impact fr-mb-3w"
      aria-labelledby="titre-impact"
    >
      <div class="accueil-impact__message">
        <h2
          id="titre-impact"
          class="fr-h6 fr-mb-1v"
        >
          {{ message.titre }}
        </h2>
        <p class="fr-text--sm fr-mb-0">
          {{ message.texte }}
          <template v-if="impact.plusUtile">
            La plus utile : <NuxtLink
              :to="`/c/${impact.plusUtile.name}`"
              class="fr-link fr-text--sm"
            >
              {{ impact.plusUtile.titre }}
            </NuxtLink>.
          </template>
        </p>
      </div>
      <dl class="accueil-impact__chiffres">
        <div v-if="impact.personnes">
          <dt class="fr-sr-only">
            Collègues aidés
          </dt>
          <dd><b>{{ nombre(impact.personnes) }}</b><span>collègue{{ impact.personnes > 1 ? 's' : '' }} aidé{{ impact.personnes > 1 ? 's' : '' }}</span></dd>
        </div>
        <div>
          <dt class="fr-sr-only">
            Questions
          </dt>
          <dd><b>{{ nombre(impact.questions) }}</b><span>question{{ impact.questions > 1 ? 's' : '' }} en {{ impact.fenetre_jours }} jours</span></dd>
        </div>
        <div v-if="impact.satisfaction !== null">
          <dt class="fr-sr-only">
            Note des usagers
          </dt>
          <dd><b>{{ impact.satisfaction }} %</b><span>de réponses utiles · {{ nombre(impact.avis) }} avis</span></dd>
        </div>
        <div
          v-if="impact.signalements"
          class="accueil-impact__alerte"
        >
          <dt class="fr-sr-only">
            Signalements
          </dt>
          <dd>
            <b>{{ impact.signalements }}</b>
            <NuxtLink
              to="/mes-collections"
              class="fr-link fr-text--xs"
            >
              signalement{{ impact.signalements > 1 ? 's' : '' }} à traiter
            </NuxtLink>
          </dd>
        </div>
      </dl>
    </section>

    <!-- Quatre tuiles basses : un titre, une phrase. -->
    <ul
      class="accueil-tuiles fr-grid-row fr-grid-row--gutters fr-mb-2w"
      role="list"
    >
      <li
        v-for="t in tuiles"
        :key="t.cle"
        class="fr-col-12 fr-col-md-6 fr-col-lg-3"
      >
        <div
          class="fr-tile fr-tile--sm fr-tile--horizontal fr-enlarge-link accueil-tuile"
          :data-tuile="t.cle"
        >
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h2 class="fr-tile__title">
                <NuxtLink
                  :to="t.vers"
                  class="fr-tile__link"
                >
                  {{ t.titre }}
                </NuxtLink>
              </h2>
              <p class="fr-tile__desc">
                {{ t.description }}
              </p>
              <p
                v-if="t.mention"
                class="fr-tile__detail"
              >
                {{ t.mention }}
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span
                class="fr-icon--lg"
                :class="[t.icone]"
                aria-hidden="true"
              />
            </div>
          </div>
        </div>
      </li>
    </ul>

    <!-- Les catégories du catalogue, et l'entraide, sur un seul bloc. -->
    <div class="accueil-pied">
      <section
        v-if="puces.length"
        class="accueil-categories"
        aria-labelledby="titre-categories"
      >
        <h2
          id="titre-categories"
          class="fr-text--sm fr-text--bold fr-mb-1v"
        >
          Parcourir par catégorie
        </h2>
        <ul class="fr-tags-group">
          <li
            v-for="p in puces"
            :key="p.cle"
          >
            <NuxtLink
              :to="{ path: '/admin/catalog', query: { categorie: p.cle } }"
              class="fr-tag fr-tag--sm"
            >
              {{ p.libelle }}&nbsp;<span class="accueil-discret">{{ p.nb }}</span>
            </NuxtLink>
          </li>
        </ul>
      </section>
      <p
        v-if="entraide"
        class="fr-text--sm fr-mb-0 accueil-entraide"
      >
        <span
          class="fr-icon-team-line fr-icon--sm fr-mr-1v"
          aria-hidden="true"
        /><strong>Une donnée vous manque ?</strong>
        <NuxtLink
          :to="entraide.vers"
          class="fr-link fr-text--sm"
        >
          Demandez au réseau
        </NuxtLink>
      </p>
    </div>
  </div>
</template>

<style scoped>
.accueil-chapeau { color: var(--text-mention-grey); max-width: 60rem; }
.accueil-impact {
  display: flex; flex-wrap: wrap; align-items: center; gap: .75rem 2rem; padding: .75rem 1.25rem;
  background: var(--background-alt-blue-france); border-left: 4px solid var(--border-plain-blue-france);
}
.accueil-impact__message { flex: 1 1 22rem; min-width: 0; }
.accueil-impact__chiffres { display: flex; flex-wrap: wrap; gap: .5rem 2rem; margin: 0; padding: 0; }
.accueil-impact__chiffres dd { margin: 0; display: flex; flex-direction: column; }
.accueil-impact__chiffres b { font-size: 1.75rem; line-height: 1.1; color: var(--text-title-blue-france); font-variant-numeric: tabular-nums; }
.accueil-impact__chiffres span { font-size: .8rem; color: var(--text-mention-grey); }
.accueil-impact__alerte b { color: var(--text-default-warning); }
.accueil-tuiles { list-style: none; padding: 0; }
.accueil-tuile { height: 100%; }
/* Des tuiles basses : moins de marge que le DSFR, une phrase sur une ou deux lignes. */
.accueil-tuile.fr-tile--sm { padding: .75rem 1rem; }
.accueil-tuile :deep(.fr-tile__content) { padding-bottom: 0; }
.accueil-tuile :deep(.fr-tile__title) { margin-bottom: .25rem; }
.accueil-tuile :deep(.fr-tile__desc) { font-size: .85rem; line-height: 1.3rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.accueil-pied { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: .75rem 2rem; }
.accueil-entraide { padding: .5rem .75rem; background: var(--background-alt-blue-france); }
.accueil-discret { color: var(--text-mention-grey); font-variant-numeric: tabular-nums; }
.accueil-categories .fr-tags-group { margin-bottom: -.5rem; }
</style>
