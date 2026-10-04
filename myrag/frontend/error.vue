<template>
  <NuxtLayout>
    <div class="fr-container fr-my-7w">
      <h1 class="fr-h2">{{ inconnue ? 'Page introuvable' : 'Une erreur est survenue' }}</h1>
      <p class="fr-text--lead">
        {{ inconnue
          ? "Cette page n'existe pas, ou plus. L'adresse est peut-être mal saisie, ou la collection a été archivée."
          : "La page n'a pas pu s'afficher. Réessayez ; si l'erreur revient, dites-le dans « Mon avis »." }}
      </p>
      <ul class="fr-btns-group fr-btns-group--inline-md">
        <li><button class="fr-btn" @click="accueil">Retour à l'accueil</button></li>
        <li><NuxtLink to="/admin/catalog" class="fr-btn fr-btn--secondary" @click="clearError()">Voir le catalogue</NuxtLink></li>
      </ul>
    </div>
  </NuxtLayout>
</template>

<script setup lang="ts">
/** La page d'erreur de l'application (avant : la page par défaut de Nuxt, en anglais). */
const props = defineProps<{ error: { statusCode?: number } }>()
const inconnue = computed(() => (props.error?.statusCode ?? 404) === 404)
useHead({ title: inconnue.value ? 'Page introuvable — Mes collections' : 'Erreur — Mes collections' })
function accueil() { clearError({ redirect: '/' }) }
</script>
