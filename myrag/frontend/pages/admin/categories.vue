<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Catégories</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Catégories du catalogue</h1>
    <p class="fr-text--sm fr-mb-3w" style="max-width:70ch">
      Une collection appartient à <strong>une seule</strong> catégorie, ou à aucune (« {{ NON_CLASSEES }} »).
      Ce que vous réglez ici s'applique tout de suite au catalogue et à l'accueil, pour tout le monde —
      sans redéploiement.
    </p>

    <div v-if="message" class="fr-alert fr-alert--sm fr-mb-3w" :class="message.ok ? 'fr-alert--success' : 'fr-alert--error'">
      <p>{{ message.texte }}</p>
    </div>

    <div v-if="resyncConseillee" class="fr-callout fr-callout--blue-ecume fr-mb-3w">
      <p class="fr-callout__text fr-text--sm">
        Le catalogue est à jour. <strong>Mon assistant</strong>, lui, montre encore les anciennes étiquettes :
        la catégorie d'une collection y est l'étiquette de son modèle.
      </p>
      <button class="fr-btn fr-btn--sm" :disabled="occupe" @click="resynchroniser">Mettre à jour l'assistant</button>
    </div>

    <!-- ─── Les catégories ─────────────────────────────────────────────────── -->
    <h2 class="fr-h5">Les catégories</h2>
    <div class="fr-table fr-mb-2w">
      <table>
        <thead>
          <tr>
            <th style="width:6rem;">Ordre</th>
            <th>Libellé</th>
            <th>Description</th>
            <th>Collections</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(cat, i) in categories" :key="cat.cle">
            <td>
              <button class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-arrow-up-line"
                      :disabled="i === 0 || occupe" :title="`Monter « ${cat.libelle} »`" @click="deplacer(i, -1)">
                Monter
              </button>
              <button class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-arrow-down-line"
                      :disabled="i === categories.length - 1 || occupe" :title="`Descendre « ${cat.libelle} »`" @click="deplacer(i, 1)">
                Descendre
              </button>
            </td>
            <td>
              <template v-if="edition?.cle === cat.cle">
                <label class="fr-sr-only" :for="`lib-${cat.cle}`">Libellé</label>
                <input :id="`lib-${cat.cle}`" v-model="edition.libelle" class="fr-input" type="text" maxlength="120" />
              </template>
              <template v-else>
                <strong>{{ cat.libelle }}</strong><br />
                <code class="fr-text--xs" style="color:var(--text-mention-grey);">{{ cat.cle }}</code>
              </template>
            </td>
            <td>
              <template v-if="edition?.cle === cat.cle">
                <label class="fr-sr-only" :for="`desc-${cat.cle}`">Description</label>
                <input :id="`desc-${cat.cle}`" v-model="edition.description" class="fr-input" type="text" maxlength="500" />
              </template>
              <span v-else class="fr-text--sm">{{ cat.description || '—' }}</span>
            </td>
            <td>{{ cat.nb_collections ?? 0 }}</td>
            <td>
              <div class="fr-btns-group fr-btns-group--sm fr-btns-group--inline fr-btns-group--inline-sm">
                <template v-if="edition?.cle === cat.cle">
                  <button class="fr-btn fr-btn--sm" :disabled="occupe || edition.libelle.trim().length < 2" @click="enregistrerEdition">Enregistrer</button>
                  <button class="fr-btn fr-btn--sm fr-btn--tertiary" @click="edition = null">Annuler</button>
                </template>
                <template v-else>
                  <button class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-edit-line fr-btn--icon-left" :title="`Renommer « ${cat.libelle} »`" @click="editer(cat)">Renommer</button>
                  <button class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-delete-line fr-btn--icon-left" style="color:#ce0500;" :title="`Supprimer « ${cat.libelle} »`" @click="aSupprimer = cat">Supprimer</button>
                </template>
              </div>
            </td>
          </tr>
          <tr v-if="!categories.length">
            <td colspan="5" class="fr-text--sm">Aucune catégorie : tout le catalogue s'affiche sous « {{ NON_CLASSEES }} ».</td>
          </tr>
        </tbody>
      </table>
    </div>

    <form class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom fr-mb-6w" @submit.prevent="creer">
      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-input-group fr-mb-0">
          <label class="fr-label" for="nouveau-libelle">Nouvelle catégorie</label>
          <input id="nouveau-libelle" v-model="nouveau.libelle" class="fr-input" type="text" maxlength="120" placeholder="Ressources humaines" />
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-5">
        <div class="fr-input-group fr-mb-0">
          <label class="fr-label" for="nouvelle-description">Description (facultative)</label>
          <input id="nouvelle-description" v-model="nouveau.description" class="fr-input" type="text" maxlength="500" />
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-3">
        <button class="fr-btn fr-btn--icon-left fr-icon-add-line" type="submit" :disabled="occupe || cleProposee.length < 2">Ajouter</button>
      </div>
      <p v-if="cleProposee" class="fr-col-12 fr-text--xs fr-mb-0" style="color:var(--text-mention-grey);">
        Clé : <code>{{ cleProposee }}</code> — elle ne changera plus, le libellé si.
      </p>
    </form>

    <!-- ─── Le classement des collections ──────────────────────────────────── -->
    <h2 class="fr-h5">Classer les collections</h2>
    <div class="fr-grid-row fr-grid-row--gutters fr-mb-2w">
      <div class="fr-col-12 fr-col-md-6">
        <div class="fr-search-bar" role="search">
          <label class="fr-label" for="recherche-classement">Rechercher une collection</label>
          <input id="recherche-classement" v-model="recherche" class="fr-input" type="search" placeholder="Titre, identifiant, description…" />
          <button class="fr-btn" type="button">Rechercher</button>
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-6" style="display:flex;align-items:center;">
        <div class="fr-checkbox-group fr-checkbox-group--sm">
          <input id="seulement-non-classees" v-model="seulementNonClassees" type="checkbox" />
          <label class="fr-label" for="seulement-non-classees">Seulement les non classées ({{ nbNonClassees }})</label>
        </div>
      </div>
    </div>

    <div class="fr-table">
      <table>
        <thead>
          <tr>
            <th>Collection</th>
            <th>Description</th>
            <th style="width:20rem;">Catégorie</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="col in visibles" :key="col.name" :style="col.name in brouillon ? 'background:var(--background-contrast-info);' : ''">
            <td>
              <NuxtLink :to="`/c/${col.name}`" class="fr-link">{{ titreDe(col) }}</NuxtLink><br />
              <code class="fr-text--xs" style="color:var(--text-mention-grey);">{{ col.name }}</code>
            </td>
            <td class="fr-text--sm">{{ col.description || '—' }}</td>
            <td>
              <label class="fr-sr-only" :for="`cat-${col.name}`">Catégorie de {{ titreDe(col) }}</label>
              <select :id="`cat-${col.name}`" class="fr-select" :value="choix(col)" @change="choisir(col, ($event.target as HTMLSelectElement).value)">
                <option value="">{{ NON_CLASSEES }}</option>
                <option v-for="cat in categories" :key="cat.cle" :value="cat.cle">{{ cat.libelle }}</option>
              </select>
            </td>
          </tr>
          <tr v-if="!visibles.length"><td colspan="3" class="fr-text--sm">Aucune collection à afficher.</td></tr>
        </tbody>
      </table>
    </div>

    <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
      <button class="fr-btn" :disabled="occupe || !nbChangements" @click="enregistrerClassement">
        Enregistrer le classement{{ nbChangements ? ` (${nbChangements})` : '' }}
      </button>
      <button class="fr-btn fr-btn--secondary" :disabled="occupe || !nbChangements" @click="brouillon = {}">Annuler les changements</button>
    </div>

    <!-- Suppression : on dit ce qui arrive aux collections avant de le faire. -->
    <dialog v-if="aSupprimer" open class="fr-modal fr-modal--opened" aria-labelledby="suppr-titre" style="display:block;">
      <div class="fr-container fr-container--fluid fr-container-md">
        <div class="fr-grid-row fr-grid-row--center">
          <div class="fr-col-12 fr-col-md-8 fr-col-lg-6">
            <div class="fr-modal__body">
              <div class="fr-modal__header">
                <button class="fr-btn--close fr-btn" @click="aSupprimer = null">Fermer</button>
              </div>
              <div class="fr-modal__content">
                <h1 id="suppr-titre" class="fr-modal__title">Supprimer « {{ aSupprimer.libelle }} » ?</h1>
                <p v-if="aSupprimer.nb_collections">
                  Ses <strong>{{ aSupprimer.nb_collections }} collection(s)</strong> ne sont pas supprimées :
                  elles repassent sous « {{ NON_CLASSEES }} ».
                </p>
                <p v-else>Aucune collection n'y est classée.</p>
              </div>
              <div class="fr-modal__footer">
                <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-reverse fr-btns-group--inline-lg">
                  <li><button class="fr-btn" style="background:#ce0500;color:#fff;" :disabled="occupe" @click="supprimer">Supprimer la catégorie</button></li>
                  <li><button class="fr-btn fr-btn--secondary" @click="aSupprimer = null">Annuler</button></li>
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
import { NON_CLASSEES, cleDepuisLibelle, filtrerCollections, titreDe } from '~/utils/catalogue'

definePageMeta({ middleware: 'admin-only' })

const { get } = useApi()
const api = useCategories()

const categories = ref<Categorie[]>([])
const collections = ref<Collection[]>([])
const message = ref<{ ok: boolean; texte: string } | null>(null)
const occupe = ref(false)
const resyncConseillee = ref(false)

const nouveau = ref({ libelle: '', description: '' })
const edition = ref<{ cle: string; libelle: string; description: string } | null>(null)
const aSupprimer = ref<Categorie | null>(null)

const recherche = ref('')
const seulementNonClassees = ref(false)
/** Les choix non encore enregistrés : {identifiant de collection: clé, ou '' pour « Non classées »}. */
const brouillon = ref<Record<string, string>>({})

const cleProposee = computed(() => cleDepuisLibelle(nouveau.value.libelle))
const connues = computed(() => new Set(categories.value.map(c => c.cle)))
const nbChangements = computed(() => Object.keys(brouillon.value).length)
const nbNonClassees = computed(() => collections.value.filter(c => !classee(c)).length)
const visibles = computed(() => {
  const base = seulementNonClassees.value
    ? collections.value.filter(c => !classee(c) || c.name in brouillon.value)
    : collections.value
  return filtrerCollections(base, recherche.value)
    .slice()
    .sort((a, b) => titreDe(a).localeCompare(titreDe(b), 'fr', { sensitivity: 'base' }))
})

function classee(c: Collection): boolean {
  return !!c.categorie && connues.value.has(c.categorie)
}
function choix(c: Collection): string {
  return c.name in brouillon.value ? brouillon.value[c.name] : (classee(c) ? (c.categorie as string) : '')
}
function choisir(c: Collection, cle: string) {
  const suite = { ...brouillon.value }
  if (cle === (classee(c) ? c.categorie : '')) delete suite[c.name]
  else suite[c.name] = cle
  brouillon.value = suite
}

function dire(ok: boolean, texte: string) {
  message.value = { ok, texte }
}
function erreur(e: any): string {
  const brut = String(e?.message || e)
  try { return JSON.parse(brut.slice(brut.indexOf('{'))).detail || brut } catch { return brut }
}

async function charger() {
  categories.value = await api.lister()
  // Les orphelines (partition sans fiche) ne peuvent pas être classées : pas de ligne en base.
  collections.value = ((await get('/api/collections')).collections || []).filter((c: Collection) => !c.orphan)
}

async function faire(geste: () => Promise<string>) {
  occupe.value = true
  try {
    const texte = await geste()
    await charger()
    dire(true, texte)
  } catch (e) {
    dire(false, erreur(e))
  } finally {
    occupe.value = false
  }
}

function creer() {
  return faire(async () => {
    const libelle = nouveau.value.libelle.trim()
    await api.creer({ cle: cleProposee.value, libelle, description: nouveau.value.description.trim() })
    nouveau.value = { libelle: '', description: '' }
    return `Catégorie « ${libelle} » ajoutée.`
  })
}

function editer(cat: Categorie) {
  edition.value = { cle: cat.cle, libelle: cat.libelle, description: cat.description || '' }
}
function enregistrerEdition() {
  return faire(async () => {
    const e = edition.value!
    const r = await api.modifier(e.cle, { libelle: e.libelle.trim(), description: e.description.trim() })
    if (r.resync_conseillee) resyncConseillee.value = true
    edition.value = null
    return `Catégorie « ${e.libelle.trim()} » enregistrée.`
  })
}

function supprimer() {
  return faire(async () => {
    const cat = aSupprimer.value!
    const r = await api.supprimer(cat.cle)
    if (r.resync_conseillee) resyncConseillee.value = true
    aSupprimer.value = null
    return `Catégorie « ${cat.libelle} » supprimée — ${r.collections_declassees} collection(s) repassée(s) sous « ${NON_CLASSEES} ».`
  })
}

function deplacer(i: number, pas: number) {
  return faire(async () => {
    const cles = categories.value.map(c => c.cle)
    const [k] = cles.splice(i, 1)
    cles.splice(i + pas, 0, k)
    await api.ordonner(cles)
    return 'Ordre enregistré.'
  })
}

function enregistrerClassement() {
  return faire(async () => {
    const affectations = Object.fromEntries(Object.entries(brouillon.value).map(([n, cle]) => [n, cle || null]))
    const r = await api.affecter(affectations)
    if (r.resync_conseillee) resyncConseillee.value = true
    brouillon.value = {}
    return `${r.changees.length} collection(s) reclassée(s).`
  })
}

function resynchroniser() {
  return faire(async () => {
    const r = await api.resynchroniser()
    resyncConseillee.value = r.echecs.length > 0
    return r.echecs.length
      ? `${r.fiches.length} fiche(s) mise(s) à jour, ${r.echecs.length} en échec : ${r.echecs.map((e: any) => e.collection).join(', ')}.`
      : `${r.fiches.length} fiche(s) de l'assistant mise(s) à jour.`
  })
}

onMounted(async () => {
  try { await charger() } catch (e) { dire(false, erreur(e)) }
})
</script>
