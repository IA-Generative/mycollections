<script setup lang="ts">
/**
 * Choisir les sous-dossiers Résana à indexer, avec le nombre de documents de chacun
 * (docs/resana.md). Le choix s'écrit en exclusions : un dossier décoché sort de l'index avec tout
 * ce qu'il contient ; un sous-dossier créé plus tard dans un dossier coché y entrera de lui-même.
 */
import type { InventaireResana, NoeudResana } from '~/utils/resana'
import { basculer, estExclu, exclusParUnParent, selection } from '~/utils/resana'

const props = defineProps<{ inventaire: InventaireResana }>()
const exclus = defineModel<string[]>({ default: () => [] })

const champ = useId()
const ensemble = computed(() => new Set(exclus.value))
const noeuds = computed(() => props.inventaire.dossiers)
const parents = computed(() => new Set(noeuds.value.map(n => n.parent_id).filter(Boolean) as string[]))
/** Les dossiers dépliés ; au départ, seul le premier niveau se voit. */
const ouverts = ref<Set<string>>(new Set())
const retenus = computed(() => selection(props.inventaire, ensemble.value))
const resteDeLaPhrase = computed(() => {
  const n = noeuds.value.length
  const d = retenus.value.dossiers
  return `sur ${props.inventaire.total}${n ? `, dans ${d} sous-dossier${d > 1 ? 's' : ''} sur ${n}` : ''}.`
})

function visible (n: NoeudResana): boolean {
  const parDossier = new Map(noeuds.value.map(x => [x.id, x.parent_id]))
  let p = n.parent_id
  while (p && parDossier.has(p)) {
    if (!ouverts.value.has(p)) {
      return false
    }
    p = parDossier.get(p) ?? null
  }
  return true
}

function deplier (id: string) {
  const s = new Set(ouverts.value)
  if (s.has(id)) {
    s.delete(id)
  }
  else {
    s.add(id)
  }
  ouverts.value = s
}

function cocher (n: NoeudResana) {
  exclus.value = [...basculer(n.id, ensemble.value, noeuds.value)].sort()
}

function tout (garder: boolean) {
  exclus.value = garder ? [] : noeuds.value.filter(n => n.profondeur === 0).map(n => n.id).sort()
}
</script>

<template>
  <fieldset
    class="fr-fieldset arbre"
    :aria-labelledby="`${champ}-legende`"
  >
    <legend
      :id="`${champ}-legende`"
      class="fr-fieldset__legend fr-text--md"
    >
      Que faut-il indexer ?
      <span class="fr-hint-text">
        Indexez seulement ce qui sert. Chaque document de plus allonge l'import et les mises à jour, et peut mêler aux
        réponses des textes hors sujet. Vous pourrez ajouter des dossiers plus tard, depuis la page de la collection.
      </span>
    </legend>

    <p
      class="fr-fieldset__element fr-text--sm fr-mb-1w"
      aria-live="polite"
    >
      <strong>Sélection : {{ retenus.documents }} document{{ retenus.documents > 1 ? 's' : '' }}</strong>
      {{ resteDeLaPhrase }}
      <template v-if="inventaire.documents_a_la_racine">
        Les {{ inventaire.documents_a_la_racine }} document{{ inventaire.documents_a_la_racine > 1 ? 's' : '' }} rangés directement dans le dossier sont toujours indexés.
      </template>
    </p>
    <ul
      v-if="noeuds.length"
      class="fr-fieldset__element fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mb-1w"
    >
      <li>
        <button
          type="button"
          class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
          @click="tout(true)"
        >
          Tout cocher
        </button>
      </li>
      <li>
        <button
          type="button"
          class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
          @click="tout(false)"
        >
          Tout décocher
        </button>
      </li>
    </ul>

    <ul
      v-if="noeuds.length"
      class="fr-fieldset__element arbre__liste"
    >
      <template
        v-for="n in noeuds"
        :key="n.id"
      >
        <li
          v-if="visible(n)"
          class="arbre__ligne"
          :style="{ paddingLeft: `${n.profondeur * 1.5}rem` }"
        >
          <button
            v-if="parents.has(n.id)"
            type="button"
            class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
            :class="ouverts.has(n.id) ? 'fr-icon-arrow-down-s-line' : 'fr-icon-arrow-right-s-line'"
            :aria-expanded="ouverts.has(n.id) ? 'true' : 'false'"
            :title="ouverts.has(n.id) ? `Replier ${n.titre}` : `Déplier ${n.titre}`"
            @click="deplier(n.id)"
          >
            {{ ouverts.has(n.id) ? 'Replier' : 'Déplier' }} {{ n.titre }}
          </button>
          <span
            v-else
            class="arbre__vide"
            aria-hidden="true"
          />
          <div class="fr-checkbox-group fr-checkbox-group--sm arbre__case">
            <input
              :id="`${champ}-${n.id}`"
              type="checkbox"
              :checked="!estExclu(n.id, ensemble, noeuds)"
              :disabled="exclusParUnParent(n, ensemble, noeuds)"
              @change="cocher(n)"
            >
            <label
              class="fr-label"
              :for="`${champ}-${n.id}`"
            >
              {{ n.titre }}
              <span class="fr-hint-text">
                {{ n.documents_total }} document{{ n.documents_total > 1 ? 's' : '' }}<template v-if="n.taille_approx_mo">
                  · environ {{ Math.max(1, Math.round(n.taille_approx_mo)) }} Mo
                </template>
              </span>
            </label>
          </div>
        </li>
      </template>
    </ul>
  </fieldset>
</template>

<style scoped>
.arbre__liste { list-style: none; padding: 0; margin: 0; max-height: 24rem; overflow-y: auto; border: 1px solid var(--border-default-grey); padding-block: .5rem; }
.arbre__ligne { display: flex; align-items: flex-start; gap: .25rem; padding-right: .5rem; }
.arbre__vide { width: 2rem; min-width: 2rem; }
.arbre__case { flex: 1; }
</style>
