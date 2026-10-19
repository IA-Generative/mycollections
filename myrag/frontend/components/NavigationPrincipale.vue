<script setup lang="ts">
import { entreesPrincipales, estActive } from '~/utils/navigation'

const props = defineProps<{
  /** Le droit d'administration, chargé par le gabarit (`useAdminAuth`). */
  admin: boolean
}>()

const route = useRoute()
// L'état partagé des capacités : le gabarit le charge, ce composant ne fait que le lire.
const { capacites } = useCapacites()
const entrees = computed(() => entreesPrincipales(capacites.value, props.admin))
</script>

<template>
  <!-- La navigation principale : ses entrées viennent de utils/navigation.ts (testées), selon les
       capacités du service et le droit d'administration. Le gabarit y glisse, en fin de liste, le
       menu « Mes collections » (il en charge le contenu une fois la session ouverte). -->
  <nav
    class="fr-nav"
    role="navigation"
    aria-label="Navigation principale"
  >
    <ul class="fr-nav__list">
      <li
        v-for="e in entrees"
        :key="e.vers"
        class="fr-nav__item"
      >
        <NuxtLink
          :to="e.vers"
          class="fr-nav__link"
          :aria-current="estActive(e, route.path) ? 'page' : undefined"
        >
          {{ e.libelle }}
        </NuxtLink>
      </li>
      <slot />
    </ul>
  </nav>
</template>
