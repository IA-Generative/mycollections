<script setup lang="ts">
import type { Collection } from '~/types/collection'
import type { BilanPartage } from '~/utils/accueil'
import { indicateursCollection, nombre } from '~/utils/accueil'
import { titreDe } from '~/utils/catalogue'
import { libelleEtat } from '~/utils/collectif'
import { etiquetteResana, phraseCouverture } from '~/utils/resana'

/**
 * Les collections que je gère, chacune avec ce qu'elle rend : questions de collègues sur la
 * fenêtre, note des usagers, signalements à traiter. Pas de fil d'Ariane : le menu dit où l'on est.
 */
const { get } = useApi()
const titre = 'Mes collections'
const bilan = ref<BilanPartage | null>(null)
const collections = ref<Collection[]>([])
const loading = ref(true)

// L'ordre du bilan (les plus interrogées d'abord) ; la note vient du catalogue.
const cartes = computed(() => (bilan.value?.collections || [])
  .map(usage => ({ usage, col: collections.value.find(c => c.name === usage.name) }))
  .filter((x): x is { usage: BilanPartage['collections'][number], col: Collection } => !!x.col)
  .map(x => ({ ...x, chiffres: indicateursCollection(x.usage, x.col) })))

onMounted(async () => {
  try {
    const [b, c] = await Promise.all([get('/api/accueil/mes-collections'), get('/api/collections')])
    bilan.value = b
    collections.value = c.collections || []
  }
  catch {}
  loading.value = false
})
</script>

<template>
  <div>
    <div class="mes-collections__tete fr-mb-2w">
      <div>
        <h1 class="fr-h3 fr-mb-0">
          {{ titre }}
        </h1>
        <p class="fr-text--sm fr-mb-0 mes-collections__discret">
          Celles dont vous êtes le créateur ou le garant. Questions de vos collègues sur {{ bilan?.fenetre_jours || 30 }} jours, sans vos propres essais.
        </p>
      </div>
      <div class="mes-collections__actions">
        <NuxtLink
          to="/admin/create"
          class="fr-btn fr-btn--sm fr-btn--icon-left fr-icon-add-line"
        >
          Partager une nouvelle collection
        </NuxtLink>
      </div>
    </div>

    <div
      v-if="loading"
      class="fr-callout"
    >
      <p>Chargement…</p>
    </div>

    <div
      v-else-if="!cartes.length"
      class="fr-callout"
    >
      <h2 class="fr-callout__title fr-h6">
        Vous ne gérez pas encore de collection.
      </h2>
      <p class="fr-callout__text fr-text--sm">
        Vous pouvez interroger toutes celles du catalogue ; en créer une n'est utile que si une source vous manque.
      </p>
      <NuxtLink
        to="/admin/catalog"
        class="fr-btn fr-btn--sm fr-mt-2w"
      >
        Explorer le catalogue
      </NuxtLink>
    </div>

    <ul
      v-else
      class="fr-grid-row fr-grid-row--gutters mes-collections__liste"
      role="list"
    >
      <li
        v-for="c in cartes"
        :key="c.col.name"
        class="fr-col-12 fr-col-md-6 fr-col-xl-4"
      >
        <article class="mes-carte">
          <div class="mes-carte__tete">
            <h2 class="fr-h6 fr-mb-0">
              <NuxtLink
                :to="`/c/${c.col.name}`"
                class="mes-carte__lien"
              >
                {{ titreDe(c.col) }}
              </NuxtLink>
            </h2>
            <span
              class="fr-badge fr-badge--sm fr-badge--no-icon"
              :class="c.col.etat_collab === 'publiee_tous' ? 'fr-badge--success' : 'fr-badge--warning'"
            >
              {{ libelleEtat(c.col.etat_collab) }}
            </span>
          </div>
          <p
            v-if="c.col.source_resume?.type === 'resana'"
            class="fr-mb-0"
          >
            <span
              class="fr-tag fr-tag--sm"
              :title="phraseCouverture(c.col.source_resume)"
            >{{ etiquetteResana(c.col.source_resume) }}</span>
          </p>
          <dl class="mes-carte__chiffres">
            <div>
              <dt class="fr-sr-only">
                Questions de collègues
              </dt>
              <dd><b>{{ nombre(c.chiffres.questions) }}</b><span>question{{ c.chiffres.questions > 1 ? 's' : '' }} en {{ bilan?.fenetre_jours }} j</span></dd>
            </div>
            <div>
              <dt class="fr-sr-only">
                Note des usagers
              </dt>
              <dd v-if="c.chiffres.satisfaction !== null">
                <b>{{ c.chiffres.satisfaction }} %</b><span>utiles · {{ nombre(c.chiffres.avis) }} avis</span>
              </dd>
              <dd v-else>
                <b>—</b><span>pas encore d'avis</span>
              </dd>
            </div>
            <div
              v-if="c.chiffres.signalements"
              class="mes-carte__alerte"
            >
              <dt class="fr-sr-only">
                Signalements
              </dt>
              <dd>
                <b>{{ c.chiffres.signalements }}</b>
                <NuxtLink
                  :to="`/c/${c.col.name}?onglet=signalements`"
                  class="fr-link fr-text--xs"
                >
                  à traiter
                </NuxtLink>
              </dd>
            </div>
          </dl>
          <div class="mes-carte__actions">
            <NuxtLink
              :to="`/c/${c.col.name}/playground`"
              class="fr-link fr-text--sm"
            >
              Poser une question
            </NuxtLink>
            <NuxtLink
              :to="`/c/${c.col.name}/qualite`"
              class="fr-link fr-text--sm"
            >
              Qualité
            </NuxtLink>
            <NuxtLink
              :to="`/c/${c.col.name}/publish`"
              class="fr-link fr-text--sm"
            >
              Partager
            </NuxtLink>
          </div>
        </article>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.mes-collections__tete { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: .75rem 1.5rem; }
.mes-collections__discret { color: var(--text-mention-grey); }
.mes-collections__actions { display: flex; flex-wrap: wrap; gap: .5rem; }
.mes-collections__liste { list-style: none; padding: 0; }
.mes-carte { height: 100%; display: flex; flex-direction: column; gap: .75rem; padding: 1rem 1.25rem; border: 1px solid var(--border-default-grey); border-bottom: 3px solid var(--border-plain-blue-france); }
.mes-carte__tete { display: flex; justify-content: space-between; align-items: flex-start; gap: .75rem; }
.mes-carte__lien { background-image: none; }
.mes-carte__lien:hover { text-decoration: underline; }
.mes-carte__chiffres { display: flex; flex-wrap: wrap; gap: .5rem 1.75rem; margin: 0; padding: 0; }
.mes-carte__chiffres dd { margin: 0; display: flex; flex-direction: column; }
.mes-carte__chiffres b { font-size: 1.4rem; line-height: 1.15; color: var(--text-title-blue-france); font-variant-numeric: tabular-nums; }
.mes-carte__chiffres span { font-size: .78rem; color: var(--text-mention-grey); }
.mes-carte__alerte b { color: var(--text-default-warning); }
.mes-carte__actions { display: flex; flex-wrap: wrap; gap: .25rem 1.25rem; margin-top: auto; }
</style>
