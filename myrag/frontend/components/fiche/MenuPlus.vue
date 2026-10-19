<script setup lang="ts">
import type { ActionFiche } from '~/utils/fiche'

/**
 * Le menu « Plus » de la fiche : un bouton à divulgation (motif « disclosure »), une liste de
 * liens. Échap le ferme et rend le focus au bouton ; quitter le menu au clavier ou cliquer
 * ailleurs le ferme aussi.
 */
defineProps<{ actions: ActionFiche[] }>()

const ouvert = ref(false)
const bouton = ref<HTMLButtonElement | null>(null)
const racine = ref<HTMLElement | null>(null)

function fermer (rendreLeFocus: boolean) {
  ouvert.value = false
  if (rendreLeFocus) {
    nextTick(() => bouton.value?.focus())
  }
}

function surEchap (e: KeyboardEvent) {
  if (ouvert.value) {
    e.stopPropagation()
    fermer(true)
  }
}

function surSortie (e: FocusEvent) {
  const vers = e.relatedTarget as Node | null
  if (vers && racine.value && !racine.value.contains(vers)) {
    fermer(false)
  }
}

function surClicAilleurs (e: MouseEvent) {
  if (ouvert.value && racine.value && !racine.value.contains(e.target as Node)) {
    fermer(false)
  }
}
onMounted(() => document.addEventListener('click', surClicAilleurs))
onBeforeUnmount(() => document.removeEventListener('click', surClicAilleurs))
</script>

<template>
  <div
    ref="racine"
    class="menu-plus"
    @keydown.esc="surEchap"
    @focusout="surSortie"
  >
    <button
      ref="bouton"
      type="button"
      class="fr-btn fr-btn--tertiary fr-btn--icon-right fr-icon-arrow-down-s-line"
      aria-controls="menu-plus-liste"
      :aria-expanded="ouvert ? 'true' : 'false'"
      @click="ouvert = !ouvert"
    >
      Plus
    </button>
    <ul
      v-show="ouvert"
      id="menu-plus-liste"
      class="menu-plus__liste"
      aria-label="Plus d'actions"
    >
      <li
        v-for="a in actions"
        :key="a.cle"
      >
        <span
          v-if="a.desactivee"
          class="menu-plus__item menu-plus__item--inactif"
          aria-disabled="true"
          :title="a.aide"
        >
          <span
            class="fr-icon--sm"
            :class="[a.icone]"
            aria-hidden="true"
          />
          {{ a.libelle }}
          <span class="fr-sr-only">({{ a.aide }})</span>
        </span>
        <NuxtLink
          v-else
          :to="a.vers"
          class="menu-plus__item"
          :title="a.aide"
          @click="fermer(false)"
        >
          <span
            class="fr-icon--sm"
            :class="[a.icone]"
            aria-hidden="true"
          />
          {{ a.libelle }}
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.menu-plus { position: relative; display: inline-block; }
.menu-plus__liste {
  position: absolute; right: 0; top: 100%; z-index: 750; min-width: 16rem; margin: .25rem 0 0; padding: .25rem 0;
  list-style: none; background: var(--background-overlap-grey); border: 1px solid var(--border-default-grey);
}
.menu-plus__liste li { padding: 0; }
.menu-plus__item { display: flex; align-items: center; gap: .5rem; padding: .6rem 1rem; background-image: none; color: var(--text-default-grey); }
a.menu-plus__item:hover { background-color: var(--background-alt-grey); }
.menu-plus__item--inactif { color: var(--text-disabled-grey); cursor: not-allowed; }
@media (max-width: 36em) { .menu-plus__liste { left: 0; right: auto; } }
</style>
