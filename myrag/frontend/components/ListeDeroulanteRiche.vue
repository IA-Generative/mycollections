<script setup lang="ts">
/**
 * Liste déroulante riche : choisir une option en tapant quelques lettres. Elle suit la maquette DSFR
 * « Liste déroulante riche » (bêta, pas encore publiée en code) et le motif « combobox » du W3C
 * (champ éditable, liste filtrée, `aria-activedescendant`).
 * Clavier : flèches pour parcourir (et ouvrir), Entrée pour choisir, Échap pour fermer puis vider,
 * Tab pour quitter. À remplacer par le composant du DSFR le jour où il existe en code.
 */
import type { OptionRiche } from '~/utils/listeRiche'
import { annonceResultats, filtrerOptions, indexSuivant } from '~/utils/listeRiche'

const props = withDefaults(defineProps<{
  options: OptionRiche[]
  label: string
  hint?: string
  placeholder?: string
  /** Au-delà, la liste affichée est coupée (on affine en tapant). */
  max?: number
}>(), { hint: '', placeholder: 'Tapez pour chercher…', max: 50 })

const valeur = defineModel<string>({ default: '' })

const id = useId()
const saisie = ref('')
const ouvert = ref(false)
const actif = ref(-1)
const champ = ref<HTMLInputElement | null>(null)
const liste = ref<HTMLElement | null>(null)

const choisie = computed(() => props.options.find(o => o.value === valeur.value) || null)
const trouvees = computed(() => filtrerOptions(props.options, saisie.value))
const affichees = computed(() => trouvees.value.slice(0, props.max))
const annonce = computed(() => (ouvert.value ? annonceResultats(trouvees.value.length) : ''))
const idActif = computed(() => (actif.value >= 0 && affichees.value[actif.value] ? `${id}-o-${actif.value}` : undefined))

// Fermé : le champ montre l'option choisie.
watch(choisie, (o) => {
  if (!ouvert.value) {
    saisie.value = o?.label || ''
  }
}, { immediate: true })

function ouvrir () {
  if (!ouvert.value) {
    ouvert.value = true
    actif.value = affichees.value.findIndex(o => o.value === valeur.value)
  }
}

function fermer () {
  ouvert.value = false
  actif.value = -1
  saisie.value = choisie.value?.label || ''
}

function choisir (o: OptionRiche) {
  valeur.value = o.value
  ouvert.value = false
  actif.value = -1
  saisie.value = o.label
}

function taper () {
  ouvert.value = true
  actif.value = affichees.value.length ? 0 : -1
}

function surClic () {
  // Rouvrir la liste en cliquant dans le champ : le texte est sélectionné, la frappe le remplace.
  if (!ouvert.value) {
    ouvrir()
    champ.value?.select()
  }
}

function surFocus () {
  // On tape pour chercher : le texte de l'option choisie est sélectionné, donc remplacé.
  nextTick(() => champ.value?.select())
}

function rendreVisible () {
  nextTick(() => {
    const el = idActif.value ? document.getElementById(idActif.value) : null
    el?.scrollIntoView({ block: 'nearest' })
  })
}

function clavier (e: KeyboardEvent) {
  switch (e.key) {
    case 'ArrowDown':
    case 'ArrowUp':
      e.preventDefault()
      if (!ouvert.value) {
        ouvrir()
        return
      }
      actif.value = indexSuivant(actif.value, affichees.value.length, e.key === 'ArrowDown' ? 1 : -1)
      rendreVisible()
      break
    case 'Enter':
      if (ouvert.value && actif.value >= 0 && affichees.value[actif.value]) {
        e.preventDefault()
        choisir(affichees.value[actif.value]!)
      }
      break
    case 'Escape':
      if (ouvert.value) {
        e.preventDefault()
        fermer()
      }
      else if (saisie.value) {
        saisie.value = ''
      }
      break
    case 'Tab':
      if (ouvert.value) {
        fermer()
      }
      break
  }
}

function surSortie (e: FocusEvent) {
  // Un clic dans la liste ne doit pas la fermer avant d'avoir choisi.
  if (liste.value && e.relatedTarget instanceof Node && liste.value.contains(e.relatedTarget)) {
    return
  }
  if (ouvert.value) {
    fermer()
  }
}
</script>

<template>
  <div class="fr-input-group riche">
    <label
      class="fr-label"
      :for="`${id}-champ`"
    >
      {{ label }}
      <span
        v-if="hint"
        class="fr-hint-text"
      >{{ hint }}</span>
    </label>
    <div class="riche__champ">
      <input
        :id="`${id}-champ`"
        ref="champ"
        v-model="saisie"
        class="fr-input"
        type="text"
        role="combobox"
        autocomplete="off"
        aria-autocomplete="list"
        :aria-expanded="ouvert ? 'true' : 'false'"
        :aria-controls="`${id}-liste`"
        :aria-activedescendant="idActif"
        :placeholder="placeholder"
        @input="taper"
        @focus="surFocus"
        @click="surClic"
        @keydown="clavier"
        @blur="surSortie"
      >
      <span
        class="riche__fleche fr-icon-arrow-down-s-line"
        :class="{ 'riche__fleche--ouverte': ouvert }"
        aria-hidden="true"
      />
    </div>
    <ul
      v-show="ouvert"
      :id="`${id}-liste`"
      ref="liste"
      class="riche__liste"
      role="listbox"
      :aria-label="label"
    >
      <li
        v-for="(o, i) in affichees"
        :id="`${id}-o-${i}`"
        :key="o.value"
        role="option"
        class="riche__option"
        :class="{ 'riche__option--active': i === actif, 'riche__option--choisie': o.value === valeur }"
        :aria-selected="o.value === valeur ? 'true' : 'false'"
        @mousedown.prevent="choisir(o)"
        @mousemove="actif = i"
      >
        <span class="riche__libelle">{{ o.label }}</span>
        <span
          v-if="o.hint"
          class="riche__precision"
        >{{ o.hint }}</span>
      </li>
      <li
        v-if="!affichees.length"
        class="riche__vide"
        role="presentation"
      >
        Aucun résultat.
      </li>
      <li
        v-else-if="trouvees.length > affichees.length"
        class="riche__vide"
        role="presentation"
      >
        {{ trouvees.length - affichees.length }} autres : précisez la recherche.
      </li>
    </ul>
    <p
      class="fr-sr-only"
      aria-live="polite"
    >
      {{ annonce }}
    </p>
  </div>
</template>

<style scoped>
.riche { position: relative; max-width: 40rem; }
.riche__champ { position: relative; }
.riche__champ .fr-input { padding-right: 2.5rem; }
.riche__fleche { position: absolute; right: .75rem; top: 50%; transform: translateY(-50%); pointer-events: none; transition: transform .15s; }
.riche__fleche--ouverte { transform: translateY(-50%) rotate(180deg); }
.riche__liste {
  position: absolute; z-index: 1000; left: 0; right: 0; margin: .25rem 0 0; padding: .25rem 0; list-style: none;
  max-height: 18rem; overflow-y: auto; background: var(--background-overlap-grey);
  box-shadow: 0 6px 18px 0 rgb(0 0 18 / 16%); border: 1px solid var(--border-default-grey);
}
.riche__option { display: flex; flex-direction: column; padding: .5rem .75rem; cursor: pointer; }
.riche__option--active { background: var(--background-default-grey-hover); box-shadow: inset 3px 0 0 var(--border-active-blue-france); }
.riche__option--choisie .riche__libelle { font-weight: 700; }
.riche__precision { font-size: .75rem; line-height: 1.25rem; color: var(--text-mention-grey); }
.riche__vide { padding: .5rem .75rem; font-size: .875rem; color: var(--text-mention-grey); }
</style>
