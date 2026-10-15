<template>
  <div class="champ">
    <span class="champ__libelle fr-text--xs">{{ libelle }}</span>
    <div v-if="edition" class="fr-input-group fr-mb-0">
      <label class="fr-label fr-sr-only" :for="uid">{{ libelle }}</label>
      <textarea :id="uid" ref="zone" v-model="brouillon" class="fr-input" :rows="Math.min(10, Math.max(2, Math.ceil(brouillon.length / 70)))"
                :maxlength="max" @keydown.esc.prevent="annuler" @keydown.ctrl.enter.prevent="enregistrer" @keydown.meta.enter.prevent="enregistrer"
                @blur="enregistrer" />
      <p class="fr-hint-text fr-mt-1v">Enregistré en quittant le champ (ou Ctrl+Entrée) ; Échap pour annuler.</p>
    </div>
    <button v-else type="button" class="champ__texte" :title="`Modifier : ${libelle.toLowerCase()}`" @click="ouvrir">
      <span v-if="valeur.trim()">{{ valeur }}</span>
      <span v-else class="champ__vide">{{ vide || 'Vide : cliquer pour écrire.' }}</span>
      <span class="fr-icon-edit-line fr-icon--sm champ__crayon" aria-hidden="true" />
    </button>
  </div>
</template>

<script setup lang="ts">
/** Un texte modifiable en place : un clic l'ouvre, quitter le champ l'enregistre s'il a changé. */
const props = defineProps<{ valeur: string, libelle: string, max?: number, vide?: string }>()
const emit = defineEmits<{ enregistrer: [valeur: string] }>()
const uid = `champ-${useId()}`
const edition = ref(false)
const brouillon = ref('')
const zone = ref<HTMLTextAreaElement | null>(null)

function ouvrir() {
  brouillon.value = props.valeur
  edition.value = true
  nextTick(() => zone.value?.focus())
}
function annuler() {
  edition.value = false
}
function enregistrer() {
  if (!edition.value) return
  edition.value = false
  const v = brouillon.value.trim()
  if (v !== props.valeur.trim()) emit('enregistrer', v)
}
</script>

<style scoped>
.champ { min-width: 0; }
.champ__libelle { display: block; color: var(--text-mention-grey); margin-bottom: .125rem; }
.champ__texte {
  display: block; width: 100%; text-align: left; background: none; border: 1px dashed transparent; padding: .25rem .375rem;
  margin: 0 -.375rem; white-space: pre-wrap; overflow-wrap: anywhere; cursor: text; font: inherit; color: inherit;
}
.champ__texte:hover, .champ__texte:focus-visible { border-color: var(--border-default-grey); background: var(--background-alt-grey); }
.champ__vide { color: var(--text-mention-grey); font-style: italic; }
.champ__crayon { color: var(--text-action-high-blue-france); margin-left: .375rem; opacity: 0; }
.champ__texte:hover .champ__crayon, .champ__texte:focus-visible .champ__crayon { opacity: 1; }
</style>
