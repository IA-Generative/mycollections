<template>
  <div class="collectif-avancement">
    <div class="collectif-avancement__tete">
      <h3 class="fr-h6" style="margin:0">Avancement</h3>
      <button v-if="abonnable" class="fr-btn fr-btn--sm fr-btn--tertiary" :class="abonne ? 'fr-icon-notification-3-fill' : 'fr-icon-notification-3-line'"
              @click="$emit('abonner', !abonne)">
        {{ abonne ? 'Abonné·e' : "S'abonner" }}
      </button>
    </div>
    <p v-if="evenements === null" class="fr-text--sm" style="color:var(--text-mention-grey)">Fil indisponible.</p>
    <p v-else-if="evenements.length === 0" class="fr-text--sm" style="color:var(--text-mention-grey)">Rien ne s'est encore passé.</p>
    <ul v-else class="collectif-fil">
      <li v-for="e in evenements" :key="e.id">
        <time class="fr-text--xs">{{ dateCourte(e.cree_le) }}</time>
        <div>
          <span>{{ libelleEvenement(e.type, e.detail) }}</span>
          <span class="fr-text--xs collectif-fil__qui">{{ e.par === 'personne' ? 'par une personne' : e.par.replace('robot:', '⚙ ') }}</span>
          <span v-if="e.detail && e.detail.motif" class="fr-text--xs collectif-fil__qui">motif : {{ e.detail.motif }}</span>
          <div v-if="chiffres(e.detail)" class="fr-text--xs collectif-fil__chiffres">{{ chiffres(e.detail) }}</div>
        </div>
      </li>
    </ul>
    <button v-if="suivant" class="fr-btn fr-btn--sm fr-btn--tertiary fr-mt-1w" @click="$emit('suite', suivant)">Plus ancien</button>
  </div>
</template>

<script setup lang="ts">
import { chiffres, dateCourte, libelleEvenement } from '~/utils/collectif'
defineProps<{ evenements: any[] | null; suivant?: string | null; abonne?: boolean; abonnable?: boolean }>()
defineEmits<{ (e: 'abonner', oui: boolean): void; (e: 'suite', avant: string): void }>()
</script>
