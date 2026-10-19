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
       capacités du service et le droit d'administration. L'entrée-volet « Mes collections » est
       rendue par le gabarit (emplacement `volet`), qui en charge le contenu. -->
  <nav
    class="fr-nav"
    role="navigation"
    aria-label="Navigation principale"
  >
    <ul class="fr-nav__list">
      <template
        v-for="e in entrees"
        :key="e.vers"
      >
        <slot
          v-if="e.volet"
          name="volet"
          :entree="e"
          :courante="estActive(e, route.path)"
        />
        <li
          v-else
          class="fr-nav__item"
        >
          <NuxtLink
            :to="e.vers"
            class="fr-nav__link"
            :aria-current="estActive(e, route.path) ? 'page' : undefined"
          >
            <!-- Icône et libellé dans un seul bloc : sur mobile, le DSFR écarte les enfants du lien. -->
            <span>
              <span
                v-if="e.icone"
                class="fr-icon--sm fr-mr-1v"
                :class="[e.icone]"
                aria-hidden="true"
              />{{ e.libelle }}
            </span>
          </NuxtLink>
        </li>
      </template>
    </ul>
  </nav>
</template>
