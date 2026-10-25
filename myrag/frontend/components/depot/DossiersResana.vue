<script setup lang="ts">
/**
 * Cocher les dossiers d'un espace Résana à indexer (docs/resana.md). Un dossier coché emporte tout
 * son contenu : ses sous-dossiers apparaissent cochés et grisés. Une recherche filtre l'arbre en
 * gardant le chemin de chaque dossier trouvé. Sous l'arbre, les dossiers choisis, avec le nombre de
 * documents de chacun (un grand dossier se prépare côté Résana : « préparation… »).
 */
import type { DossierResana, ErreurResana } from '~/utils/resana'
import { ancetres, arbreDossiers, basculerDossier, dossiersVisibles, erreurResana, inclusParUnParent, preparation } from '~/utils/resana'

const props = withDefaults(defineProps<{
  espace: string
  /** Résana (l'espace), ou Fichiers (l'instance) : mêmes routes sous `/api/sources/<source>`. */
  source?: 'resana' | 'fichiers'
}>(), { source: 'resana' })
const emit = defineEmits<{ dossiers: [{ id: string, chemin: string }[]] }>()
const base = computed(() => `/api/sources/${props.source}`)
const choisis = defineModel<string[]>({ default: () => [] })
const { get } = useApi()
const champ = useId()
const dossiers = ref<DossierResana[]>([])
const charge = ref(false)
const erreur = ref<ErreurResana | null>(null)
const recherche = ref('')
const ouverts = ref<Set<string>>(new Set())
/** Les comptes des dossiers choisis : nombre de documents, ou l'état de la préparation. */
const comptes = ref<Record<string, { total?: number, preparation?: string, erreur?: string }>>({})
const rappels = new Map<string, ReturnType<typeof setTimeout>>()

const ensemble = computed(() => new Set(choisis.value))
const arbre = computed(() => arbreDossiers(dossiers.value))
const visibles = computed(() => dossiersVisibles(dossiers.value, recherche.value))
const parId = computed(() => new Map(dossiers.value.map(d => [d.id, d])))
const choix = computed(() => choisis.value.map(id => parId.value.get(id)).filter((d): d is DossierResana => !!d))
const total = computed(() => choix.value.reduce((n, d) => n + (comptes.value[d.id]?.total ?? 0), 0))
const comptesPrets = computed(() => choix.value.every(d => typeof comptes.value[d.id]?.total === 'number'))

/** Les lignes affichées, à plat (profondeur pour le retrait) : dépliées, ou trouvées par la recherche. */
const lignes = computed(() => {
  const rendu: { d: DossierResana, profondeur: number, parent: boolean }[] = []
  const filtre = visibles.value
  const descendre = (liste: DossierResana[], profondeur: number) => {
    for (const d of liste) {
      if (filtre && !filtre.has(d.id)) {
        continue
      }
      const enfants = arbre.value.enfants.get(d.id) || []
      rendu.push({ d, profondeur, parent: enfants.length > 0 })
      if (filtre || ouverts.value.has(d.id)) {
        descendre(enfants, profondeur + 1)
      }
    }
  }
  descendre(arbre.value.racines, 0)
  return rendu
})

async function charger () {
  charge.value = true
  erreur.value = null
  try {
    dossiers.value = (await get(`${base.value}/espaces/${encodeURIComponent(props.espace)}/dossiers`)).dossiers || []
    // Une sélection existante (« Modifier la sélection ») : ses dossiers sont visibles d'emblée.
    ouverts.value = new Set(choisis.value.flatMap(id => ancetres(id, dossiers.value)))
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    charge.value = false
  }
}

async function compter (id: string) {
  clearTimeout(rappels.get(id))
  try {
    const r = await get(`${base.value}/espaces/${encodeURIComponent(props.espace)}/apercu`, { dossier: id })
    if (!ensemble.value.has(id)) {
      return
    }
    if (r.en_preparation) {
      comptes.value = { ...comptes.value, [id]: { preparation: `préparation chez Résana${preparation(r.dossiers_lus, r.dossiers)}…` } }
      rappels.set(id, setTimeout(compter, 5000, id))
      return
    }
    comptes.value = { ...comptes.value, [id]: { total: r.total } }
  }
  catch (e) {
    comptes.value = { ...comptes.value, [id]: { erreur: erreurResana(e).message } }
  }
}

function cocher (d: DossierResana) {
  choisis.value = [...basculerDossier(d.id, ensemble.value, dossiers.value)]
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

watch(choix, (liste) => {
  emit('dossiers', liste.map(d => ({ id: d.id, chemin: d.chemin || d.titre })))
  for (const d of liste) {
    if (!comptes.value[d.id]) {
      comptes.value = { ...comptes.value, [d.id]: {} }
      compter(d.id)
    }
  }
}, { immediate: true })

watch(() => props.espace, () => {
  choisis.value = []
  comptes.value = {}
  ouverts.value = new Set()
  charger()
})

onMounted(charger)
onBeforeUnmount(() => {
  for (const t of rappels.values()) {
    clearTimeout(t)
  }
})
</script>

<template>
  <fieldset
    class="dossiers"
    :aria-labelledby="`${champ}-legende`"
  >
    <legend
      :id="`${champ}-legende`"
      class="dossiers__legende"
    >
      <span class="fr-h6 fr-mb-0">Que faut-il indexer ?</span>
      <span class="fr-hint-text">
        Cochez seulement ce qui sert : un dossier coché emporte ses sous-dossiers. Chaque document de plus allonge l'import
        et peut mêler aux réponses des textes hors sujet. Seuls les documents que vous pouvez ouvrir dans {{ source === 'fichiers' ? 'Fichiers' : 'Résana' }} seront
        indexés. La sélection se modifie ensuite depuis la collection.
      </span>
    </legend>

    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
      role="alert"
    >
      <p>{{ erreur.message }}</p>
    </div>
    <p
      v-else-if="charge"
      class="fr-text--sm"
      role="status"
    >
      Lecture des dossiers de l'espace…
    </p>

    <template v-else>
      <div class="fr-input-group fr-mb-1w dossiers__recherche">
        <label
          class="fr-label"
          :for="`${champ}-recherche`"
        >Rechercher un dossier</label>
        <input
          :id="`${champ}-recherche`"
          v-model="recherche"
          class="fr-input"
          type="search"
          placeholder="Rechercher un dossier…"
          autocomplete="off"
        >
      </div>

      <ul
        v-if="lignes.length"
        class="dossiers__liste"
      >
        <li
          v-for="l in lignes"
          :key="l.d.id"
          class="dossiers__ligne"
          :style="{ paddingLeft: `${l.profondeur * 1.25}rem` }"
        >
          <button
            v-if="l.parent && !visibles"
            type="button"
            class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
            :class="ouverts.has(l.d.id) ? 'fr-icon-arrow-down-s-line' : 'fr-icon-arrow-right-s-line'"
            :aria-expanded="ouverts.has(l.d.id) ? 'true' : 'false'"
            :title="`${ouverts.has(l.d.id) ? 'Replier' : 'Déplier'} ${l.d.titre}`"
            @click="deplier(l.d.id)"
          >
            {{ ouverts.has(l.d.id) ? 'Replier' : 'Déplier' }} {{ l.d.titre }}
          </button>
          <span
            v-else
            class="dossiers__vide"
            aria-hidden="true"
          />
          <div class="fr-checkbox-group fr-checkbox-group--sm dossiers__case">
            <input
              :id="`${champ}-${l.d.id}`"
              type="checkbox"
              :checked="ensemble.has(l.d.id) || inclusParUnParent(l.d.id, ensemble, dossiers)"
              :disabled="inclusParUnParent(l.d.id, ensemble, dossiers)"
              @change="cocher(l.d)"
            >
            <label
              class="fr-label"
              :for="`${champ}-${l.d.id}`"
            >
              {{ l.d.titre }}
              <span
                v-if="visibles"
                class="fr-hint-text"
              >{{ l.d.chemin }}</span>
            </label>
          </div>
        </li>
      </ul>
      <p
        v-else
        class="fr-text--sm"
      >
        {{ recherche.trim() ? 'Aucun dossier ne correspond.' : 'Cet espace n\'a pas de dossier.' }}
      </p>

      <div
        class="dossiers__choix fr-mt-2w"
        aria-live="polite"
      >
        <p class="fr-text--sm fr-mb-1w">
          <strong>{{ choix.length }} dossier{{ choix.length > 1 ? 's' : '' }} choisi{{ choix.length > 1 ? 's' : '' }}</strong>
          <template v-if="choix.length && comptesPrets">
            — {{ total }} document{{ total > 1 ? 's' : '' }}
          </template>
        </p>
        <ul
          v-if="choix.length"
          class="fr-tags-group"
        >
          <li
            v-for="d in choix"
            :key="d.id"
          >
            <button
              type="button"
              class="fr-tag fr-tag--sm fr-tag--dismiss"
              :aria-label="`Retirer ${d.chemin}`"
              @click="cocher(d)"
            >
              {{ d.chemin || d.titre }}
              <template v-if="typeof comptes[d.id]?.total === 'number'">
                · {{ comptes[d.id]!.total }}
              </template>
              <template v-else-if="comptes[d.id]?.preparation">
                · {{ comptes[d.id]!.preparation }}
              </template>
            </button>
          </li>
        </ul>
      </div>
    </template>
  </fieldset>
</template>

<style scoped>
.dossiers { border: 0; padding: 0; margin: 0; min-width: 0; }
.dossiers__legende { float: left; width: 100%; padding: 0; margin: 0 0 .75rem; }
.dossiers__legende + * { clear: both; }
.dossiers__recherche { max-width: 32rem; }
.dossiers__liste { list-style: none; margin: 0; padding: .5rem 0; max-height: 20rem; overflow-y: auto; border: 1px solid var(--border-default-grey); }
.dossiers__ligne { display: flex; align-items: flex-start; gap: .25rem; padding-right: .5rem; }
.dossiers__vide { width: 2rem; min-width: 2rem; }
.dossiers__case { flex: 1; }
</style>
