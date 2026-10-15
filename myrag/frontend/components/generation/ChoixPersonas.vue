<template>
  <fieldset class="fr-fieldset choix" :aria-labelledby="`${uid}-legende`">
    <legend :id="`${uid}-legende`" class="fr-fieldset__legend fr-text--regular">
      Qui pose les questions ? <strong>{{ coches }} / {{ PERSONAS_MAX }}</strong>
      <span class="fr-hint-text">Cochez un ou plusieurs personas : les questions seront réparties entre eux. Leur situation se modifie avant le lancement.</span>
    </legend>

    <div class="choix__actions">
      <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-sparkling-2-line fr-btn--icon-left"
              :disabled="desactive || proposition" @click="proposer">
        {{ proposition ? 'Lecture des documents…' : 'Proposer des personas d\'après les documents' }}
      </button>
      <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-add-line fr-btn--icon-left"
              :disabled="desactive" @click="ajouterLibre">Ajouter un persona</button>
    </div>
    <p v-if="message" class="fr-text--xs fr-mb-1w" aria-live="polite">{{ message }}</p>
    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w" role="alert"><p>{{ erreur }}</p></div>

    <ul class="choix__liste">
      <li v-for="c in modelValue" :key="c.cle" class="choix__item" :class="{ 'choix__item--coche': c.coche }">
        <div class="fr-checkbox-group fr-checkbox-group--sm">
          <input :id="`${uid}-${c.cle}`" v-model="c.coche" type="checkbox"
                 :disabled="desactive || (!c.coche && coches >= PERSONAS_MAX)">
          <label class="fr-label" :for="`${uid}-${c.cle}`">
            <template v-if="c.origine !== 'libre'">{{ c.nom }}</template>
            <span v-else class="fr-sr-only">Persona libre</span>
            <span class="fr-badge fr-badge--sm fr-badge--no-icon choix__origine" :class="`choix__origine--${c.origine}`">{{ ORIGINES[c.origine] }}</span>
          </label>
        </div>
        <div v-if="c.origine === 'libre'" class="fr-input-group choix__champ">
          <label class="fr-label" :for="`${uid}-${c.cle}-nom`">Nom du profil</label>
          <input :id="`${uid}-${c.cle}-nom`" v-model="c.nom" class="fr-input" maxlength="120" :disabled="desactive"
                 placeholder="Ex. : Usager qui prépare son rendez-vous">
        </div>
        <div v-if="c.id" class="fr-text--sm choix__role">{{ c.description_role }}</div>
        <div v-else class="fr-input-group choix__champ">
          <label class="fr-label fr-sr-only" :for="`${uid}-${c.cle}-role`">Situation de {{ c.nom || 'ce persona' }}</label>
          <textarea :id="`${uid}-${c.cle}-role`" v-model="c.description_role" class="fr-input" rows="3" :disabled="desactive"
                    placeholder="Son métier, à qui il répond, ce qu'il cherche."></textarea>
        </div>
      </li>
    </ul>
  </fieldset>
</template>

<script setup lang="ts">
import { PERSONAS_MAX, ajouterCandidats, type CandidatPersona } from '~/utils/generation'

/**
 * Choisir les personas d'une génération : ceux de la collection, des exemples, un ou plusieurs
 * personas libres, ou des propositions tirées des documents (un appel au modèle, rien d'enregistré
 * avant le lancement). La liste est le v-model ; `preparerLancement` en tire ce qu'il faut créer.
 */
const props = defineProps<{ collection: string, modelValue: CandidatPersona[], desactive?: boolean }>()
const g = useGeneration()
const uid = `choix-${useId()}`
const proposition = ref(false)
const message = ref('')
const erreur = ref('')
let libres = 0
const coches = computed(() => props.modelValue.filter(c => c.coche).length)
const ORIGINES: Record<CandidatPersona['origine'], string> = {
  collection: 'de la collection', exemple: 'exemple', proposition: 'proposé', libre: 'libre',
}

function ajouterLibre() {
  libres++
  ajouterCandidats(props.modelValue, [{ nom: `Persona ${libres}`, description_role: '' }], 'libre')
  const c = props.modelValue[0]
  c.nom = ''
  nextTick(() => document.getElementById(`${uid}-${c.cle}-nom`)?.focus())
}

async function proposer() {
  proposition.value = true
  erreur.value = ''
  message.value = ''
  try {
    const r = await g.proposerPersonas(props.collection, 4)
    const n = ajouterCandidats(props.modelValue, r.propositions || [], 'proposition')
    message.value = n
      ? `${n} persona${n > 1 ? 's' : ''} proposé${n > 1 ? 's' : ''} d'après ${r.passages} passages — relisez-les et modifiez leur situation au besoin.`
      : 'Aucun nouveau persona : les propositions reprenaient ceux de la liste.'
  } catch (e) {
    erreur.value = messageErreur(e)
  } finally {
    proposition.value = false
  }
}
</script>

<style scoped>
.choix { width: 100%; min-width: 0; margin: 0; }
.choix__liste, .choix__actions { width: 100%; }
.choix__actions { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: .75rem; }
.choix__liste { list-style: none; padding: 0; margin: 0; display: grid; gap: .5rem; }
.choix__item { border: 1px solid var(--border-default-grey); padding: .5rem .75rem; display: grid; gap: .25rem; }
.choix__item--coche { border-color: var(--border-action-high-blue-france); background: var(--background-alt-blue-france); }
.choix__origine { margin-left: .5rem; }
.choix__origine--proposition { background: var(--background-contrast-yellow-tournesol); }
.choix__role { color: var(--text-mention-grey); padding-left: 1.75rem; }
.choix__champ { margin: 0; padding-left: 1.75rem; }
</style>
