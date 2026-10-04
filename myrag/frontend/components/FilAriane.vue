<template>
  <!-- Le fil d'Ariane DSFR complet. Nous ne chargeons pas le JavaScript du DSFR : c'est Vue qui
       ouvre le volet sur petit écran (bouton « Voir le fil d'Ariane »). Au-delà de 48em, le DSFR
       cache le bouton et montre toujours la liste. -->
  <nav role="navigation" class="fr-breadcrumb" aria-label="vous êtes ici :">
    <button type="button" class="fr-breadcrumb__button" :aria-expanded="ouvert" :aria-controls="idVolet" @click="ouvert = true">
      Voir le fil d’Ariane
    </button>
    <div :id="idVolet" class="fr-collapse" :class="{ 'fr-collapse--expanded': ouvert }">
      <ol class="fr-breadcrumb__list">
        <li v-for="(m, i) in maillons" :key="i">
          <NuxtLink v-if="m.vers" class="fr-breadcrumb__link" :to="m.vers">{{ m.libelle }}</NuxtLink>
          <a v-else class="fr-breadcrumb__link" aria-current="page">{{ m.libelle }}</a>
        </li>
      </ol>
    </div>
  </nav>
</template>

<script setup lang="ts">
/** Accueil › Catalogue › {collection} › {rubrique} — le même fil sur toutes les pages d'une collection. */
import { maillonsFil } from '~/utils/filAriane'

const props = defineProps<{
  /** Identifiant de la collection (celui de l'adresse `/c/…`). */
  collection: string
  /** Titre affiché de la collection. */
  titre: string
  /** La rubrique ou l'onglet où l'on est ; absent, la collection est la page courante. */
  rubrique?: string
}>()

const idVolet = 'fil-ariane-volet'
const ouvert = ref(false)
const maillons = computed(() => maillonsFil(props.collection, props.titre, props.rubrique))
</script>
