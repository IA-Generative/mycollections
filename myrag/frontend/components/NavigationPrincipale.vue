<script setup lang="ts">
import { entreesPrincipales, estActive } from '~/utils/navigation'

const props = defineProps<{
  /** Le droit d'administration, chargé par le gabarit (`useAdminAuth`). */
  admin: boolean
  /** Le nombre de collections que je gère : la pastille de « Mes collections ». */
  compteMiennes?: number | null
}>()

const route = useRoute()
// L'état partagé des capacités : le gabarit le charge, ce composant ne fait que le lire.
const { capacites } = useCapacites()
const entrees = computed(() => entreesPrincipales(capacites.value, props.admin))
</script>

<template>
  <!-- La navigation principale : ses entrées viennent de utils/navigation.ts (testées), selon les
       capacités du service et le droit d'administration. « Mes collections » mène à la liste et
       porte une pastille (le nombre de collections que je gère), sans volet. -->
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
          <!-- Icône, libellé et pastille dans un seul bloc : sur mobile, le DSFR écarte les enfants du lien. -->
          <span class="nav-entree">
            <span
              v-if="e.icone"
              class="fr-icon--sm fr-mr-1v"
              :class="[e.icone]"
              aria-hidden="true"
            />{{ e.libelle }}
            <span
              v-if="e.pastille && compteMiennes"
              class="nav-entree__pastille"
              :aria-label="`${compteMiennes} collection${compteMiennes > 1 ? 's' : ''} que vous gérez`"
            >{{ compteMiennes }}</span>
          </span>
        </NuxtLink>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.nav-entree { display: inline-flex; align-items: center; gap: .4rem; }
/* Une pastille discrète : un compteur, pas un appel à l'action. */
.nav-entree__pastille {
  min-width: 1.4em; padding: 0 .4em; border-radius: 1em; text-align: center;
  font-size: .75rem; font-weight: 700; font-variant-numeric: tabular-nums;
  background: var(--background-contrast-grey); color: var(--text-default-grey);
}
</style>
