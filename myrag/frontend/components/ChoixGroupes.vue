<script setup lang="ts">
/**
 * Choisir les groupes avec qui partager une collection (étape 5 de l'assistant, page Partager),
 * comme à l'étape 2 : une barre de recherche parmi ses propres groupes (le claim `groups` du
 * jeton, en chemins complets), le groupe choisi se range dessous en puce ; un nom hors liste
 * s'ajoute tel quel. Puis le pont vers Communauté pour créer un groupe, et « Actualiser mes
 * groupes », qui renouvelle le jeton pour y lire le nouveau (docs/resana.md, « Partager »).
 */
import { fusionnerGroupes, optionsGroupes } from '~/utils/groupes'
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
const texte = computed(() => recherche.value.trim())
/** Mes groupes qui correspondent à la saisie, pas encore choisis. */
const resultats = computed(() => (texte.value ? filtrerOptions(options.value, texte.value) : options.value).filter(o => !props.modelValue.includes(o.value)))
/** La saisie ne correspond à aucun de mes groupes : on peut l'ajouter telle quelle (un groupe du chat MirAI dont on n'est pas membre). */
const horsListe = computed(() => !!texte.value && !options.value.some(o => o.value === texte.value || o.label.toLowerCase() === texte.value.toLowerCase()))
const ouvert = ref(false)

function ajouter (valeur: string) {
  const v = valeur.trim()
  if (!v) {
    return
  }
  emit('update:modelValue', fusionnerGroupes(props.modelValue, [v]))
  recherche.value = ''
  ouvert.value = false
}
function retirer (valeur: string) {
  emit('update:modelValue', props.modelValue.filter(g => g !== valeur))
}
function surEntree () {
  if (resultats.value.length === 1 || (resultats.value.length && !horsListe.value)) {
    ajouter(resultats.value[0]!.value)
  }
  else if (horsListe.value) {
    ajouter(texte.value)
  }
}
function fermerPlusTard () {
  // Laisser le clic sur un résultat arriver avant de replier la liste.
  setTimeout(() => {
    ouvert.value = false
  }, 150)
}

// ─── Communauté : créer un groupe, puis relire ses groupes ──────────────────
const communauteUrl = ref('')
const nomGroupe = ref('')
const actualisation = ref(false)
const messageActualisation = ref('')
// `creer=1` et `retour=` : Communauté accueille la personne pour créer, puis lui propose de revenir ici
// (keycloak-comu #116 ; l'origine de Mes collections doit être dans sa liste blanche).
const lienCreation = computed(() => {
  if (!communauteUrl.value) {
    return ''
  }
  const p = new URLSearchParams({ q: nomGroupe.value.trim() || props.nomPropose, creer: '1' })
  if (typeof window !== 'undefined') {
    p.set('retour', window.location.href)
  }
  return `${communauteUrl.value}/?${p.toString()}`
})

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
        ? `${apres - avant} nouveau${apres - avant > 1 ? 'x' : ''} groupe${apres - avant > 1 ? 's' : ''} : cherchez-le ci-dessus.`
        : 'Vos groupes n\'ont pas changé. S\'il manque encore, reconnectez-vous : votre session sera reprise ici.'
  }
  finally {
    actualisation.value = false
  }
}
</script>

<template>
  <div class="choix-groupes">
    <div class="fr-input-group fr-mb-1w">
      <label
        class="fr-label"
        :for="champ"
      >Groupes
        <span class="fr-hint-text">
          {{ options.length ? 'Cherchez parmi vos groupes, puis choisissez : le groupe se range dessous.' : 'Vos groupes ne sont pas lisibles depuis votre connexion : tapez le nom du groupe tel qu\'il apparaît dans le chat MirAI.' }}
          Seuls les membres des groupes choisis verront la collection dans le chat MirAI.
        </span>
      </label>
      <input
        :id="champ"
        v-model="recherche"
        class="fr-input"
        type="text"
        placeholder="Rechercher un groupe…"
        autocomplete="off"
        role="combobox"
        :aria-expanded="ouvert && (resultats.length > 0 || horsListe) ? 'true' : 'false'"
        :aria-controls="`${champ}-liste`"
        @focus="ouvert = true"
        @input="ouvert = true"
        @blur="fermerPlusTard"
        @keydown.enter.prevent="surEntree"
        @keydown.esc="ouvert = false"
      >
      <ul
        v-if="ouvert && (resultats.length || horsListe)"
        :id="`${champ}-liste`"
        class="choix-groupes__resultats"
      >
        <li
          v-for="o in resultats"
          :key="o.value"
        >
          <button
            type="button"
            class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
            @mousedown.prevent="ajouter(o.value)"
          >
            {{ o.label }} <span class="choix-groupes__discret">{{ o.hint }}</span>
          </button>
        </li>
        <li v-if="horsListe">
          <button
            type="button"
            class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-add-line fr-btn--icon-left"
            @mousedown.prevent="ajouter(texte)"
          >
            Ajouter « {{ texte }} » (un groupe hors de ma liste)
          </button>
        </li>
      </ul>
    </div>

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
    <p
      v-else
      class="fr-text--sm fr-mb-2w choix-groupes__discret"
    >
      Aucun groupe choisi.
    </p>

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
.choix-groupes__resultats { list-style: none; margin: .25rem 0 0; padding: .25rem 0; border: 1px solid var(--border-default-grey); background: #fff; max-height: 14rem; overflow-y: auto; }
.choix-groupes__resultats li { margin: 0; }
.choix-groupes__resultats .fr-btn { width: 100%; justify-content: flex-start; text-align: left; }
.choix-groupes__discret { color: var(--text-mention-grey); font-size: .8rem; margin-left: .35rem; }
</style>
