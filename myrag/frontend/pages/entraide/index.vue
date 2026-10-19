<script setup lang="ts">
definePageMeta({ middleware: 'capacite', capacite: 'entraide' })
useHead({ title: 'Réseau d\'entraide — Mes collections' })
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
          >Réseau d'entraide</a>
        </li>
      </ol>
    </nav>
    <h1 class="fr-h2">
      Réseau d'entraide
    </h1>
    <p class="fr-text--lead">
      Lancer un appel à l'aide : le réseau propose d'abord ce qui existe, puis des personnes, puis un lieu pour échanger.
    </p>
    <p>Cette page arrive avec un prochain incrément.</p>
  </div>
</template>
