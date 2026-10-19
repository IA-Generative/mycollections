<script setup lang="ts">
import type { Categorie, Collection } from '~/types/collection'
import type { BilanPartage, Exemple } from '~/utils/accueil'
import { indicateurs, nombre, porteNonClassees, portes, tuilesAccueil } from '~/utils/accueil'

const { get } = useApi()
const { capacites } = useCapacites()
const { lister: listerCategories } = useCategories()

const collections = ref<Collection[]>([])
const categories = ref<Categorie[]>([])
const bilan = ref<BilanPartage | null>(null)
const bilanCharge = ref(false)
const exemple = ref<Exemple | null>(null)
const catalogueCharge = ref(false)
const tirage = ref(false)

const chiffres = computed(() => catalogueCharge.value ? indicateurs(collections.value, categories.value) : null)
const tuiles = computed(() => tuilesAccueil(capacites.value, bilan.value, exemple.value, chiffres.value))
const puces = computed(() => {
  const nonClassees = porteNonClassees(collections.value, categories.value)
  return [...portes(collections.value, categories.value), ...(nonClassees ? [nonClassees] : [])]
})

async function autreIdee () {
  tirage.value = true
  try {
    const r = await get('/api/accueil/exemple', exemple.value ? { sauf: exemple.value.name } : undefined)
    if (r.exemple) {
      exemple.value = r.exemple
    }
  }
  catch {}
  tirage.value = false
}

onMounted(() => {
  autreIdee()
  get('/api/accueil/mes-collections')
    .then((r) => {
      bilan.value = r
    })
    .catch(() => {})
    .finally(() => {
      bilanCharge.value = true
    })
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
    <div class="fr-mb-5w">
      <h1>Que souhaitez-vous faire ?</h1>
      <p
        class="fr-text--lead fr-mb-0"
        style="max-width:48rem"
      >
        Interrogez les données de votre ministère en langage courant, ou constituez les vôtres.
        Pas besoin d'être spécialiste : déposez vos documents, l'assistant s'occupe du reste.
      </p>
    </div>

    <!-- Quatre tuiles (refonte du 2026-10-19) : ce qu'elles disent vient de utils/accueil.ts (testé).
         Chaque bloc tombe seul : une panne d'un appel ne vide jamais la page. -->
    <ul
      class="accueil-tuiles fr-grid-row fr-grid-row--gutters fr-mb-6w"
      role="list"
    >
      <li
        v-for="t in tuiles"
        :key="t.cle"
        class="fr-col-12 fr-col-md-6 fr-col-xl-3"
      >
        <div
          class="fr-tile fr-tile--vertical accueil-tuile"
          :class="{ 'fr-enlarge-link': t.cle !== 'decouvrir' }"
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

              <!-- Découvrir : la question d'exemple, à essayer en un geste. -->
              <div
                v-if="t.cle === 'decouvrir' && exemple"
                class="accueil-exemple"
                aria-live="polite"
              >
                <p class="fr-text--xs fr-mb-0 accueil-exemple__collection">
                  {{ exemple.titre }}
                </p>
                <p class="fr-text--sm fr-mb-0">
                  « {{ exemple.question }} »
                </p>
              </div>

              <dl
                v-if="t.kpis.length"
                class="accueil-kpis"
              >
                <div
                  v-for="k in t.kpis"
                  :key="k.libelle"
                  class="accueil-kpi"
                  :class="{ 'accueil-kpi--alerte': k.alerte }"
                >
                  <dt class="fr-sr-only">
                    {{ k.libelle }}
                  </dt>
                  <dd><b>{{ nombre(k.valeur) }}</b><span aria-hidden="true">{{ k.libelle }}</span></dd>
                </div>
              </dl>
              <p
                v-else-if="t.cle === 'gerer' && bilanCharge"
                class="fr-text--sm fr-mb-0 accueil-mention"
              >
                Vous ne gérez pas encore de collection.
              </p>
              <p
                v-if="t.mention"
                class="fr-text--sm fr-mb-0 accueil-mention accueil-mention--forte"
              >
                {{ t.mention }}
              </p>

              <div
                v-if="t.cle === 'decouvrir'"
                class="fr-btns-group fr-btns-group--inline-sm fr-btns-group--sm fr-mt-1w accueil-actions"
              >
                <NuxtLink
                  :to="t.vers"
                  class="fr-btn fr-btn--sm"
                >
                  {{ t.action }}
                </NuxtLink>
                <button
                  v-if="exemple?.autres"
                  type="button"
                  class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-btn--icon-left fr-icon-refresh-line"
                  :disabled="tirage"
                  @click="autreIdee"
                >
                  Une autre idée
                </button>
              </div>
              <p
                v-else
                class="fr-tile__detail accueil-action"
              >
                {{ t.action }}
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

    <!-- Les portes d'entrée du catalogue : une puce par catégorie non vide, puis les non classées. -->
    <section
      v-if="puces.length"
      aria-labelledby="titre-categories"
    >
      <h2
        id="titre-categories"
        class="fr-h4"
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
            class="fr-tag"
          >
            {{ p.libelle }}&nbsp;<span class="accueil-puce__nb">{{ p.nb }}</span>
          </NuxtLink>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.accueil-tuiles { list-style: none; padding: 0; }
.accueil-tuile { height: 100%; text-align: left; }
.accueil-tuile .fr-tile__content { display: flex; flex-direction: column; gap: .75rem; }
.accueil-exemple { padding: .5rem .75rem; background: var(--background-alt-blue-france); }
.accueil-exemple__collection { color: var(--text-mention-grey); }
.accueil-kpis { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; margin: 0; }
.accueil-kpi dd { margin: 0; display: flex; flex-direction: column; }
.accueil-kpi b { font-size: 1.5rem; line-height: 1.2; color: var(--text-title-blue-france); font-variant-numeric: tabular-nums; }
.accueil-kpi span { font-size: .8rem; line-height: 1.3; color: var(--text-mention-grey); }
.accueil-kpi--alerte b { color: var(--text-default-warning); }
.accueil-mention { color: var(--text-mention-grey); }
.accueil-mention--forte { color: var(--text-default-success); font-weight: 500; }
.accueil-action { margin-top: auto; color: var(--text-action-high-blue-france); font-weight: 500; }
.accueil-actions { margin-top: auto; }
.accueil-puce__nb { color: var(--text-mention-grey); font-variant-numeric: tabular-nums; }
</style>
