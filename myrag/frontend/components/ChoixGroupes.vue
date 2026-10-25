<script setup lang="ts">
import { fusionnerGroupes, optionsGroupes } from '~/utils/groupes'
/**
 * Choisir les groupes avec qui partager une collection (étape 5 de l'assistant, page Partager) :
 * ses propres groupes à cocher (le claim `groups` du jeton, en chemins complets), un groupe hors
 * liste à saisir, et le pont vers Communauté pour en créer un — puis « Actualiser mes groupes »,
 * qui renouvelle le jeton pour y lire le nouveau groupe (docs/resana.md, « Partager »).
 */
import { filtrerOptions } from '~/utils/listeRiche'

const props = withDefaults(defineProps<{
  modelValue: string[]
  /** Le nom proposé pour un groupe à créer dans Communauté (le titre de la collection). */
  nomPropose?: string
}>(), { nomPropose: '' })
const emit = defineEmits<{ 'update:modelValue': [v: string[]] }>()

const { user, renewToken, reconnecter } = useAuth()
const { get } = useApi()
const champ = useId()

const options = computed(() => optionsGroupes(user.value?.profile?.groups))
const recherche = ref('')
const visibles = computed(() => (recherche.value.trim() ? filtrerOptions(options.value, recherche.value) : options.value))
const avecFiltre = computed(() => options.value.length > 8)

const coches = computed(() => props.modelValue.filter(g => options.value.some(o => o.value === g)))
const libres = computed(() => props.modelValue.filter(g => !options.value.some(o => o.value === g)))
const saisie = ref('')

function poser (nouveauxCoches: readonly string[], nouveauxLibres: readonly string[]) {
  emit('update:modelValue', fusionnerGroupes(nouveauxCoches, nouveauxLibres))
}
function basculer (valeur: string, coche: boolean) {
  poser(coche ? [...coches.value, valeur] : coches.value.filter(g => g !== valeur), libres.value)
}
function ajouterLibre () {
  const g = saisie.value.trim()
  if (!g) {
    return
  }
  poser(coches.value, [...libres.value, g])
  saisie.value = ''
}
function retirer (valeur: string) {
  poser(coches.value.filter(g => g !== valeur), libres.value.filter(g => g !== valeur))
}

// ─── Communauté : créer un groupe, puis relire ses groupes ──────────────────
const communauteUrl = ref('')
const nomGroupe = ref('')
const actualisation = ref(false)
const messageActualisation = ref('')
const lienCreation = computed(() => (communauteUrl.value ? `${communauteUrl.value}/?q=${encodeURIComponent(nomGroupe.value.trim() || props.nomPropose)}` : ''))

onMounted(async () => {
  try {
    communauteUrl.value = (await get('/api/config')).communaute_url || ''
  }
  catch { /* sans adresse, pas de pont */ }
})

async function actualiserMesGroupes () {
  actualisation.value = true
  messageActualisation.value = ''
  const avant = options.value.length
  try {
    const ok = await renewToken()
    const apres = options.value.length
    messageActualisation.value = !ok
      ? 'Vos groupes n\'ont pas pu être relus.'
      : apres > avant
        ? `${apres - avant} nouveau${apres - avant > 1 ? 'x' : ''} groupe${apres - avant > 1 ? 's' : ''} : cochez-le ci-dessus.`
        : 'Vos groupes n\'ont pas changé. S\'il manque encore, reconnectez-vous : votre session sera reprise ici.'
  }
  finally {
    actualisation.value = false
  }
}
</script>

<template>
  <div class="choix-groupes">
    <fieldset
      class="fr-fieldset fr-mb-2w"
      :aria-labelledby="`${champ}-legende`"
    >
      <legend
        :id="`${champ}-legende`"
        class="fr-fieldset__legend fr-text--regular fr-pb-0"
      >
        Mes groupes
        <span class="fr-hint-text">Les groupes dont vous êtes membre. Seuls leurs membres verront la collection dans le chat MirAI.</span>
      </legend>
      <div
        v-if="avecFiltre"
        class="fr-fieldset__element"
      >
        <div class="fr-input-group fr-mb-0">
          <label
            class="fr-label fr-sr-only"
            :for="`${champ}-filtre`"
          >Filtrer mes groupes</label>
          <input
            :id="`${champ}-filtre`"
            v-model="recherche"
            class="fr-input"
            type="search"
            placeholder="Filtrer mes groupes…"
          >
        </div>
      </div>
      <p
        v-if="!options.length"
        class="fr-fieldset__element fr-text--sm choix-groupes__discret"
      >
        Vos groupes ne sont pas lisibles depuis votre connexion : saisissez-les ci-dessous.
      </p>
      <div
        v-for="o in visibles"
        :key="o.value"
        class="fr-fieldset__element fr-fieldset__element--inline"
      >
        <div class="fr-checkbox-group fr-checkbox-group--sm">
          <input
            :id="`${champ}-${o.value}`"
            type="checkbox"
            :checked="coches.includes(o.value)"
            @change="basculer(o.value, ($event.target as HTMLInputElement).checked)"
          >
          <label
            class="fr-label"
            :for="`${champ}-${o.value}`"
          >{{ o.label }}
            <span class="fr-hint-text">{{ o.hint }}</span>
          </label>
        </div>
      </div>
    </fieldset>

    <div class="fr-input-group fr-mb-2w">
      <label
        class="fr-label"
        :for="`${champ}-libre`"
      >Un groupe hors de cette liste
        <span class="fr-hint-text">Son nom tel qu'il apparaît dans le chat MirAI. Un nom inconnu du chat MirAI est refusé au partage : la collection ne viserait personne.</span>
      </label>
      <div class="choix-groupes__ligne">
        <input
          :id="`${champ}-libre`"
          v-model="saisie"
          class="fr-input"
          type="text"
          @keydown.enter.prevent="ajouterLibre"
        >
        <button
          type="button"
          class="fr-btn fr-btn--sm fr-btn--secondary"
          :disabled="!saisie.trim()"
          @click="ajouterLibre"
        >
          Ajouter
        </button>
      </div>
    </div>

    <p
      v-if="modelValue.length"
      class="fr-text--sm fr-mb-1v"
    >
      Partagée avec :
    </p>
    <ul
      v-if="modelValue.length"
      class="fr-tags-group fr-mb-2w"
    >
      <li
        v-for="g in modelValue"
        :key="g"
      >
        <button
          type="button"
          class="fr-tag fr-tag--sm fr-tag--dismiss"
          :aria-label="`Retirer ${g}`"
          @click="retirer(g)"
        >
          {{ g }}
        </button>
      </li>
    </ul>

    <div
      v-if="communauteUrl"
      class="fr-callout fr-callout--blue-ecume fr-mb-2w"
    >
      <h3 class="fr-callout__title fr-h6">
        Il vous manque un groupe ?
      </h3>
      <p class="fr-callout__text fr-text--sm">
        Les groupes se créent dans Communauté : donnez-lui un nom, invitez vos collègues, puis revenez ici et
        actualisez vos groupes.
      </p>
      <div class="fr-input-group fr-mb-1w">
        <label
          class="fr-label fr-text--sm"
          :for="`${champ}-nom`"
        >Nom du groupe à créer (facultatif)</label>
        <input
          :id="`${champ}-nom`"
          v-model="nomGroupe"
          class="fr-input"
          type="text"
          :placeholder="nomPropose"
        >
      </div>
      <ul class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mb-0">
        <li>
          <a
            :href="lienCreation"
            class="fr-btn fr-btn--sm fr-btn--secondary"
            target="_blank"
            rel="noopener"
          >Créer un groupe dans Communauté<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
        </li>
        <li>
          <button
            type="button"
            class="fr-btn fr-btn--sm fr-btn--tertiary"
            :disabled="actualisation"
            @click="actualiserMesGroupes"
          >
            {{ actualisation ? 'Relecture…' : 'J\'ai créé mon groupe : actualiser mes groupes' }}
          </button>
        </li>
        <li v-if="messageActualisation.includes('reconnectez')">
          <button
            type="button"
            class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline"
            @click="reconnecter"
          >
            Se reconnecter
          </button>
        </li>
      </ul>
      <p
        v-if="messageActualisation"
        class="fr-text--xs fr-mt-1w fr-mb-0"
        role="status"
      >
        {{ messageActualisation }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.choix-groupes__ligne { display: flex; gap: .5rem; align-items: flex-start; }
.choix-groupes__ligne .fr-input { flex: 1 1 auto; }
.choix-groupes__discret { color: var(--text-mention-grey); }
</style>
