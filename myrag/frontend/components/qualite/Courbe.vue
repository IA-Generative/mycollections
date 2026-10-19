<script setup lang="ts">
import { dateMesure, pointsCourbe } from '~/utils/qualite'

/** La tendance des dernières mesures, à l'échelle 0–100. */
const props = defineProps<{ tendance: { cree_le: string, score: number | null, methode: string }[] }>()
const L = 400
const H = 150
const M = 30
const points = computed(() => pointsCourbe(props.tendance.map(t => t.score), L, H, M))
const y = (v: number) => Math.round(H - M - (v / 100) * (H - 2 * M))
const methodesMelees = computed(() => new Set(props.tendance.map(t => t.methode)).size > 1)
const jour = (iso?: string) => dateMesure(iso, false)
</script>

<template>
  <section
    class="courbe"
    aria-labelledby="courbe-titre"
  >
    <h2
      id="courbe-titre"
      class="fr-h6 fr-mb-1w"
    >
      Dans le temps
    </h2>
    <p
      v-if="points.length < 2"
      class="fr-text--sm fr-mb-0"
    >
      La courbe apparaît à partir de deux mesures. Mesurez à nouveau après chaque changement
      (documents ajoutés, réindexation, consignes) pour voir son effet.
    </p>
    <template v-else>
      <svg
        :viewBox="`0 0 ${L} ${H}`"
        class="courbe__svg"
        role="img"
        :aria-label="`Qualité des ${points.length} dernières mesures : ${points.map(p => p.score).join(', ')} sur 100`"
      >
        <g
          v-for="v in [0, 50, 100]"
          :key="v"
        >
          <line
            :x1="M"
            :x2="L - M / 2"
            :y1="y(v)"
            :y2="y(v)"
            class="courbe__grille"
          />
          <text
            :x="M - 6"
            :y="y(v) + 4"
            text-anchor="end"
            class="courbe__texte"
          >{{ v }}</text>
        </g>
        <polyline
          :points="points.map(p => `${p.x},${p.y}`).join(' ')"
          class="courbe__ligne"
        />
        <circle
          v-for="(p, i) in points"
          :key="i"
          :cx="p.x"
          :cy="p.y"
          r="4"
          class="courbe__point"
        >
          <title>{{ dateMesure(tendance[i]?.cree_le) }} : {{ p.score }} %</title>
        </circle>
        <text
          :x="points[0].x"
          :y="H - 6"
          text-anchor="start"
          class="courbe__texte"
        >{{ jour(tendance[0]?.cree_le) }}</text>
        <text
          :x="points[points.length - 1].x"
          :y="H - 6"
          text-anchor="end"
          class="courbe__texte"
        >{{ jour(tendance[tendance.length - 1]?.cree_le) }}</text>
      </svg>
      <p class="fr-text--xs fr-mb-0 courbe__discret">
        {{ points.length }} dernières mesures terminées.
        <template v-if="methodesMelees">
          Certaines ont été comparées par similarité (juge indisponible) : elles se comparent mal aux autres.
        </template>
      </p>
    </template>
  </section>
</template>

<style scoped>
.courbe__svg { width: 100%; max-width: 100%; height: auto; display: block; }
.courbe__grille { stroke: var(--border-default-grey); stroke-width: 1; }
.courbe__texte { fill: var(--text-mention-grey); font-size: 11px; }
.courbe__ligne { fill: none; stroke: var(--border-action-high-blue-france); stroke-width: 2; }
.courbe__point { fill: var(--background-action-high-blue-france); }
.courbe__discret { color: var(--text-mention-grey); }
</style>
