<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Accueil</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Mes collections</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Les collections que je gère</h1>
    <p class="fr-text--sm fr-mb-3w" style="max-width:70ch">
      Celles dont vous êtes le créateur ou le garant. Les questions comptées sont celles de vos collègues, au bac à sable,
      sur {{ bilan?.fenetre_jours || 30 }} jours — vos propres essais n'y figurent pas, et le texte des questions n'est jamais gardé.
    </p>

    <div v-if="loading" class="fr-callout"><p>Chargement…</p></div>

    <div v-else-if="!cartes.length" class="fr-callout">
      <h2 class="fr-callout__title fr-h6">Vous ne gérez pas encore de collection.</h2>
      <p class="fr-callout__text fr-text--sm">Vous pouvez interroger toutes celles du catalogue ; en créer une n'est utile que si une source vous manque.</p>
      <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-2w">
        <NuxtLink to="/admin/catalog" class="fr-btn fr-btn--sm">Explorer le catalogue</NuxtLink>
        <NuxtLink to="/admin/create" class="fr-btn fr-btn--secondary fr-btn--sm">Créer une collection</NuxtLink>
      </div>
    </div>

    <div v-else class="fr-grid-row fr-grid-row--gutters">
      <div v-for="c in cartes" :key="c.col.name" class="fr-col-12 fr-col-md-6 fr-col-lg-4">
        <p class="fr-text--xs fr-mb-1v" style="color:var(--text-mention-grey);">
          {{ c.usage.questions }} question{{ c.usage.questions > 1 ? 's' : '' }} en {{ bilan?.fenetre_jours }} jours
          <template v-if="c.usage.signalements_ouverts">
            · <NuxtLink :to="`/c/${c.col.name}`" class="fr-link fr-text--xs">{{ c.usage.signalements_ouverts }} signalement{{ c.usage.signalements_ouverts > 1 ? 's' : '' }} à traiter</NuxtLink>
          </template>
        </p>
        <CarteCollection :col="c.col" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Collection } from '~/types/collection'
import type { BilanPartage } from '~/utils/accueil'

const { get } = useApi()
const bilan = ref<BilanPartage | null>(null)
const collections = ref<Collection[]>([])
const loading = ref(true)

// L'ordre du bilan (les plus interrogées d'abord) ; la carte vient du catalogue.
const cartes = computed(() => (bilan.value?.collections || [])
  .map(usage => ({ usage, col: collections.value.find(c => c.name === usage.name) }))
  .filter((x): x is { usage: BilanPartage['collections'][number]; col: Collection } => !!x.col))

onMounted(async () => {
  try {
    const [b, c] = await Promise.all([get('/api/accueil/mes-collections'), get('/api/collections')])
    bilan.value = b
    collections.value = c.collections || []
  } catch (e) {}
  loading.value = false
})
</script>
