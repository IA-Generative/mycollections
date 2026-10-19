<script setup lang="ts">
import { dateFiche } from '~/utils/fiche'

/**
 * « Ce qu'en pensent vos collègues » : la satisfaction (tous les lecteurs), l'usage sur la
 * fenêtre (sous le seuil, le serveur ne donne pas de nombre de personnes), et pour qui gère les
 * trois derniers avis et ceux à relire. Aucun texte d'avis n'est interprété comme du HTML.
 */
const props = defineProps<{
  id: string
  stats: { total: number, satisfaction_rate: number, pending_review: number } | null
  usage: { fenetre_jours: number, questions: number, personnes: number | null } | null
  derniers: { id: number, question: string, reason?: string, rating: number, created_at: string }[] | null
  peutGerer: boolean
}>()

const taux = computed(() => props.stats && props.stats.total ? Math.round(props.stats.satisfaction_rate * 100) : null)
</script>

<template>
  <section
    class="fiche-bloc"
    aria-labelledby="titre-avis-collegues"
  >
    <h2
      id="titre-avis-collegues"
      class="fr-h5"
    >
      <span
        class="fr-icon-thumb-up-line fr-mr-1w"
        aria-hidden="true"
      />Ce qu'en pensent vos collègues
    </h2>
    <dl class="fiche-kpis">
      <div>
        <dt class="fr-sr-only">
          Satisfaction
        </dt>
        <dd v-if="taux !== null">
          <b>{{ taux }} %</b><span>de réponses jugées utiles, sur {{ stats!.total }} avis</span>
        </dd>
        <dd v-else>
          <b>—</b><span>pas encore d'avis</span>
        </dd>
      </div>
      <div v-if="usage">
        <dt class="fr-sr-only">
          Questions
        </dt>
        <dd><b>{{ usage.questions }}</b><span>question{{ usage.questions > 1 ? 's' : '' }} posée{{ usage.questions > 1 ? 's' : '' }} en {{ usage.fenetre_jours }} jours</span></dd>
      </div>
      <div v-if="usage && usage.personnes">
        <dt class="fr-sr-only">
          Collègues aidés
        </dt>
        <dd><b>{{ usage.personnes }}</b><span>collègues aidés</span></dd>
      </div>
    </dl>

    <ul
      v-if="peutGerer && derniers && derniers.length"
      class="fiche-avis"
      aria-label="Les derniers avis"
    >
      <li
        v-for="a in derniers"
        :key="a.id"
      >
        <span
          :class="a.rating > 0 ? 'fr-icon-thumb-up-line fiche-avis--positif' : 'fr-icon-thumb-down-line fiche-avis--negatif'"
          class="fr-icon--sm"
          :aria-label="a.rating > 0 ? 'Avis positif' : 'Avis négatif'"
          role="img"
        />
        <div>
          <span class="fiche-avis__question">« {{ a.question }} »</span>
          <span
            v-if="a.reason"
            class="fr-text--sm fiche-avis__motif"
          >{{ a.reason }}</span>
          <span class="fr-text--xs fiche-discret"> · {{ dateFiche(a.created_at, false) }}</span>
        </div>
      </li>
    </ul>

    <div
      v-if="peutGerer"
      class="fiche-bloc__actions"
    >
      <NuxtLink
        v-if="stats && stats.pending_review > 0"
        :to="`/c/${id}/qualite?onglet=avis`"
        class="fr-btn fr-btn--secondary fr-btn--sm"
      >
        {{ stats.pending_review }} avis à relire
      </NuxtLink>
      <NuxtLink
        :to="`/c/${id}/qualite?onglet=avis`"
        class="fr-link fr-text--sm"
      >
        Tous les avis
      </NuxtLink>
    </div>
  </section>
</template>
