<script setup lang="ts">
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
useHead({ title: 'Assistants — Mes collections' })
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
          <a
            class="fr-breadcrumb__link"
            aria-current="page"
          >Assistants</a>
        </li>
      </ol>
    </nav>
    <h1 class="fr-h2">
      Assistants
    </h1>
    <p class="fr-text--lead">
      Un assistant de recherche interroge plusieurs sources — collections et connecteurs — selon des consignes, et sert d'abord les réponses fiables.
    </p>
    <p>Cette page arrive avec un prochain incrément.</p>
  </div>
</template>
