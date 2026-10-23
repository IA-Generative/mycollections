<script setup lang="ts">
/**
 * Créer une collection depuis Résana, dans l'ordre où l'on pense (docs/resana.md) : d'abord
 * choisir dans Résana l'espace, le dossier et ce qu'il faut en indexer ; l'outil vérifie qu'aucune
 * de vos collections ne le couvre déjà ; puis la fiche, déjà remplie, à relire ; un clic crée la
 * collection (privée) et lance l'indexation.
 */
import type { ReglesNommage } from '~/utils/collectionName'
import type { ErreurResana, InventaireResana } from '~/utils/resana'
import { isConflictError, motifRefus, REGLES_PAR_DEFAUT } from '~/utils/collectionName'
import { erreurResana, etiquetteResana, ficheDepuisResana, preparation, selection } from '~/utils/resana'
import { identifiantPropose } from '~/utils/wizard'

interface Espace { id: string, nom: string }
interface Dossier { id: string, titre: string, chemin: string }
interface Existante { collection: string, titre: string, dossier_chemin?: string, couverture: string }

const router = useRouter()
const { get, post } = useApi()
const champ = useId()

const phase = ref<'choisir' | 'fiche'>('choisir')
const erreur = ref<ErreurResana | null>(null)

// ─── Choisir dans Résana ─────────────────────────────────────────────────────
const espaces = ref<Espace[]>([])
const espace = ref('')
const dossiers = ref<Dossier[]>([])
const dossier = ref('')
const recherche = ref('')
const chargeEspaces = ref(false)
const chargeDossiers = ref(false)
const inventaire = ref<InventaireResana | null>(null)
const enPreparation = ref<{ dossiers_lus?: number | null, dossiers?: number | null } | null>(null)
const exclus = ref<string[]>([])
const existant = ref<{ meme_dossier: Existante[], dossier_parent: Existante[], sous_dossiers: Existante[] } | null>(null)
let minuterie: ReturnType<typeof setTimeout> | undefined
let rappel: ReturnType<typeof setTimeout> | undefined

const espaceChoisi = computed(() => espaces.value.find(e => e.id === espace.value) || null)
const dossierChoisi = computed(() => dossiers.value.find(d => d.id === dossier.value) || null)
const retenus = computed(() => (inventaire.value ? selection(inventaire.value, new Set(exclus.value)) : null))
const peutContinuer = computed(() => !!dossierChoisi.value && (enPreparation.value !== null || (retenus.value?.documents ?? 0) > 0))

async function chargerEspaces () {
  chargeEspaces.value = true
  erreur.value = null
  try {
    espaces.value = (await get('/api/sources/resana/espaces')).espaces || []
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    chargeEspaces.value = false
  }
}

async function chargerDossiers () {
  clearTimeout(rappel)
  dossier.value = ''
  inventaire.value = null
  enPreparation.value = null
  existant.value = null
  dossiers.value = []
  if (!espace.value) {
    return
  }
  chargeDossiers.value = true
  erreur.value = null
  try {
    const params: Record<string, string> = recherche.value.trim() ? { recherche: recherche.value.trim() } : {}
    dossiers.value = (await get(`/api/sources/resana/espaces/${encodeURIComponent(espace.value)}/dossiers`, params)).dossiers || []
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    chargeDossiers.value = false
  }
}

function chercher () {
  clearTimeout(minuterie)
  minuterie = setTimeout(chargerDossiers, 350)
}

async function choisirDossier () {
  exclus.value = []
  inventaire.value = null
  existant.value = null
  const d = dossierChoisi.value
  if (!d) {
    return
  }
  get('/api/sources/resana/existant', { espace: espace.value, dossier: d.id, chemin: d.chemin })
    .then((r) => {
      existant.value = r
    })
    .catch(() => {})
  await chargerInventaire()
}

async function chargerInventaire () {
  clearTimeout(rappel)
  const demande = dossier.value
  if (!demande) {
    return
  }
  erreur.value = null
  try {
    const r = await get(`/api/sources/resana/espaces/${encodeURIComponent(espace.value)}/inventaire`, { dossier: demande })
    if (demande !== dossier.value) {
      return // un autre dossier a été choisi entre-temps
    }
    if (r.en_preparation) {
      enPreparation.value = r
      rappel = setTimeout(chargerInventaire, 5000)
      return
    }
    enPreparation.value = null
    inventaire.value = r
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
}

// ─── La fiche ────────────────────────────────────────────────────────────────
const titre = ref('')
const description = ref('')
const identifiant = ref('')
const regles = ref<ReglesNommage>(REGLES_PAR_DEFAUT)
const pris = ref(new Set<string>())
const envoi = ref(false)
const creee = ref('')
const erreurFiche = ref('')

function continuer () {
  if (!dossierChoisi.value || !espaceChoisi.value) {
    return
  }
  const f = ficheDepuisResana(dossierChoisi.value, espaceChoisi.value.nom)
  titre.value = f.titre
  description.value = f.description
  identifiant.value = identifiantPropose(f.titre, pris.value, regles.value)
  phase.value = 'fiche'
}

watch(titre, (t) => {
  if (phase.value === 'fiche' && !creee.value) {
    identifiant.value = identifiantPropose(t, pris.value, regles.value)
  }
})

async function creerEtIndexer () {
  if (!dossierChoisi.value || !espaceChoisi.value) {
    return
  }
  envoi.value = true
  erreurFiche.value = ''
  erreur.value = null
  try {
    if (!creee.value) {
      const motif = motifRefus(identifiant.value, regles.value)
      if (!identifiant.value || motif) {
        erreurFiche.value = motif ? (regles.value.motifs[motif] || 'Identifiant refusé.') : 'Donnez un titre à la collection.'
        return
      }
      try {
        await post('/api/collections', {
          name: identifiant.value,
          titre: titre.value.trim(),
          description: description.value.trim(),
          scope: 'private',
          scope_groups: [],
          strategy: 'auto',
        })
      }
      catch (e) {
        if (isConflictError(e)) {
          pris.value = new Set([...pris.value, identifiant.value])
          identifiant.value = identifiantPropose(titre.value, pris.value, regles.value)
          erreurFiche.value = 'Cet identifiant venait d\'être pris : un autre vous est proposé, relancez.'
          return
        }
        throw e
      }
      creee.value = identifiant.value
    }
    await post('/api/sources/resana/add', {
      collection: creee.value,
      espace_id: espace.value,
      espace_nom: espaceChoisi.value.nom,
      dossier_id: dossierChoisi.value.id,
      dossier_chemin: dossierChoisi.value.chemin,
      exclus: exclus.value,
    })
    router.push(`/c/${creee.value}/upload`)
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    envoi.value = false
  }
}

onMounted(async () => {
  chargerEspaces()
  get('/api/collections/regles-nommage')
    .then((r) => {
      regles.value = { ...REGLES_PAR_DEFAUT, ...r }
    })
    .catch(() => {})
  try {
    pris.value = new Set(((await get('/api/collections')).collections || []).map((c: { name: string }) => c.name))
  }
  catch {}
})
onBeforeUnmount(() => {
  clearTimeout(minuterie)
  clearTimeout(rappel)
})
</script>

<template>
  <WizardEtape
    :numero="phase === 'choisir' ? 1 : 2"
    :titre="phase === 'choisir' ? 'Choisir dans Résana' : 'Relire la fiche'"
    :chapeau="phase === 'choisir'
      ? 'Choisissez l\'espace, le dossier, puis ce qu\'il faut en indexer. La collection reste privée : vous seul l\'interrogez, avec vos droits Résana.'
      : 'Tout est prérempli d\'après le dossier : relisez, puis créez. L\'indexation se fait en arrière-plan.'"
  >
    <template #formulaire>
      <div
        v-if="erreur"
        class="fr-alert fr-alert--sm fr-mb-2w"
        :class="erreur.code === 'session_absente' ? 'fr-alert--warning' : 'fr-alert--error'"
        role="alert"
      >
        <p>{{ erreur.message }}</p>
        <p class="fr-mt-1w">
          <a
            v-if="erreur.urlConnexion"
            :href="erreur.urlConnexion"
            class="fr-link fr-mr-2w"
            target="_blank"
            rel="noopener"
          >Se connecter à Résana<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
          <button
            v-if="phase === 'choisir'"
            type="button"
            class="fr-btn fr-btn--sm fr-btn--tertiary"
            @click="espaces.length ? (dossier ? chargerInventaire() : chargerDossiers()) : chargerEspaces()"
          >
            Réessayer
          </button>
        </p>
      </div>

      <!-- 1. Choisir dans Résana -->
      <template v-if="phase === 'choisir'">
        <p
          v-if="chargeEspaces"
          class="fr-text--sm"
          role="status"
        >
          Ouverture de votre session Résana… Cela peut prendre jusqu'à une minute et demie la première fois.
        </p>
        <div
          v-if="espaces.length"
          class="fr-select-group"
        >
          <label
            class="fr-label"
            :for="`${champ}-espace`"
          >Espace</label>
          <select
            :id="`${champ}-espace`"
            v-model="espace"
            class="fr-select"
            @change="chargerDossiers"
          >
            <option
              value=""
              disabled
            >
              Choisissez un espace
            </option>
            <option
              v-for="e in espaces"
              :key="e.id"
              :value="e.id"
            >
              {{ e.nom }}
            </option>
          </select>
        </div>
        <p
          v-else-if="!chargeEspaces && !erreur"
          class="fr-text--sm"
        >
          Aucun espace Résana ne vous est ouvert.
        </p>

        <template v-if="espace">
          <div class="fr-input-group">
            <label
              class="fr-label"
              :for="`${champ}-recherche`"
            >Dossier
              <span class="fr-hint-text">Pour tout l'espace, choisissez son dossier principal : vous retirerez ensuite ce qui ne sert pas.</span>
            </label>
            <input
              :id="`${champ}-recherche`"
              v-model="recherche"
              class="fr-input"
              type="search"
              placeholder="Filtrer les dossiers…"
              autocomplete="off"
              @input="chercher"
            >
          </div>
          <p
            v-if="chargeDossiers"
            class="fr-text--sm"
            role="status"
          >
            Lecture des dossiers…
          </p>
          <div
            v-else-if="dossiers.length"
            class="fr-select-group"
          >
            <label
              class="fr-label"
              :for="`${champ}-dossier`"
            >Dossier à indexer</label>
            <select
              :id="`${champ}-dossier`"
              v-model="dossier"
              class="fr-select"
              @change="choisirDossier"
            >
              <option
                value=""
                disabled
              >
                Choisissez un dossier ({{ dossiers.length }})
              </option>
              <option
                v-for="d in dossiers"
                :key="d.id"
                :value="d.id"
              >
                {{ d.chemin || d.titre }}
              </option>
            </select>
          </div>
          <p
            v-else
            class="fr-text--sm"
          >
            Aucun dossier{{ recherche.trim() ? ' ne correspond' : '' }}.
          </p>
        </template>

        <!-- Ce qui existe déjà : le reprendre plutôt que de créer une collection de plus. -->
        <div
          v-if="existant && (existant.meme_dossier.length || existant.dossier_parent.length || existant.sous_dossiers.length)"
          class="fr-alert fr-alert--info fr-alert--sm fr-my-2w"
        >
          <p
            v-for="c in existant.meme_dossier"
            :key="`m-${c.collection}`"
          >
            Ce dossier est déjà indexé dans votre collection
            <NuxtLink :to="`/c/${c.collection}/upload`">
              « {{ c.titre }} »
            </NuxtLink> ({{ etiquetteResana(c) }}) : mettez-la à jour
            ou ajoutez-y des sous-dossiers plutôt que d'en créer une autre.
          </p>
          <p
            v-for="c in existant.dossier_parent"
            :key="`p-${c.collection}`"
          >
            Votre collection <NuxtLink :to="`/c/${c.collection}/upload`">
              « {{ c.titre }} »
            </NuxtLink> indexe déjà un dossier qui contient
            celui-ci (« {{ c.dossier_chemin }} »).
          </p>
          <p
            v-for="c in existant.sous_dossiers"
            :key="`s-${c.collection}`"
          >
            Ce dossier contient « {{ c.dossier_chemin }} », déjà indexé dans votre collection
            <NuxtLink :to="`/c/${c.collection}/upload`">
              « {{ c.titre }} »
            </NuxtLink>.
          </p>
        </div>

        <p
          v-if="enPreparation"
          class="fr-text--sm fr-mt-2w"
          role="status"
        >
          Résana prépare l'inventaire de ce grand dossier{{ preparation(enPreparation.dossiers_lus, enPreparation.dossiers) }}.
          Cela peut prendre plusieurs minutes ; vous pouvez aussi continuer : tout le dossier sera indexé, et vous retirerez
          des sous-dossiers ensuite.
        </p>
        <p
          v-else-if="dossier && !inventaire && !erreur"
          class="fr-text--sm fr-mt-2w"
          role="status"
        >
          Inventaire du dossier…
        </p>
        <DepotArbreResana
          v-if="inventaire"
          v-model="exclus"
          class="fr-mt-3w"
          :inventaire="inventaire"
        />
      </template>

      <!-- 2. La fiche -->
      <template v-else>
        <div class="fr-input-group">
          <label
            class="fr-label"
            :for="`${champ}-titre`"
          >Titre</label>
          <input
            :id="`${champ}-titre`"
            v-model="titre"
            class="fr-input"
            :disabled="!!creee"
          >
        </div>
        <p class="fr-text--sm resana-discret">
          Identifiant : <code>{{ identifiant || '—' }}</code>
        </p>
        <div class="fr-input-group">
          <label
            class="fr-label"
            :for="`${champ}-description`"
          >Description</label>
          <textarea
            :id="`${champ}-description`"
            v-model="description"
            class="fr-input"
            rows="3"
            :disabled="!!creee"
          />
        </div>
        <ul class="fr-tags-group fr-mb-2w">
          <li><span class="fr-tag fr-tag--sm">Résana</span></li>
          <li>
            <span class="fr-tag fr-tag--sm">{{ exclus.length ? 'Index partiel' : 'Index complet' }}</span>
          </li>
          <li><span class="fr-tag fr-tag--sm">Privée</span></li>
        </ul>
        <p class="fr-text--sm">
          <strong>{{ espaceChoisi?.nom }}</strong> › {{ dossierChoisi?.chemin }}
          <template v-if="retenus">
            — {{ retenus.documents }} document{{ retenus.documents > 1 ? 's' : '' }} à indexer{{ exclus.length ? `, ${exclus.length} sous-dossier${exclus.length > 1 ? 's' : ''} exclu${exclus.length > 1 ? 's' : ''}` : '' }}.
          </template>
          <template v-else>
            — tout le dossier (inventaire en cours chez Résana).
          </template>
        </p>
        <div
          v-if="erreurFiche"
          class="fr-alert fr-alert--error fr-alert--sm"
          role="alert"
        >
          <p>{{ erreurFiche }}</p>
        </div>
        <p
          v-if="creee"
          class="fr-text--sm"
        >
          La collection « {{ creee }} » est créée ; l'indexation n'a pas pu démarrer. Réessayez, ou retrouvez-la dans
          <NuxtLink to="/mes-collections">
            Mes collections
          </NuxtLink>.
        </p>
      </template>
    </template>

    <template #encadre>
      <h2 class="fr-callout__title fr-h6">
        Ce qui se passe
      </h2>
      <ol class="fr-callout__text fr-text--sm">
        <li><strong>Lecture :</strong> les documents sont lus dans Résana avec vos droits.</li>
        <li><strong>Indexation :</strong> en arrière-plan ; un grand dossier peut demander plusieurs passes.</li>
        <li><strong>Mise à jour :</strong> quand l'index vieillit, l'outil vous propose de le mettre à jour, jusque dans les réponses.</li>
      </ol>
      <p class="fr-text--xs fr-mb-0">
        La collection reste privée : seul vous l'interrogez et la mettez à jour.
      </p>
    </template>

    <template #actions>
      <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-md">
        <li>
          <NuxtLink
            to="/admin/create"
            class="fr-btn fr-btn--tertiary-no-outline"
          >
            Annuler
          </NuxtLink>
        </li>
        <li v-if="phase === 'fiche' && !creee">
          <button
            type="button"
            class="fr-btn fr-btn--secondary"
            @click="phase = 'choisir'"
          >
            Étape précédente
          </button>
        </li>
        <li v-if="phase === 'choisir'">
          <button
            type="button"
            class="fr-btn"
            :disabled="!peutContinuer"
            @click="continuer"
          >
            Continuer
          </button>
        </li>
        <li v-else>
          <button
            type="button"
            class="fr-btn"
            :disabled="envoi || !titre.trim()"
            @click="creerEtIndexer"
          >
            {{ envoi ? 'Création…' : (creee ? 'Relancer l\'indexation' : 'Créer et indexer') }}
          </button>
        </li>
      </ul>
    </template>
  </WizardEtape>
</template>

<style scoped>
.resana-discret { color: var(--text-mention-grey); }
</style>
