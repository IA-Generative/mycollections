<template>
  <div class="collectif-etapes">
    <p class="fr-text--xs collectif-etapes__sur" style="margin:0">État de la collection · étape {{ indexEtat(etat.etat) + 1 }} sur 4</p>
    <div class="collectif-etapes__ligne">
      <h3 class="fr-h6" style="margin:0">{{ libelleEtat(etat.etat) }}</h3>
      <span v-if="etat.mention" class="fr-badge fr-badge--warning fr-badge--sm fr-badge--no-icon">⚠ {{ etat.mention }}</span>
      <span v-else class="fr-badge fr-badge--success fr-badge--sm">diffusée à tous</span>
    </div>
    <div class="collectif-etapes__pas" role="img" :aria-label="`Étape ${indexEtat(etat.etat) + 1} sur 4`">
      <div v-for="(e, i) in ETATS_COLLECTION" :key="e" :class="{ fait: i <= indexEtat(etat.etat) }"></div>
    </div>
    <div class="collectif-etapes__lib fr-text--xs">
      <span v-for="(e, i) in ETATS_COLLECTION" :key="e" :class="{ ici: i === indexEtat(etat.etat) }">{{ libelleEtat(e) }}</span>
    </div>
    <p class="fr-text--xs fr-mt-1w" style="margin:0;color:var(--text-mention-grey)">
      <template v-if="etat.garant">Garant confirmé{{ etat.je_suis_garant ? ' : vous' : '' }}.</template>
      <template v-else-if="etat.garant_pressenti">Garant pressenti : {{ etat.garant_pressenti }} (à confirmer).</template>
      <template v-else>Pas encore de garant.</template>
    </p>
    <div v-if="etat.transitions_possibles && etat.transitions_possibles.length" class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-2w">
      <button v-for="cible in etat.transitions_possibles" :key="cible" class="fr-btn fr-btn--sm"
              :class="indexEtat(cible) < indexEtat(etat.etat) ? 'fr-btn--secondary' : ''" @click="$emit('changer', cible)">
        {{ indexEtat(cible) < indexEtat(etat.etat) ? 'Retirer de la diffusion à tous' : `Passer en « ${libelleEtat(cible)} »` }}
      </button>
    </div>
    <p v-else-if="etat.je_suis_garant && etat.etat === 'publiee_groupe' && !etat.grille_complete" class="fr-text--xs fr-mt-1w" style="color:var(--text-default-warning)">
      Publier à tous demande la grille de contrôle complète (source et licence, données personnelles, fraîcheur, une relecture).
    </p>
    <div v-if="superadmin" class="fr-mt-2w">
      <details>
        <summary class="fr-text--xs">Forcer le cycle (administration)</summary>
        <div class="collectif-forcer">
          <select v-model="cibleForcee" class="fr-select fr-select--sm" aria-label="État cible">
            <option v-for="e in ETATS_COLLECTION" :key="e" :value="e" :disabled="e === etat.etat">{{ libelleEtat(e) }}</option>
          </select>
          <input v-model="motifForce" class="fr-input" placeholder="Motif (obligatoire, il restera dans le fil)" aria-label="Motif du forçage">
          <button class="fr-btn fr-btn--sm fr-btn--secondary" :disabled="!motifForce.trim() || !cibleForcee" @click="$emit('forcer', cibleForcee, motifForce)">Forcer</button>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ETATS_COLLECTION, indexEtat, libelleEtat } from '~/utils/collectif'
defineProps<{ etat: any; superadmin?: boolean }>()
defineEmits<{ (e: 'changer', cible: string): void; (e: 'forcer', cible: string, motif: string): void }>()
const cibleForcee = ref('')
const motifForce = ref('')
</script>
