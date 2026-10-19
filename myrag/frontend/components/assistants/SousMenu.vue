<script setup lang="ts">
import { estActive, sousMenuAssistant } from '~/utils/navigation'

const props = defineProps<{ id: string }>()
const route = useRoute()
const entrees = computed(() => sousMenuAssistant(props.id))
</script>

<template>
  <nav
    class="fr-mb-4w"
    :aria-label="`Rubriques de l'assistant ${id}`"
  >
    <ul class="fr-btns-group fr-btns-group--inline-sm fr-btns-group--sm">
      <li
        v-for="e in entrees"
        :key="e.vers"
      >
        <NuxtLink
          :to="e.vers"
          class="fr-btn fr-btn--sm"
          :class="{ 'fr-btn--secondary': !estActive(e, route.path) }"
          :aria-current="estActive(e, route.path) ? 'page' : undefined"
        >
          {{ e.libelle }}
        </NuxtLink>
      </li>
    </ul>
  </nav>
</template>
