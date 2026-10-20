<script setup lang="ts">
import type { Categorie, Collection } from '~/types/collection'
import type { CleTri } from '~/utils/catalogue'
import { COLONNES_CATALOGUE, filtrerCollections, grouperParCategorie, ligneCatalogue, NON_CLASSEES, trierCollections, TRIS } from '~/utils/catalogue'
import { entreeEntraide } from '~/utils/navigation'

const { get } = useApi()
const { capacites } = useCapacites()
// « Besoin d'une donnée ? » mène où mène l'entrée Entraide du menu (réseau, sinon demandes).
const entraide = computed(() => entreeEntraide(capacites.value))
const { isAdmin } = useAdminAuth()
const { lister: listerCategories } = useCategories()

const collections = ref<Collection[]>([])
const categories = ref<Categorie[]>([])
// Les portes d'entrée de l'accueil arrivent ici avec ?categorie=<clé>.
const categorieChoisie = ref(String(useRoute().query.categorie || ''))
const search = ref('')
const showArchived = ref(false)
const tri = ref<CleTri>('recente')

const filtered = computed(() => {
  const connues = new Set(categories.value.map(c => c.cle))
  const parRubrique = collections.value.filter((c) => {
    if (!categorieChoisie.value) {
      return true
    }
    if (categorieChoisie.value === '__aucune__') {
      return !c.categorie || !connues.has(c.categorie)
    }
    return c.categorie === categorieChoisie.value
  })
  return filtrerCollections(parRubrique, search.value)
})
const groupes = computed(() => grouperParCategorie(filtered.value, categories.value))
// Le tri s'applique dans chaque catégorie ; une ligne ne porte que du texte (jamais du HTML).
const groupesTries = computed(() => {
  const maintenant = new Date()
  return groupes.value.map((g) => {
    const triees = trierCollections(g.collections, tri.value)
    return { ...g, collections: triees, lignes: triees.map(c => ligneCatalogue(c, maintenant)) }
  })
})
const compte = computed(() => ({
  collections: collections.value.length,
  categories: grouperParCategorie(collections.value, categories.value).length,
}))

// Catégories dépliées, par clé (« __aucune__ » pour les non classées). Vide au départ : tout est replié.
const ouvertes = ref(new Set<string>())
const cleDe = (g: { cle?: string | null }) => g.cle || '__aucune__'
const estOuverte = (g: { cle?: string | null }) => ouvertes.value.has(cleDe(g))
const toutOuvert = computed(() => groupes.value.length > 0 && groupes.value.every(estOuverte))
function basculer (g: { cle?: string | null }) {
  const suivantes = new Set(ouvertes.value)
  if (suivantes.has(cleDe(g))) {
    suivantes.delete(cleDe(g))
  }
  else {
    suivantes.add(cleDe(g))
  }
  ouvertes.value = suivantes
}
function toutDeplier () {
  ouvertes.value = new Set(groupes.value.map(cleDe))
}
function toutReplier () {
  ouvertes.value = new Set()
}
// Chercher ou filtrer déplie ce qui répond — y compris l'arrivée par ?categorie= depuis l'accueil.
watch([search, categorieChoisie, groupes], () => {
  if (search.value.trim() || categorieChoisie.value) {
    toutDeplier()
  }
}, { immediate: true })

const chargement = ref(true)
const erreurChargement = ref('')

async function loadCollections () {
  chargement.value = true
  erreurChargement.value = ''
  try {
    const data = await get('/api/collections', showArchived.value ? { include_archived: 'true' } : undefined)
    collections.value = data.collections || []
  }
  catch (e: any) {
    console.error(e)
    erreurChargement.value = messageErreur(e)
  }
  finally {
    chargement.value = false
  }
}

onMounted(async () => {
  await loadCollections()
  try {
    categories.value = await listerCategories()
  }
  catch (e) {
    console.error(e)
  }
})
</script>

<template>
  <div>
    <!-- Pas de fil d'Ariane : le menu dit déjà où l'on est. -->
    <div class="catalogue-tete fr-mb-2w">
      <div>
        <h1 class="fr-h3 fr-mb-0">
          Catalogue des collections
        </h1>
        <p
          v-if="!chargement || collections.length"
          class="fr-text--sm fr-mb-0 catalogue-tete__compte"
        >
          {{ compte.collections }} collection{{ compte.collections > 1 ? 's' : '' }} · {{ compte.categories }} catégorie{{ compte.categories > 1 ? 's' : '' }}
        </p>
      </div>
      <p
        v-if="entraide"
        class="fr-text--sm fr-mb-0 catalogue-tete__entraide"
      >
        <span
          class="fr-icon-team-line fr-icon--sm fr-mr-1v"
          aria-hidden="true"
        /><strong>Besoin d'une donnée ?</strong>
        <NuxtLink
          :to="entraide.vers"
          class="fr-link fr-text--sm"
        >
          Demandez au réseau
        </NuxtLink>
      </p>
    </div>

    <!-- Les filtres : recherche, catégorie, tri, archivées. -->
    <form
      class="catalogue-filtres fr-background-alt--grey fr-px-2w fr-py-1w fr-mb-2w"
      role="search"
      aria-label="Filtrer le catalogue"
      @submit.prevent
    >
      <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
        <div class="fr-col-12 fr-col-lg-5">
          <div class="fr-search-bar">
            <label
              class="fr-label"
              for="search"
            >Rechercher</label>
            <input
              id="search"
              v-model="search"
              class="fr-input"
              type="search"
              placeholder="CESEDA, code civil, documentation technique…"
            >
            <button
              class="fr-btn"
              type="submit"
              title="Rechercher"
            >
              Rechercher
            </button>
          </div>
        </div>
        <div class="fr-col-12 fr-col-md-4 fr-col-lg-3">
          <div class="fr-select-group fr-mb-0">
            <label
              class="fr-label"
              for="filtre-categorie"
            >Catégorie</label>
            <select
              id="filtre-categorie"
              v-model="categorieChoisie"
              class="fr-select"
            >
              <option value="">
                Toutes les catégories
              </option>
              <option
                v-for="c in categories"
                :key="c.cle"
                :value="c.cle"
              >
                {{ c.libelle }}
              </option>
              <option value="__aucune__">
                {{ NON_CLASSEES }}
              </option>
            </select>
          </div>
        </div>
        <div class="fr-col-12 fr-col-md-4 fr-col-lg-2">
          <div class="fr-select-group fr-mb-0">
            <label
              class="fr-label"
              for="tri"
            >Trier par</label>
            <select
              id="tri"
              v-model="tri"
              class="fr-select"
            >
              <option
                v-for="t in TRIS"
                :key="t.cle"
                :value="t.cle"
              >
                {{ t.libelle }}
              </option>
            </select>
          </div>
        </div>
        <div class="fr-col-12 fr-col-md-4 fr-col-lg-2">
          <div class="fr-checkbox-group fr-checkbox-group--sm">
            <input
              id="show-archived"
              v-model="showArchived"
              type="checkbox"
              @change="loadCollections"
            >
            <label
              class="fr-label"
              for="show-archived"
            >Afficher les archivées</label>
          </div>
        </div>
      </div>
    </form>

    <!-- Chargement : sans lui, le tableau vide des premières secondes se lisait « aucune collection ». -->
    <div
      v-if="chargement && !collections.length"
      class="catalogue-chargement fr-mb-4w"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div class="catalogue-chargement__tete">
        <span
          class="catalogue-chargement__roue"
          aria-hidden="true"
        />
        <span><strong>Chargement du catalogue…</strong> Les collections et leurs documents sont recensés ; cela peut prendre quelques secondes.</span>
      </div>
      <div
        class="catalogue-chargement__lignes"
        aria-hidden="true"
      >
        <div
          v-for="n in 6"
          :key="n"
          class="catalogue-chargement__ligne"
          :style="{ animationDelay: `${n * 90}ms` }"
        >
          <span style="width:22%" /><span style="width:38%" /><span style="width:12%" /><span style="width:14%" />
        </div>
      </div>
    </div>

    <div
      v-else-if="erreurChargement && !collections.length"
      class="fr-alert fr-alert--error fr-mb-4w"
    >
      <h2 class="fr-alert__title">
        Le catalogue n'a pas pu être chargé
      </h2>
      <p>{{ erreurChargement }}</p>
      <button
        class="fr-btn fr-btn--sm fr-btn--secondary fr-mt-1w"
        @click="loadCollections"
      >
        Réessayer
      </button>
    </div>

    <div
      v-else-if="!collections.length"
      class="fr-callout fr-mb-4w"
    >
      <h2 class="fr-callout__title">
        Aucune collection pour l'instant
      </h2>
      <p class="fr-callout__text">
        Le catalogue est vide : la première collection peut être la vôtre.
      </p>
      <NuxtLink
        to="/admin/create"
        class="fr-btn fr-mt-2w"
      >
        Créer une collection
      </NuxtLink>
    </div>

    <div
      v-else-if="filtered.length === 0"
      class="fr-callout fr-mb-4w"
    >
      <h2 class="fr-callout__title">
        Aucune collection ne correspond à votre recherche
      </h2>
      <p class="fr-callout__text">
        Essayez un autre mot, ou une autre catégorie.
      </p>
    </div>

    <div
      v-else
      :aria-busy="chargement"
    >
      <!-- Les catégories sont repliées par défaut : on parcourt les rubriques, on ouvre celle qui intéresse.
           Une recherche ou un filtre de catégorie les déplie, sinon le résultat serait caché. -->
      <div class="catalogue-replis">
        <button
          type="button"
          class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-arrow-down-s-line fr-btn--icon-left"
          :disabled="toutOuvert"
          @click="toutDeplier"
        >
          Tout déplier
        </button>
        <button
          type="button"
          class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-arrow-up-s-line fr-btn--icon-left"
          :disabled="!ouvertes.size"
          @click="toutReplier"
        >
          Tout replier
        </button>
      </div>
      <div
        class="fr-table catalogue-table"
        :class="{ 'catalogue-rechargement': chargement }"
      >
        <table>
          <caption class="fr-sr-only">
            Catalogue des collections, par catégorie
          </caption>
          <thead>
            <tr>
              <th
                v-for="col in COLONNES_CATALOGUE"
                :key="col"
                scope="col"
              >
                {{ col }}
              </th>
            </tr>
          </thead>
          <tbody
            v-for="groupe in groupesTries"
            :key="groupe.cle || '__aucune__'"
          >
            <tr>
              <th
                :colspan="COLONNES_CATALOGUE.length"
                scope="colgroup"
                class="catalogue-categorie"
              >
                <button
                  type="button"
                  class="catalogue-categorie__bascule"
                  :aria-expanded="estOuverte(groupe) ? 'true' : 'false'"
                  @click="basculer(groupe)"
                >
                  <span
                    class="catalogue-categorie__chevron fr-icon-arrow-right-s-line fr-icon--sm"
                    :class="{ 'catalogue-categorie__chevron--ouvert': estOuverte(groupe) }"
                    aria-hidden="true"
                  />
                  <span
                    class="fr-icon-folder-2-line fr-icon--sm"
                    aria-hidden="true"
                  />
                  {{ groupe.libelle }}
                  <span class="catalogue-categorie__compte">
                    {{ groupe.collections.length }} collection{{ groupe.collections.length > 1 ? 's' : '' }}
                  </span>
                </button>
              </th>
            </tr>
            <tr
              v-for="l in groupe.lignes"
              v-show="estOuverte(groupe)"
              :key="l.name"
              :class="{ 'catalogue-ligne--archivee': l.etat.libelle === 'Archivée' }"
            >
              <td>
                <NuxtLink
                  :to="`/c/${l.name}`"
                  class="fr-link"
                >
                  {{ l.titre }}
                </NuxtLink>
                <br>
                <code
                  class="fr-text--xs catalogue-mention"
                  title="Identifiant technique : ce que tapent les applications (openrag-…)"
                >{{ l.name }}</code>
                <p
                  v-if="l.description"
                  class="fr-text--sm fr-mb-0 fr-mt-1v"
                >
                  {{ l.description }}
                </p>
              </td>
              <td>
                <span
                  class="fr-badge fr-badge--sm fr-badge--no-icon"
                  :class="l.etat.classe"
                >{{ l.etat.libelle }}</span>
              </td>
              <td class="catalogue-date">
                {{ l.creeeLe }}
              </td>
              <td class="catalogue-date">
                {{ l.miseAJour.date }}
                <span
                  v-if="l.miseAJour.ilYa"
                  class="fr-text--xs catalogue-mention catalogue-date__depuis"
                >{{ l.miseAJour.ilYa }}</span>
              </td>
              <td>
                <template v-if="l.avis.taux">
                  <strong>{{ l.avis.taux }}</strong>
                  <span class="fr-text--xs catalogue-mention catalogue-date__depuis">{{ l.avis.detail }}</span>
                </template>
                <span
                  v-else
                  class="fr-text--sm catalogue-mention"
                >{{ l.avis.detail }}</span>
              </td>
              <td>
                <template v-if="l.responsable.nom || l.responsable.courriel">
                  {{ l.responsable.nom }}
                  <br v-if="l.responsable.nom && l.responsable.courriel">
                  <a
                    v-if="l.responsable.courriel"
                    :href="`mailto:${l.responsable.courriel}?subject=${encodeURIComponent(`Collection : ${l.titre} (${l.name})`)}`"
                    class="fr-link fr-text--sm"
                  >
                    {{ l.responsable.courriel }}
                  </a>
                </template>
                <span
                  v-else
                  class="fr-text--sm catalogue-mention"
                >Non renseigné</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p
        v-if="isAdmin"
        class="fr-text--sm fr-mt-2w"
      >
        <NuxtLink
          to="/admin/categories"
          class="fr-link fr-text--sm"
        >
          Régler les catégories et le classement
        </NuxtLink>
      </p>
    </div>

    <p class="fr-text--sm fr-mt-3w catalogue-mention">
      Une collection manque ? Contactez d'abord son responsable : compléter une collection vaut mieux que la dupliquer.
    </p>
  </div>
</template>

<style scoped>
.catalogue-tete { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: .5rem 1.5rem; }
.catalogue-tete__entraide { padding: .5rem .75rem; background: var(--background-alt-blue-france); }
.catalogue-tete__compte, .catalogue-mention { color: var(--text-mention-grey); }
.catalogue-date { white-space: nowrap; }
.catalogue-date__depuis { display: block; }
.catalogue-ligne--archivee { opacity: .65; }
/* Le bandeau de catégorie : les lignes du tableau DSFR sont zébrées de gris, un intertitre gris s'y perdait.
   Bleu France léger + filet à gauche, et de l'air au-dessus pour séparer les groupes. */
.fr-table tbody th.catalogue-categorie { background: var(--background-action-low-blue-france) !important;
  color: var(--text-title-blue-france); box-shadow: inset 4px 0 0 var(--border-action-high-blue-france);
  text-align: left; font-size: 1rem; font-weight: 700; padding-top: .75rem; padding-bottom: .75rem; }
tbody + tbody th.catalogue-categorie { border-top: .75rem solid var(--background-default-grey); }
.catalogue-categorie__bascule { display: flex; align-items: center; gap: .4rem; width: 100%; margin: 0; padding: 0;
  background: none; border: 0; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.catalogue-categorie__bascule:hover, .catalogue-categorie__bascule:active { background: none !important; text-decoration: underline; }
/* Largeurs fixes : sans elles, replier une catégorie resserrait les colonnes et le tableau sautait. */
.catalogue-table { overflow-x: auto; }
.catalogue-table table { width: 100%; min-width: 56rem; table-layout: fixed; }
.catalogue-table thead th:nth-child(1) { width: 36%; } .catalogue-table thead th:nth-child(2) { width: 10%; }
.catalogue-table thead th:nth-child(3) { width: 11%; } .catalogue-table thead th:nth-child(4) { width: 12%; }
.catalogue-table thead th:nth-child(5) { width: 11%; } .catalogue-table thead th:nth-child(6) { width: 20%; }
.catalogue-table td { overflow-wrap: anywhere; }
.catalogue-categorie__chevron { transition: transform .15s; }
.catalogue-categorie__chevron--ouvert { transform: rotate(90deg); }
.catalogue-replis { display: flex; justify-content: flex-end; gap: .5rem; margin-bottom: .5rem; }
@media (prefers-reduced-motion: reduce) { .catalogue-categorie__chevron { transition: none; } }
.catalogue-categorie__compte { margin-left: .5rem; padding: 0 .5rem; border-radius: 1rem; font-size: .75rem; font-weight: 500;
  background: var(--background-default-grey); color: var(--text-mention-grey); vertical-align: middle; }
.catalogue-chargement { border: 1px solid var(--border-default-grey); padding: 1.25rem 1.5rem; }
.catalogue-chargement__tete { display: flex; align-items: center; gap: .9rem; margin-bottom: 1.1rem; }
.catalogue-chargement__roue { flex: 0 0 auto; width: 1.6rem; height: 1.6rem; border-radius: 50%;
  border: 3px solid var(--border-default-grey); border-top-color: var(--border-active-blue-france); animation: catalogue-tour .8s linear infinite; }
.catalogue-chargement__lignes { display: flex; flex-direction: column; gap: .7rem; }
.catalogue-chargement__ligne { display: flex; gap: 1.2rem; animation: catalogue-pulse 1.4s ease-in-out infinite; }
.catalogue-chargement__ligne span { height: .85rem; border-radius: 3px; background: var(--background-contrast-grey); }
/* Un rechargement (bascule « archivées ») garde le tableau, estompé : rien ne saute. */
.catalogue-rechargement { opacity: .5; transition: opacity .2s; pointer-events: none; }
@keyframes catalogue-tour { to { transform: rotate(360deg); } }
@keyframes catalogue-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
@media (prefers-reduced-motion: reduce) {
  .catalogue-chargement__roue { animation-duration: 2.4s; }
  .catalogue-chargement__ligne { animation: none; }
}
</style>
