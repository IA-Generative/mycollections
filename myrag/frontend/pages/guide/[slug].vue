<template>
  <div class="collectif-guide">
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous êtes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/guide">Soyez acteurs vous-mêmes</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">{{ page ? page.titre : slug }}</a></li>
      </ol>
    </nav>
    <div v-if="page === null" class="fr-alert fr-alert--warning"><p>Page introuvable.</p></div>
    <div v-else-if="page" v-html="html"></div>
    <div v-if="pages" class="fr-btns-group fr-btns-group--inline fr-mt-4w">
      <NuxtLink v-if="precedent" :to="`/guide/${precedent.slug}`" class="fr-btn fr-btn--secondary fr-btn--sm">← {{ precedent.titre }}</NuxtLink>
      <NuxtLink v-if="suivant" :to="`/guide/${suivant.slug}`" class="fr-btn fr-btn--sm">{{ suivant.titre }} →</NuxtLink>
      <NuxtLink to="/c/guide-soyez-acteurs" class="fr-btn fr-btn--tertiary fr-btn--sm">Proposer une modification de cette page</NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { renderMarkdownSafe } from '~/utils/sanitize'
const route = useRoute()
const slug = computed(() => route.params.slug as string)
const { guide, pageGuide } = useCollectif()
const page = ref<any>(undefined)
const pages = ref<any[] | null>(null)
const html = computed(() => renderMarkdownSafe(page.value?.markdown))
const index = computed(() => (pages.value || []).findIndex(p => p.slug === slug.value))
const precedent = computed(() => (index.value > 0 ? pages.value![index.value - 1] : null))
const suivant = computed(() => (pages.value && index.value >= 0 && index.value < pages.value.length - 1 ? pages.value[index.value + 1] : null))
async function charger() { try { page.value = await pageGuide(slug.value) } catch { page.value = null } }
onMounted(async () => { await charger(); try { pages.value = (await guide()).pages } catch { pages.value = null } })
watch(slug, charger)
</script>
