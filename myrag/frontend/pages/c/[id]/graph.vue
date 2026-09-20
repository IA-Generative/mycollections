<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb fr-mb-1w" aria-label="vous êtes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ titre }}</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Graphe</a></li>
      </ol>
    </nav>
    <div class="graphe-tete">
      <h1 class="fr-h5 fr-mb-0">Graphe de références — {{ titre }}</h1>
      <button v-if="pleinEcranPossible" type="button" class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-fullscreen-line fr-btn--icon-left"
              title="Le graphe occupe tout l'écran. Échap pour revenir." @click="pleinEcran">
        Plein écran
      </button>
    </div>

    <!-- Le graphe sort du conteneur de la page (≈ 1 200 px) : il prend la largeur de la fenêtre et
         la hauteur qui reste sous l'en-tête. La largeur se MESURE (clientWidth) plutôt que `100vw`,
         qui compte la barre de défilement et ferait défiler la page de côté sous Windows. -->
    <div ref="cadre" class="graphe-cadre" :style="styleCadre">
      <iframe :src="`${baseUrl}/graph?corpus_id=${id}`" title="Graphe de références de la collection" allowfullscreen></iframe>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
const { baseUrl } = useApi()

const cadre = ref<HTMLElement | null>(null)
const styleCadre = ref<Record<string, string>>({})
const pleinEcranPossible = ref(false)
const MARGE = 12

function mesurer() {
  const el = cadre.value
  if (!el || !el.parentElement) return
  const large = document.documentElement.clientWidth
  const parent = el.parentElement.getBoundingClientRect()
  const haut = el.getBoundingClientRect().top + window.scrollY
  styleCadre.value = {
    width: `${large - 2 * MARGE}px`,
    marginLeft: `${MARGE - parent.left}px`,
    height: `${Math.max(520, window.innerHeight - Math.min(haut, 320) - MARGE)}px`,
  }
}

function pleinEcran() {
  cadre.value?.requestFullscreen?.().catch(() => {})
}

onMounted(() => {
  pleinEcranPossible.value = !!document.fullscreenEnabled
  mesurer()
  window.addEventListener('resize', mesurer)
  // Le titre arrive après la fiche : la hauteur disponible a pu bouger.
  nextTick(mesurer)
})
onBeforeUnmount(() => window.removeEventListener('resize', mesurer))
watch(titre, () => nextTick(mesurer))
</script>

<style scoped>
.graphe-tete { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem 1rem; margin-bottom: .75rem; }
.graphe-cadre { border: 1px solid var(--border-default-grey); border-radius: 4px; overflow: hidden; background: #fff; margin-bottom: -4rem; }
.graphe-cadre iframe { display: block; width: 100%; height: 100%; border: 0; }
.graphe-cadre:fullscreen { width: 100vw !important; height: 100vh !important; margin: 0 !important; border: 0; border-radius: 0; }
</style>
