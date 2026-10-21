<script setup lang="ts">
import type { Categorie, Collection } from '~/types/collection'
import type { ConnecteurDeclare, FormulaireAssistant, Regime } from '~/utils/assistants'
import { etiquetteSource, ficheDepuisFormulaire, REGIMES, validerFormulaire } from '~/utils/assistants'
import { titreDe } from '~/utils/catalogue'
import { deriverIdentifiant } from '~/utils/collectionName'

/**
 * Créer un assistant (B1) : un titre, une description, une catégorie, et les collections qu'il
 * interroge, avec pour chacune QUAND il l'interroge. Seules les collections que vous gérez peuvent
 * être réunies (le serveur le vérifie de toute façon). Les consignes viennent ensuite (B2).
 */
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
useHead({ title: 'Créer un assistant — Mes collections' })

const { get } = useApi()
const { lister, enregistrer, connecteurs: listerConnecteurs } = useAssistants()
const { lister: listerCategories } = useCategories()

const form = ref<FormulaireAssistant>({ titre: '', identifiant: '', description: '', rubrique: '', sources: [] })
const identifiantManuel = ref(false)
const collections = ref<Collection[]>([])
const connecteurs = ref<ConnecteurDeclare[]>([])
const categories = ref<Categorie[]>([])
const pris = ref(new Set<string>())
const filtre = ref('')
const envoi = ref(false)
const erreurServeur = ref('')
const tente = ref(false)

/** Les collections que je peux réunir : celles que je gère, ni archivées ni orphelines. */
const gerables = computed(() => collections.value
  .filter(c => c.mes_droits?.ecrire && !c.orphan && !c.archived_at)
  .filter(c => !filtre.value.trim() || `${titreDe(c)} ${c.name}`.toLowerCase().includes(filtre.value.trim().toLowerCase())))
/** Les référentiels déclarés : ils ne retiennent personne, tout le monde peut les réunir. */
const referentiels = computed(() => connecteurs.value
  .filter(k => !filtre.value.trim() || `${k.titre} ${k.id}`.toLowerCase().includes(filtre.value.trim().toLowerCase())))
const choisie = (id: string) => form.value.sources.find(s => s.id === id)
const erreurs = computed(() => validerFormulaire(form.value))

function proposer () {
  if (identifiantManuel.value) {
    return
  }
  const base = deriverIdentifiant(form.value.titre, 60)
  let candidat = base
  for (let n = 2; pris.value.has(candidat) && n < 100; n++) {
    candidat = `${base}-${n}`
  }
  form.value.identifiant = candidat
}

function basculer (c: Collection) {
  const i = form.value.sources.findIndex(s => s.id === c.name)
  if (i >= 0) {
    form.value.sources.splice(i, 1)
  }
  else {
    form.value.sources.push({ id: c.name, regime: 'selon_question' })
  }
}

function basculerConnecteur (k: ConnecteurDeclare) {
  const i = form.value.sources.findIndex(s => s.id === k.id)
  if (i >= 0) {
    form.value.sources.splice(i, 1)
  }
  else {
    form.value.sources.push({ id: k.id, type: 'connecteur', regime: 'selon_question' })
  }
}

function regime (id: string, r: string) {
  const s = choisie(id)
  if (s) {
    s.regime = r as Regime
  }
}

async function creer () {
  tente.value = true
  erreurServeur.value = ''
  if (Object.keys(erreurs.value).length) {
    return
  }
  envoi.value = true
  try {
    await enregistrer(ficheDepuisFormulaire(form.value))
    await navigateTo(`/assistants/${encodeURIComponent(form.value.identifiant)}/sources`)
  }
  catch (e) {
    erreurServeur.value = messageErreur(e)
  }
  finally {
    envoi.value = false
  }
}

onMounted(async () => {
  const [cols, cats, existants, refs] = await Promise.allSettled([get('/api/collections'), listerCategories(), lister(), listerConnecteurs()])
  if (refs.status === 'fulfilled') {
    connecteurs.value = refs.value
  }
  if (cols.status === 'fulfilled') {
    collections.value = cols.value.collections || []
  }
  if (cats.status === 'fulfilled') {
    categories.value = cats.value
  }
  if (existants.status === 'fulfilled') {
    pris.value = new Set(existants.value.map((a: { id: string }) => a.id))
  }
})
</script>

<template>
  <div>
    <p class="fr-text--sm fr-mb-0">
      <NuxtLink
        to="/assistants"
        class="fr-link fr-text--sm fr-icon-arrow-left-line fr-link--icon-left"
      >
        Assistants de recherche
      </NuxtLink>
    </p>
    <h1 class="fr-h3 fr-mb-1v">
      Créer un assistant
    </h1>
    <p class="fr-mb-3w nouveau-discret">
      Un assistant ne contient pas de documents : il interroge les collections que vous choisissez ici. Vous écrirez ensuite
      ses consignes : quand chercher où, et comment répondre.
    </p>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-12 fr-col-lg-8">
        <div
          class="fr-input-group"
          :class="{ 'fr-input-group--error': tente && erreurs.titre }"
        >
          <label
            class="fr-label"
            for="titre"
          >Titre de l'assistant *
            <span class="fr-hint-text">Ce que liront vos collègues dans Mon assistant.</span>
          </label>
          <input
            id="titre"
            v-model="form.titre"
            class="fr-input"
            maxlength="255"
            placeholder="Ex. : Séjour des étrangers"
            @input="proposer"
          >
          <p
            v-if="tente && erreurs.titre"
            class="fr-error-text"
          >
            {{ erreurs.titre }}
          </p>
        </div>

        <div
          class="fr-input-group"
          :class="{ 'fr-input-group--error': tente && erreurs.identifiant }"
        >
          <label
            class="fr-label"
            for="identifiant"
          >Identifiant
            <span class="fr-hint-text">Proposé d'après le titre ; c'est ce que taperont les applications.</span>
          </label>
          <input
            id="identifiant"
            v-model="form.identifiant"
            class="fr-input"
            :readonly="!identifiantManuel"
            @input="identifiantManuel = true"
          >
          <button
            v-if="!identifiantManuel"
            type="button"
            class="fr-link fr-text--xs fr-mt-1v"
            @click="identifiantManuel = true"
          >
            Le choisir moi-même
          </button>
          <p
            v-if="tente && erreurs.identifiant"
            class="fr-error-text"
          >
            {{ erreurs.identifiant }}
          </p>
        </div>

        <div class="fr-input-group">
          <label
            class="fr-label"
            for="description"
          >Description
            <span class="fr-hint-text">À quoi il sert, quelles questions lui poser.</span>
          </label>
          <textarea
            id="description"
            v-model="form.description"
            class="fr-input"
            rows="2"
            maxlength="2000"
          />
        </div>

        <div class="fr-select-group">
          <label
            class="fr-label"
            for="rubrique"
          >Catégorie</label>
          <select
            id="rubrique"
            v-model="form.rubrique"
            class="fr-select"
          >
            <option value="">
              Non classé
            </option>
            <option
              v-for="c in categories"
              :key="c.cle"
              :value="c.cle"
            >
              {{ c.libelle }}
            </option>
          </select>
        </div>

        <fieldset
          class="fr-fieldset nouveau-sources"
          :class="{ 'fr-fieldset--error': tente && erreurs.sources }"
          aria-labelledby="titre-sources"
        >
          <legend
            id="titre-sources"
            class="fr-fieldset__legend"
          >
            Les sources qu'il interroge *
            <span class="fr-hint-text">Les collections que vous gérez, et les référentiels proposés. Pour chacune, dites quand l'assistant l'interroge.</span>
          </legend>
          <div class="fr-fieldset__element">
            <div class="fr-input-group fr-mb-1w">
              <label
                class="fr-label fr-sr-only"
                for="filtre"
              >Filtrer les collections</label>
              <input
                id="filtre"
                v-model="filtre"
                class="fr-input"
                type="search"
                placeholder="Filtrer les collections…"
              >
            </div>
          </div>
          <div
            v-for="c in gerables"
            :key="c.name"
            class="fr-fieldset__element nouveau-source"
          >
            <div class="fr-checkbox-group">
              <input
                :id="`src-${c.name}`"
                type="checkbox"
                :checked="!!choisie(c.name)"
                @change="basculer(c)"
              >
              <label
                class="fr-label"
                :for="`src-${c.name}`"
              >{{ titreDe(c) }}
                <span class="fr-hint-text">{{ c.description || c.name }}</span>
              </label>
            </div>
            <select
              v-if="choisie(c.name)"
              class="fr-select nouveau-regime"
              :aria-label="`Quand interroger ${titreDe(c)}`"
              :value="choisie(c.name)!.regime"
              @change="regime(c.name, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-for="r in REGIMES"
                :key="r.cle"
                :value="r.cle"
              >
                {{ r.libelle }}
              </option>
            </select>
          </div>
          <div
            v-for="k in referentiels"
            :key="k.id"
            class="fr-fieldset__element nouveau-source"
          >
            <div class="fr-checkbox-group">
              <input
                :id="`src-${k.id}`"
                type="checkbox"
                :checked="!!choisie(k.id)"
                @change="basculerConnecteur(k)"
              >
              <label
                class="fr-label"
                :for="`src-${k.id}`"
              >{{ k.titre }}
                <span class="fr-badge fr-badge--sm fr-badge--info fr-badge--no-icon fr-ml-1w">{{ etiquetteSource(k.type) }}</span>
                <span class="fr-hint-text">{{ k.description || k.id }}</span>
              </label>
            </div>
            <select
              v-if="choisie(k.id)"
              class="fr-select nouveau-regime"
              :aria-label="`Quand interroger ${k.titre}`"
              :value="choisie(k.id)!.regime"
              @change="regime(k.id, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-for="r in REGIMES"
                :key="r.cle"
                :value="r.cle"
              >
                {{ r.libelle }}
              </option>
            </select>
          </div>
          <p
            v-if="!gerables.length && !referentiels.length"
            class="fr-text--sm nouveau-discret fr-ml-1w"
          >
            {{ filtre ? 'Aucune collection ne correspond.' : 'Vous ne gérez encore aucune collection : créez-en une d\'abord.' }}
          </p>
          <p
            v-if="tente && erreurs.sources"
            class="fr-error-text fr-ml-1w"
          >
            {{ erreurs.sources }}
          </p>
        </fieldset>

        <div
          v-if="erreurServeur"
          class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
          role="alert"
        >
          <p>{{ erreurServeur }}</p>
        </div>
        <ul class="fr-btns-group fr-btns-group--inline-md">
          <li>
            <button
              type="button"
              class="fr-btn"
              :disabled="envoi"
              @click="creer"
            >
              {{ envoi ? 'Création…' : 'Créer l\'assistant' }}
            </button>
          </li>
          <li>
            <NuxtLink
              to="/assistants"
              class="fr-btn fr-btn--tertiary-no-outline"
            >
              Annuler
            </NuxtLink>
          </li>
        </ul>
      </div>

      <div class="fr-col-12 fr-col-lg-4">
        <div class="fr-callout">
          <h2 class="fr-callout__title fr-h6">
            Quand interroger une collection ?
          </h2>
          <ul class="fr-callout__text fr-text--sm">
            <li
              v-for="r in REGIMES"
              :key="r.cle"
            >
              <strong>{{ r.libelle }} :</strong> {{ r.aide }}
            </li>
          </ul>
          <p class="fr-text--xs fr-mb-0">
            L'assistant ne cite que ce que la personne qui pose la question a le droit de lire.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nouveau-discret { color: var(--text-mention-grey); }
.nouveau-sources { max-height: 26rem; overflow-y: auto; }
.nouveau-source { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem 1rem; }
.nouveau-regime { max-width: 18rem; }
</style>
