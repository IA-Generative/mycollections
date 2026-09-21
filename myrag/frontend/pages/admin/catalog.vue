<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Catalogue des collections</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Catalogue des collections existantes</h1>
    <p class="fr-text--sm fr-mb-3w">
      Une collection <strong>publiée à tous</strong> s'interroge ici, dans son bac à sable, mais aussi dans
      l'agent conversationnel de MirAI Next et par l'API depuis vos SI — le détail est sur sa fiche.
      <NuxtLink to="/guide/interroger-depuis-vos-si" class="fr-link">Interroger depuis vos SI</NuxtLink>.
    </p>
    <p class="fr-text--lg fr-mb-2w">Avant de creer une collection, verifiez qu'elle n'existe pas deja.</p>

    <div class="fr-callout fr-callout--brown-caramel fr-mb-4w">
      <p class="fr-callout__text">
        <strong>Evitez les doublons.</strong> Dupliquer une collection degrade la qualite du RAG
        (reponses inconsistantes, cout d'indexation double, maintenance multiple).
        Preferez contacter le responsable d'une collection existante pour y contribuer.
      </p>
    </div>

    <!-- Search + toggle -->
    <div class="fr-grid-row fr-grid-row--gutters fr-mb-4w">
      <div class="fr-col-12 fr-col-md-5">
        <div class="fr-search-bar" role="search">
          <label class="fr-label" for="search">Rechercher une collection</label>
          <input class="fr-input" id="search" type="search" v-model="search"
                 placeholder="CESEDA, code civil, documentation technique..." />
          <button class="fr-btn" @click="">Rechercher</button>
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-4">
        <label class="fr-sr-only" for="filtre-categorie">Catégorie</label>
        <select id="filtre-categorie" class="fr-select" v-model="categorieChoisie">
          <option value="">Toutes les catégories</option>
          <option v-for="c in categories" :key="c.cle" :value="c.cle">{{ c.libelle }}</option>
          <option value="__aucune__">{{ NON_CLASSEES }}</option>
        </select>
      </div>
      <div class="fr-col-12 fr-col-md-3" style="display:flex;align-items:flex-end;">
        <div class="fr-toggle">
          <input type="checkbox" class="fr-toggle__input" id="show-archived" v-model="showArchived" @change="loadCollections" />
          <label class="fr-toggle__label" for="show-archived">Afficher les archivees</label>
        </div>
      </div>
    </div>

    <!-- Chargement : sans lui, le tableau vide des premières secondes se lisait « aucune collection ». -->
    <div v-if="chargement && !collections.length" class="catalogue-chargement fr-mb-4w" role="status" aria-live="polite" aria-busy="true">
      <div class="catalogue-chargement__tete">
        <span class="catalogue-chargement__roue" aria-hidden="true"></span>
        <span><strong>Chargement du catalogue…</strong> Les collections et leurs documents sont recensés ; cela peut prendre quelques secondes.</span>
      </div>
      <div class="catalogue-chargement__lignes" aria-hidden="true">
        <div v-for="n in 6" :key="n" class="catalogue-chargement__ligne" :style="{ animationDelay: `${n * 90}ms` }">
          <span style="width:22%"></span><span style="width:38%"></span><span style="width:12%"></span><span style="width:14%"></span>
        </div>
      </div>
    </div>

    <div v-else-if="erreurChargement && !collections.length" class="fr-alert fr-alert--error fr-mb-4w">
      <h3 class="fr-alert__title">Le catalogue n'a pas pu être chargé</h3>
      <p>{{ erreurChargement }}</p>
      <button class="fr-btn fr-btn--sm fr-btn--secondary fr-mt-1w" @click="loadCollections">Réessayer</button>
    </div>

    <div v-else-if="!collections.length" class="fr-callout fr-mb-4w">
      <h3 class="fr-callout__title">Aucune collection pour l'instant</h3>
      <p class="fr-callout__text">Le catalogue est vide : la première collection peut être la vôtre.</p>
      <NuxtLink to="/admin/create" class="fr-btn fr-mt-2w">Créer une collection</NuxtLink>
    </div>

    <!-- Results -->
    <div v-else-if="filtered.length === 0 && search" class="fr-callout fr-mb-4w">
      <h3 class="fr-callout__title">Aucune collection trouvee pour "{{ search }}"</h3>
      <p class="fr-callout__text">Vous pouvez creer une nouvelle collection.</p>
      <NuxtLink to="/admin/create" class="fr-btn fr-mt-2w">Creer une collection</NuxtLink>
    </div>

    <div v-else :aria-busy="chargement">
      <!-- Les catégories sont repliées par défaut : on parcourt les rubriques, on ouvre celle qui intéresse.
           Une recherche ou un filtre de catégorie les déplie, sinon le résultat serait caché. -->
      <div class="catalogue-replis">
        <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-arrow-down-s-line fr-btn--icon-left"
                :disabled="toutOuvert" @click="toutDeplier">Tout déplier</button>
        <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-arrow-up-s-line fr-btn--icon-left"
                :disabled="!ouvertes.size" @click="toutReplier">Tout replier</button>
      </div>
      <div class="fr-table catalogue-table" :class="{ 'catalogue-rechargement': chargement }">
        <table>
          <thead>
            <tr>
              <th>Collection</th>
              <th>Description</th>
              <th>Source</th>
              <th>Etat</th>
              <th>Responsable</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody v-for="groupe in groupes" :key="groupe.cle || '__aucune__'">
            <tr>
              <th colspan="6" scope="colgroup" class="catalogue-categorie">
                <button type="button" class="catalogue-categorie__bascule"
                        :aria-expanded="estOuverte(groupe) ? 'true' : 'false'"
                        @click="basculer(groupe)">
                  <span class="catalogue-categorie__chevron fr-icon-arrow-right-s-line fr-icon--sm"
                        :class="{ 'catalogue-categorie__chevron--ouvert': estOuverte(groupe) }" aria-hidden="true"></span>
                  <span class="fr-icon-folder-2-line fr-icon--sm" aria-hidden="true"></span>
                  {{ groupe.libelle }}
                  <span class="catalogue-categorie__compte">
                    {{ groupe.collections.length }} collection{{ groupe.collections.length > 1 ? 's' : '' }}
                  </span>
                </button>
              </th>
            </tr>
            <tr v-for="col in groupe.collections" v-show="estOuverte(groupe)" :key="col.name" :style="col.archived_at ? 'opacity:0.65;' : ''">
              <td>
                <NuxtLink :to="`/c/${col.name}`" class="fr-link">{{ titreDe(col) }}</NuxtLink>
                <br />
                <code class="fr-text--xs" style="color:var(--text-mention-grey);" title="Identifiant technique : ce que tapent les applications (openrag-…)">{{ col.name }}</code>
              </td>
              <td>{{ col.description || '—' }}</td>
              <td>
                <span class="fr-badge fr-badge--sm">{{ col.source?.type || col.strategy }}</span>
              </td>
              <td>
                <span v-if="col.archived_at" class="fr-badge fr-badge--sm fr-badge--warning">Archivee</span>
                <template v-else>
                  <span class="fr-badge fr-badge--sm" :class="stateBadge(col.publication?.state)">
                    {{ stateLabel(col.publication?.state) }}
                  </span>
                  <span v-for="t in col.publication?.targets || []" :key="t.app"
                        class="fr-badge fr-badge--sm fr-badge--success fr-ml-1v"
                        :title="`Servie dans ${appLabel(t.app)} (${t.model_id})`">
                    {{ appLabel(t.app) }}
                  </span>
                </template>
              </td>
              <td>
                <div v-if="col.contact_name">
                  {{ col.contact_name }}
                  <br v-if="col.contact_email" />
                  <a v-if="col.contact_email" :href="`mailto:${col.contact_email}?subject=Collection : ${titreDe(col)} (${col.name})`"
                     class="fr-link fr-text--sm">
                    {{ col.contact_email }}
                  </a>
                </div>
                <span v-else class="fr-text--sm" style="color:#666;">Non renseigne</span>
              </td>
              <td>
                <div class="fr-btns-group fr-btns-group--sm fr-btns-group--inline fr-btns-group--inline-sm">
                  <button v-if="!col.archived_at"
                          class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-inbox-archive-line fr-btn--icon-left"
                          @click="onArchive(col)">
                    Archiver
                  </button>
                  <button v-else
                          class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-refresh-line fr-btn--icon-left"
                          @click="onUnarchive(col)">
                    Desarchiver
                  </button>
                  <button v-if="col.archived_at"
                          class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-delete-line fr-btn--icon-left"
                          style="color:#ce0500;"
                          @click="askPurge(col)">
                    Purger
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="fr-text--sm fr-mt-2w">
        {{ filtered.length }} collection(s) trouvee(s)
        <template v-if="isAdmin"> — <NuxtLink to="/admin/categories" class="fr-link fr-text--sm">Régler les catégories et le classement</NuxtLink></template>
      </p>
    </div>

    <div class="fr-btns-group fr-mt-4w">
      <NuxtLink to="/admin/create" class="fr-btn">
        Creer une nouvelle collection
      </NuxtLink>
    </div>

    <!-- Purge confirmation modal -->
    <dialog v-if="purgeTarget" open class="fr-modal fr-modal--opened"
            aria-labelledby="purge-title" style="display:block;">
      <div class="fr-container fr-container--fluid fr-container-md">
        <div class="fr-grid-row fr-grid-row--center">
          <div class="fr-col-12 fr-col-md-8 fr-col-lg-6">
            <div class="fr-modal__body">
              <div class="fr-modal__header">
                <button class="fr-btn--close fr-btn" @click="purgeTarget = null">Fermer</button>
              </div>
              <div class="fr-modal__content">
                <h1 id="purge-title" class="fr-modal__title">
                  <span class="fr-icon-warning-fill" aria-hidden="true"></span>
                  Purger definitivement « {{ titreDe(purgeTarget) }} » ?
                </h1>
                <p>Cette action est <strong>irreversible</strong>. Elle supprime :</p>
                <ul>
                  <li>La partition OpenRAG (tous les documents indexes)</li>
                  <li>Les fichiers sources stockes sur disque</li>
                  <li>Toutes les donnees liees (publications, jobs, feedback, evaluations)</li>
                </ul>
                <div class="fr-input-group" :class="purgeError ? 'fr-input-group--error' : ''">
                  <label class="fr-label" for="purge-confirm">
                    Pour confirmer, tapez l'identifiant de la collection : <strong>{{ purgeTarget.name }}</strong>
                  </label>
                  <input class="fr-input" id="purge-confirm" type="text" v-model="purgeConfirm"
                         @keyup.enter="confirmPurge" />
                  <p v-if="purgeError" class="fr-error-text">{{ purgeError }}</p>
                </div>
              </div>
              <div class="fr-modal__footer">
                <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-reverse fr-btns-group--inline-lg">
                  <li>
                    <button class="fr-btn" style="background:#ce0500;color:#fff;" @click="confirmPurge"
                            :disabled="purging">
                      {{ purging ? 'Purge en cours...' : 'Purger definitivement' }}
                    </button>
                  </li>
                  <li>
                    <button class="fr-btn fr-btn--secondary" @click="purgeTarget = null">Annuler</button>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </dialog>
  </div>
</template>

<script setup lang="ts">
import type { Categorie, Collection } from '~/types/collection'
import { NON_CLASSEES, filtrerCollections, grouperParCategorie, titreDe } from '~/utils/catalogue'

const { get, post, del } = useApi()
const { isAdmin } = useAdminAuth()
const { lister: listerCategories } = useCategories()

const collections = ref<Collection[]>([])
const categories = ref<Categorie[]>([])
// Les portes d'entrée de l'accueil arrivent ici avec ?categorie=<clé>.
const categorieChoisie = ref(String(useRoute().query.categorie || ''))
const search = ref('')
const showArchived = ref(false)

const purgeTarget = ref<any | null>(null)
const purgeConfirm = ref('')
const purgeError = ref('')
const purging = ref(false)

const filtered = computed(() => {
  const connues = new Set(categories.value.map(c => c.cle))
  const parRubrique = collections.value.filter((c) => {
    if (!categorieChoisie.value) return true
    if (categorieChoisie.value === '__aucune__') return !c.categorie || !connues.has(c.categorie)
    return c.categorie === categorieChoisie.value
  })
  return filtrerCollections(parRubrique, search.value)
})
const groupes = computed(() => grouperParCategorie(filtered.value, categories.value))

// Catégories dépliées, par clé (« __aucune__ » pour les non classées). Vide au départ : tout est replié.
const ouvertes = ref(new Set<string>())
const cleDe = (g: { cle?: string | null }) => g.cle || '__aucune__'
const estOuverte = (g: { cle?: string | null }) => ouvertes.value.has(cleDe(g))
const toutOuvert = computed(() => groupes.value.length > 0 && groupes.value.every(estOuverte))
function basculer(g: { cle?: string | null }) {
  const suivantes = new Set(ouvertes.value)
  suivantes.has(cleDe(g)) ? suivantes.delete(cleDe(g)) : suivantes.add(cleDe(g))
  ouvertes.value = suivantes
}
function toutDeplier() { ouvertes.value = new Set(groupes.value.map(cleDe)) }
function toutReplier() { ouvertes.value = new Set() }
// Chercher ou filtrer déplie ce qui répond — y compris l'arrivée par ?categorie= depuis l'accueil.
watch([search, categorieChoisie, groupes], () => {
  if (search.value.trim() || categorieChoisie.value) toutDeplier()
}, { immediate: true })

function stateBadge(state: string) {
  return {
    draft: 'fr-badge--info', published: 'fr-badge--success',
    disabled: 'fr-badge--warning', archived: '',
  }[state] || ''
}

function stateLabel(state: string) {
  return { draft: 'Brouillon', published: 'Publie', disabled: 'Desactive', archived: 'Archive' }[state] || 'Brouillon'
}

// Applications dans lesquelles une collection publiee est servie. L'assistant
// est la seule aujourd'hui ; les suivantes (greffon LibreOffice…) s'ajoutent ici.
function appLabel(app: string) {
  return { assistant: 'Assistant' }[app] || app
}

const chargement = ref(true)
const erreurChargement = ref('')

async function loadCollections() {
  chargement.value = true
  erreurChargement.value = ''
  try {
    const data = await get('/api/collections', showArchived.value ? { include_archived: 'true' } : undefined)
    collections.value = data.collections || []
  } catch (e: any) {
    console.error(e)
    erreurChargement.value = e?.message || 'Le service ne répond pas. Réessayez dans un instant.'
  } finally {
    chargement.value = false
  }
}

async function onArchive(col: any) {
  if (!confirm(`Archiver la collection « ${titreDe(col)} » (${col.name}) ? Elle sera depubliee et masquee du catalogue. Reversible.`)) return
  try {
    await post(`/api/collections/${col.name}/archive`)
    await loadCollections()
  } catch (e: any) { alert(`Erreur: ${e.message}`) }
}

async function onUnarchive(col: any) {
  try {
    await post(`/api/collections/${col.name}/unarchive`)
    await loadCollections()
  } catch (e: any) { alert(`Erreur: ${e.message}`) }
}

function askPurge(col: any) {
  purgeTarget.value = col
  purgeConfirm.value = ''
  purgeError.value = ''
}

async function confirmPurge() {
  if (!purgeTarget.value) return
  if (purgeConfirm.value !== purgeTarget.value.name) {
    purgeError.value = 'Le nom saisi ne correspond pas.'
    return
  }
  purging.value = true
  purgeError.value = ''
  try {
    await del(`/api/collections/${purgeTarget.value.name}`)
    purgeTarget.value = null
    await loadCollections()
  } catch (e: any) {
    purgeError.value = e.message
  } finally {
    purging.value = false
  }
}

onMounted(async () => {
  await loadCollections()
  try { categories.value = await listerCategories() } catch (e) { console.error(e) }
})
</script>

<style scoped>
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
.catalogue-table table { width: 100%; min-width: 56rem; table-layout: fixed; }
.catalogue-table thead th:nth-child(1) { width: 22%; } .catalogue-table thead th:nth-child(2) { width: 34%; }
.catalogue-table thead th:nth-child(3) { width: 8%; } .catalogue-table thead th:nth-child(4) { width: 12%; }
.catalogue-table thead th:nth-child(5) { width: 15%; } .catalogue-table thead th:nth-child(6) { width: 9%; }
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
