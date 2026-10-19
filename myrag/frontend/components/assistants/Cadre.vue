<script setup lang="ts">
/** Le cadre commun des rubriques d'un assistant : fil d'Ariane, titre, sous-menu, contenu. */
defineProps<{ id: string, rubrique: string }>()
</script>

<template>
  <div>
    <nav
      role="navigation"
      class="fr-breadcrumb"
      aria-label="vous êtes ici :"
    >
      <ol class="fr-breadcrumb__list">
        <li>
          <NuxtLink
            class="fr-breadcrumb__link"
            to="/"
          >
            Accueil
          </NuxtLink>
        </li>
        <li>
          <NuxtLink
            class="fr-breadcrumb__link"
            to="/assistants"
          >
            Assistants
          </NuxtLink>
        </li>
        <li>
          <a
            class="fr-breadcrumb__link"
            aria-current="page"
          >{{ id }} — {{ rubrique }}</a>
        </li>
      </ol>
    </nav>
    <p class="fr-text--sm fr-mb-1w">
      Assistant « {{ id }} »
    </p>
    <h1 class="fr-h3">
      {{ rubrique }}
    </h1>
    <AssistantsSousMenu :id="id" />
    <slot>
      <p>Cette page arrive avec un prochain incrément.</p>
    </slot>
  </div>
</template>
