<template>
  <div>
    <div class="collectif-avancement__tete">
      <h3 class="fr-h6" style="margin:0">Grille de contrôle</h3>
      <span class="fr-badge fr-badge--sm" :class="grille.complete ? 'fr-badge--success' : 'fr-badge--warning'">
        {{ grille.complete ? 'complète' : 'incomplète' }}
      </span>
    </div>
    <dl class="collectif-grille">
      <div v-for="c in CHAMPS" :key="c.cle">
        <dt>{{ c.libelle }}</dt>
        <dd>
          <template v-if="edition && garant">
            <textarea v-model="brouillon[c.cle]" class="fr-input" rows="2" :aria-label="c.libelle"></textarea>
          </template>
          <template v-else-if="grille[c.cle]">{{ grille[c.cle] }}</template>
          <span v-else class="collectif-grille__vide">non renseigné</span>
        </dd>
      </div>
      <div>
        <dt>Relecture</dt>
        <dd>
          <template v-if="grille.relecture_n >= 1">{{ grille.relecture_n }} relecture{{ grille.relecture_n > 1 ? 's' : '' }}</template>
          <span v-else class="collectif-grille__vide">0 relecture sur 1 attendue</span>
          <button class="fr-btn fr-btn--sm fr-btn--tertiary fr-ml-1w" @click="$emit('relire')">Je relis cette collection</button>
        </dd>
      </div>
      <div v-if="grille.couverture && Object.keys(grille.couverture).length">
        <dt>Couverture constatée</dt>
        <dd>
          <ul class="fr-text--sm" style="margin:0;padding-left:1rem">
            <li v-for="(v, k) in grille.couverture" :key="k"><strong>{{ k }}</strong> : {{ Array.isArray(v) ? v.join(', ') : (typeof v === 'object' ? JSON.stringify(v) : v) }}</li>
          </ul>
          <p class="fr-text--xs" style="margin:0;color:var(--text-mention-grey)">Écrite par le connecteur à l'import, jamais par une personne.</p>
        </dd>
      </div>
    </dl>
    <div v-if="garant" class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-1w">
      <button v-if="!edition" class="fr-btn fr-btn--sm fr-btn--secondary" @click="commencer">Compléter la grille</button>
      <template v-else>
        <button class="fr-btn fr-btn--sm" @click="$emit('enregistrer', { ...brouillon }); edition = false">Enregistrer</button>
        <button class="fr-btn fr-btn--sm fr-btn--tertiary" @click="edition = false">Annuler</button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
const props = defineProps<{ grille: any; garant?: boolean }>()
defineEmits<{ (e: 'enregistrer', champs: any): void; (e: 'relire'): void }>()
const CHAMPS = [
  { cle: 'source_licence', libelle: 'Source et licence' },
  { cle: 'donnees_perso', libelle: 'Données personnelles' },
  { cle: 'fraicheur', libelle: 'Fraîcheur' },
]
const edition = ref(false)
const brouillon = ref<Record<string, string>>({})
function commencer() {
  brouillon.value = { source_licence: props.grille.source_licence || '', donnees_perso: props.grille.donnees_perso || '', fraicheur: props.grille.fraicheur || '' }
  edition.value = true
}
</script>
