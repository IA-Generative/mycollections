<script setup lang="ts">
/**
 * Choisir un dossier d'un espace Résana et l'importer (docs/resana.md). Le service lit Résana avec
 * la session de la personne : il ne demande jamais de mot de passe ; sans session, il donne le lien
 * où s'en ouvrir une. Le parent porte le bouton d'import (`importer()`), comme pour un dossier.
 */
import type { ErreurResana } from '~/utils/resana'
import { erreurResana, preparation, resumeApercu } from '~/utils/resana'

const props = defineProps<{ collection: string }>()
const emit = defineEmits<{ pret: [boolean], lance: [number] }>()

interface Espace { id: string, nom: string }
interface Dossier { id: string, titre: string, chemin: string }

const { get, post } = useApi()
const champ = useId()
const espaces = ref<Espace[]>([])
const espace = ref('')
const dossiers = ref<Dossier[]>([])
const dossier = ref('')
const recherche = ref('')
const apercu = ref<{ total: number, taille_approx_mo?: number | null, documents: { titre: string, chemin: string }[] } | null>(null)
const chargeEspaces = ref(false)
const chargeDossiers = ref(false)
const chargeApercu = ref(false)
/** Un grand dossier : le service prépare la liste (202), on rappelle jusqu'à ce qu'elle soit prête. */
const enPreparation = ref<{ dossiers_lus?: number | null, dossiers?: number | null } | null>(null)
let rappel: ReturnType<typeof setTimeout> | undefined
const envoi = ref(false)
const erreur = ref<ErreurResana | null>(null)

const dossierChoisi = computed(() => dossiers.value.find(d => d.id === dossier.value) || null)
const pret = computed(() => !!(espace.value && dossierChoisi.value && (apercu.value?.total || enPreparation.value)) && !envoi.value)
watch(pret, v => emit('pret', v), { immediate: true })

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
  dossier.value = ''
  apercu.value = null
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

let minuterie: ReturnType<typeof setTimeout> | undefined
function chercher () {
  clearTimeout(minuterie)
  minuterie = setTimeout(chargerDossiers, 350)
}

async function chargerApercu () {
  clearTimeout(rappel)
  apercu.value = null
  enPreparation.value = null
  if (!dossier.value) {
    return
  }
  const demande = dossier.value
  chargeApercu.value = true
  erreur.value = null
  try {
    const r = await get(`/api/sources/resana/espaces/${encodeURIComponent(espace.value)}/apercu`, { dossier: demande })
    if (demande !== dossier.value) {
      return // la personne a choisi un autre dossier entre-temps
    }
    if (r.en_preparation) {
      enPreparation.value = r
      rappel = setTimeout(chargerApercu, 5000)
      return
    }
    apercu.value = r
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    chargeApercu.value = false
  }
}

async function importer () {
  if (!pret.value || !dossierChoisi.value) {
    return
  }
  envoi.value = true
  erreur.value = null
  try {
    const r = await post('/api/sources/resana/add', {
      collection: props.collection,
      espace_id: espace.value,
      espace_nom: espaces.value.find(e => e.id === espace.value)?.nom || '',
      dossier_id: dossierChoisi.value.id,
      dossier_chemin: dossierChoisi.value.chemin,
    })
    emit('lance', r.total || 0)
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    envoi.value = false
  }
}

defineExpose({ importer })
onMounted(chargerEspaces)
onBeforeUnmount(() => {
  clearTimeout(minuterie)
  clearTimeout(rappel)
})
</script>

<template>
  <section
    class="fr-card fr-mb-4w"
    :aria-labelledby="`${champ}-titre`"
  >
    <div class="fr-card__body">
      <div class="fr-card__content">
        <h2
          :id="`${champ}-titre`"
          class="fr-h5"
        >
          Choisir un dossier Résana
        </h2>
        <div class="fr-notice fr-notice--info fr-mb-2w">
          <div class="fr-container">
            <div class="fr-notice__body">
              <p class="fr-notice__title fr-text--sm">
                La collection reste privée : vous seul l'interrogez. Résana est lu avec vos droits, et vous seul pourrez la synchroniser.
              </p>
            </div>
          </div>
        </div>

        <p
          v-if="chargeEspaces"
          class="fr-text--sm"
          role="status"
        >
          Ouverture de votre session Résana… Cela peut prendre jusqu'à une minute et demie la première fois.
        </p>

        <div
          v-if="erreur"
          class="fr-alert fr-alert--sm fr-mb-2w"
          :class="erreur.code === 'session_absente' ? 'fr-alert--warning' : 'fr-alert--error'"
          role="alert"
        >
          <p>{{ erreur.message }}</p>
          <p
            v-if="erreur.urlConnexion || erreur.reessayable || erreur.code === 'session_absente'"
            class="fr-mt-1w"
          >
            <a
              v-if="erreur.urlConnexion"
              :href="erreur.urlConnexion"
              class="fr-link fr-mr-2w"
              target="_blank"
              rel="noopener"
            >Se connecter à Résana<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary"
              @click="espaces.length ? chargerDossiers() : chargerEspaces()"
            >
              Réessayer
            </button>
          </p>
        </div>

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
              <span class="fr-hint-text">Ses sous-dossiers sont importés avec lui.</span>
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
          <fieldset
            v-else-if="dossiers.length"
            class="fr-fieldset resana-dossiers"
          >
            <legend class="fr-sr-only">
              Dossiers de l'espace
            </legend>
            <div
              v-for="d in dossiers"
              :key="d.id"
              class="fr-fieldset__element"
            >
              <div class="fr-radio-group fr-radio-group--sm">
                <input
                  :id="`${champ}-d-${d.id}`"
                  v-model="dossier"
                  type="radio"
                  :name="`${champ}-dossier`"
                  :value="d.id"
                  @change="chargerApercu"
                >
                <label
                  class="fr-label"
                  :for="`${champ}-d-${d.id}`"
                >{{ d.chemin || d.titre }}</label>
              </div>
            </div>
          </fieldset>
          <p
            v-else
            class="fr-text--sm"
          >
            Aucun dossier{{ recherche.trim() ? ' ne correspond' : '' }}.
          </p>
        </template>

        <p
          v-if="enPreparation"
          class="fr-text--sm"
          role="status"
        >
          Résana prépare la liste de ce grand dossier{{ preparation(enPreparation.dossiers_lus, enPreparation.dossiers) }}.
          Cela peut prendre plusieurs minutes ; vous pouvez aussi lancer l'import tout de suite.
        </p>
        <p
          v-else-if="chargeApercu"
          class="fr-text--sm"
          role="status"
        >
          Inventaire du dossier…
        </p>
        <div
          v-else-if="apercu"
          class="fr-mt-2w"
          aria-live="polite"
        >
          <p class="fr-text--sm fr-mb-1w">
            <strong>{{ resumeApercu(apercu) }}</strong> seront importés depuis « {{ dossierChoisi?.chemin }} ».
          </p>
          <ul
            v-if="apercu.documents.length"
            class="fr-text--xs resana-apercu"
          >
            <li
              v-for="(d, i) in apercu.documents"
              :key="i"
            >
              {{ d.titre }}
            </li>
          </ul>
          <p
            v-if="!apercu.total"
            class="fr-text--sm"
          >
            Ce dossier est vide : choisissez-en un autre.
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.resana-dossiers { max-height: 18rem; overflow-y: auto; }
.resana-apercu { color: var(--text-mention-grey); max-height: 10rem; overflow-y: auto; }
</style>
