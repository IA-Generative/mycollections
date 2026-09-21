<template>
  <div class="collectif-roles" role="group" aria-label="Je peux aider">
    <!-- L'auteur : un rôle tenu, pas un bouton. -->
    <span v-if="jeSuisDemandeur" class="collectif-roles__role pris collectif-roles__role--tenu"
          :title="`Vous avez déposé cette demande : ${ROLE_DEMANDEUR.cout}, et vous confirmerez qu'elle répond à votre besoin.`">
      {{ ROLE_DEMANDEUR.libelle }} <span>{{ ROLE_DEMANDEUR.cout }}</span>
    </span>
    <button v-for="r in roles" :key="r.valeur" class="collectif-roles__role" :class="{ pris: monRole === r.valeur }"
            :disabled="ferme || (r.valeur === 'garant' && garant && monRole !== 'garant')"
            :title="r.valeur === 'garant' && garant && monRole !== 'garant' ? 'Cette demande a déjà un garant' : r.cout"
            @click="$emit('choisir', r.valeur, r.minutes)">
      {{ r.libelle }} <span>{{ r.cout }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ROLES, ROLE_DEMANDEUR } from '~/utils/collectif'
withDefaults(defineProps<{ monRole?: string | null; garant?: boolean; ferme?: boolean; jeSuisDemandeur?: boolean; roles?: typeof ROLES }>(), { roles: () => ROLES })
defineEmits<{ (e: 'choisir', role: string, minutes: number): void }>()
</script>
