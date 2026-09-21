<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb fr-mb-1w" aria-label="vous êtes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ titre }}</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Liens entre documents</a></li>
      </ol>
    </nav>
    <div class="graphe-tete">
      <h1 class="fr-h5 fr-mb-0">Liens entre documents — {{ titre }}</h1>
      <button v-if="pleinEcranPossible" type="button" class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-fullscreen-line fr-btn--icon-left"
              title="La carte des liens occupe tout l'écran. Échap pour revenir." @click="pleinEcran">
        Plein écran
      </button>
    </div>

    <!-- Le graphe sort du conteneur de la page (≈ 1 200 px) : il prend la largeur de la fenêtre et
         la hauteur qui reste sous l'en-tête. La largeur se MESURE (clientWidth) plutôt que `100vw`,
         qui compte la barre de défilement et ferait défiler la page de côté sous Windows. -->
    <div ref="cadre" class="graphe-cadre" :style="styleCadre">
      <iframe :src="`${baseUrl}/graph?corpus_id=${id}`" title="Liens entre les documents de la collection" allowfullscreen></iframe>
      <!-- En plein écran, l'en-tête de la page a disparu : la sortie doit se voir DANS le graphe.
           Le bouton reste ; le rappel « Échap » s'efface après quelques secondes. -->
      <div v-if="enPleinEcran" class="graphe-sortie">
        <span v-if="rappelVisible" class="graphe-sortie__rappel" role="status">Appuyez sur <kbd>Échap</kbd> pour quitter le plein écran</span>
        <button ref="btnSortie" type="button" class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-close-line fr-btn--icon-left" @click="quitterPleinEcran">
          Quitter le plein écran
        </button>
      </div>
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

const enPleinEcran = ref(false)
const rappelVisible = ref(false)
const btnSortie = ref<HTMLButtonElement | null>(null)
let minuterieRappel: ReturnType<typeof setTimeout> | null = null

function pleinEcran() {
  cadre.value?.requestFullscreen?.().catch(() => {})
}
function quitterPleinEcran() {
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {})
}
/** Le navigateur est seul juge : Échap, ou son propre bouton, sortent aussi du plein écran. */
function suivrePleinEcran() {
  enPleinEcran.value = document.fullscreenElement === cadre.value
  if (minuterieRappel) { clearTimeout(minuterieRappel); minuterieRappel = null }
  rappelVisible.value = enPleinEcran.value
  if (enPleinEcran.value) {
    minuterieRappel = setTimeout(() => { rappelVisible.value = false }, 6000)
    nextTick(() => btnSortie.value?.focus())  // la sortie est à une touche, clavier compris
  }
}

onMounted(() => {
  pleinEcranPossible.value = !!document.fullscreenEnabled
  mesurer()
  window.addEventListener('resize', mesurer)
  document.addEventListener('fullscreenchange', suivrePleinEcran)
  // Le titre arrive après la fiche : la hauteur disponible a pu bouger.
  nextTick(mesurer)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', mesurer)
  document.removeEventListener('fullscreenchange', suivrePleinEcran)
  if (minuterieRappel) clearTimeout(minuterieRappel)
})
watch(titre, () => nextTick(mesurer))
</script>

<style scoped>
.graphe-tete { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem 1rem; margin-bottom: .75rem; }
.graphe-cadre { border: 1px solid var(--border-default-grey); border-radius: 4px; overflow: hidden; background: #fff; margin-bottom: -4rem; }
.graphe-cadre iframe { display: block; width: 100%; height: 100%; border: 0; }
.graphe-cadre { position: relative; }
/* En bas au centre : le haut du visualiseur est pris (carte d'état à gauche, compteur à droite),
   ses deux volets tiennent les coins du bas — on passe juste au-dessus de leur rangée. */
.graphe-sortie { position: absolute; z-index: 5; bottom: 60px; left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: .75rem; white-space: nowrap; }
.graphe-sortie .fr-btn { background-color: #fff; box-shadow: 0 2px 8px rgba(0, 0, 18, .2); }
.graphe-sortie__rappel { font-size: .85rem; color: #fff; background: rgba(22, 22, 22, .86); padding: .35rem .7rem; border-radius: 4px; }
.graphe-sortie__rappel kbd { font: inherit; font-weight: 700; border: 1px solid rgba(255, 255, 255, .6); border-radius: 3px; padding: 0 .3rem; }
.graphe-cadre:fullscreen { width: 100vw !important; height: 100vh !important; margin: 0 !important; border: 0; border-radius: 0; }
</style>
