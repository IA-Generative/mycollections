<script setup lang="ts">
import { etatAssistant } from '~/utils/assistants'

/**
 * Le cadre commun des rubriques d'un assistant : titre et état, sous-menu, contenu. Il charge la
 * fiche une fois et la passe à la rubrique (emplacement par défaut). Pas de fil d'Ariane : le menu
 * et le sous-menu disent où l'on est.
 */
const props = defineProps<{ id: string, rubrique: string }>()
const { lire } = useAssistants()
const donnees = ref<any>(null)
const erreur = ref('')

async function recharger () {
  try {
    donnees.value = await lire(props.id)
    erreur.value = ''
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
}
onMounted(recharger)
const etat = computed(() => etatAssistant(donnees.value?.version))
</script>

<template>
  <div>
    <div class="assistant-tete fr-mb-2w">
      <div>
        <p class="fr-text--sm fr-mb-0 assistant-discret">
          <NuxtLink
            to="/assistants"
            class="fr-link fr-text--sm fr-icon-arrow-left-line fr-link--icon-left"
          >
            Assistants de recherche
          </NuxtLink>
        </p>
        <h1 class="fr-h3 fr-mb-0">
          {{ donnees?.fiche?.titre || id }}
          <span
            v-if="donnees"
            class="fr-badge fr-badge--sm fr-badge--no-icon fr-ml-1w"
            :class="etat.classe"
          >{{ etat.libelle }}</span>
        </h1>
        <p
          v-if="donnees?.fiche?.description"
          class="fr-text--sm fr-mb-0 assistant-discret"
        >
          {{ donnees.fiche.description }}
        </p>
      </div>
    </div>
    <AssistantsSousMenu :id="id" />
    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-alert--sm"
      role="alert"
    >
      <p>{{ erreur }}</p>
    </div>
    <slot
      v-else-if="donnees"
      :donnees="donnees"
      :recharger="recharger"
    >
      <p class="fr-text--sm">
        La rubrique « {{ rubrique }} » arrive avec un prochain incrément.
      </p>
    </slot>
    <p
      v-else
      class="fr-text--sm"
    >
      Chargement…
    </p>
  </div>
</template>

<style scoped>
.assistant-tete { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 1rem; }
.assistant-discret { color: var(--text-mention-grey); }
</style>
