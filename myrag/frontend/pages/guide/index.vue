<template>
  <div class="collectif-guide">
    <h1 class="fr-h2">Soyez acteurs vous-mêmes</h1>
    <p class="fr-text--lead">Cinq pages pour dire ce qui manque, rassembler, amorcer, vérifier et entretenir un jeu de données — chacune finit par le geste dans l'outil et un exemple tiré des premières collections.</p>
    <p v-if="pages === null" class="fr-text--sm">Guide indisponible.</p>
    <ol v-else class="fr-mt-3w">
      <li v-for="p in pages" :key="p.slug" class="fr-mb-2w"><NuxtLink :to="`/guide/${p.slug}`" class="fr-link fr-text--lg">{{ p.titre }}</NuxtLink></li>
    </ol>
    <p class="fr-text--sm" style="color:var(--text-mention-grey)">Ce guide est aussi une collection interrogeable depuis l'assistant, ouverte aux propositions de modification :
      <NuxtLink to="/c/guide-soyez-acteurs" class="fr-link fr-text--sm">guide-soyez-acteurs</NuxtLink>.</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
const { guide } = useCollectif()
const pages = ref<any[] | null>([])
onMounted(async () => { try { pages.value = (await guide()).pages } catch { pages.value = null } })
</script>
