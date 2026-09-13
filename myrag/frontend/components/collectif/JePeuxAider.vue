<template>
  <div class="collectif-roles" role="group" aria-label="Je peux aider">
    <button v-for="r in roles" :key="r.valeur" class="collectif-roles__role" :class="{ pris: monRole === r.valeur }"
            :disabled="ferme || (r.valeur === 'garant' && garant && monRole !== 'garant')"
            :title="r.valeur === 'garant' && garant && monRole !== 'garant' ? 'Cette demande a déjà un garant' : r.cout"
            @click="$emit('choisir', r.valeur, r.minutes)">
      {{ r.libelle }} <span>{{ r.cout }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ROLES } from '~/utils/collectif'
withDefaults(defineProps<{ monRole?: string | null; garant?: boolean; ferme?: boolean; roles?: typeof ROLES }>(), { roles: () => ROLES })
defineEmits<{ (e: 'choisir', role: string, minutes: number): void }>()
</script>
