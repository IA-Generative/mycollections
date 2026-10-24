<script setup lang="ts">
/**
 * Où en est une collection Résana (docs/resana.md) : le dossier relié, ce que l'index en couvre
 * (complet ou partiel, et pourquoi), l'import ou la mise à jour en cours, l'invitation à mettre à
 * jour un index ancien, et — pour la personne qui a importé — « Mettre à jour » et « Modifier la
 * sélection » (ajouter ou retirer des sous-dossiers, pour poursuivre l'indexation).
 */
import type { AvisResana, CouvertureResana, ErreurResana, StatutResana } from '~/utils/resana'
import { erreurResana, etiquetteResana, libelleTravail, phraseCouverture, travailEnCours } from '~/utils/resana'

const props = defineProps<{ collection: string }>()

type Statut = StatutResana & CouvertureResana & {
  espace_id?: string | null
  espace?: { id: string, nom: string, entite?: string } | null
  dossiers?: { id: string, chemin: string }[]
  exclus: string[]
  avis?: AvisResana | null
}

const route = useRoute()
const { get, post } = useApi()
const statut = ref<Statut | null>(null)
const erreur = ref<ErreurResana | null>(null)
const envoi = ref(false)
const bouton = ref<HTMLButtonElement | null>(null)
let minuterie: ReturnType<typeof setTimeout> | undefined

const enCours = computed(() => travailEnCours(statut.value?.travail))
const phrase = computed(() => libelleTravail(statut.value?.travail))
const ecartes = computed(() => statut.value?.travail?.documents_ecartes || [])
const derniere = computed(() => {
  const d = statut.value?.last_sync_at
  return d ? new Date(d.endsWith('Z') || d.includes('+') ? d : `${d}Z`).toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'short' }) : ''
})

// ─── Modifier la sélection ───────────────────────────────────────────────────
const edition = ref(false)
const choisis = ref<string[]>([])
const dossiersChoisis = ref<{ id: string, chemin: string }[]>([])

async function charger () {
  clearTimeout(minuterie)
  try {
    statut.value = await get(`/api/sources/resana/status/${encodeURIComponent(props.collection)}`)
  }
  catch (e) {
    erreur.value = erreurResana(e)
    return
  }
  if (enCours.value) {
    minuterie = setTimeout(charger, 3000)
  }
}

async function synchroniser (dossiers?: { id: string, chemin: string }[], complet = false) {
  envoi.value = true
  erreur.value = null
  try {
    // Changer la sélection remplace la liste des dossiers inclus (et efface d'anciennes exclusions).
    const corps = dossiers || complet ? { ...(dossiers ? { dossiers, exclus: [] } : {}), ...(complet ? { complet: true } : {}) } : undefined
    await post(`/api/sources/resana/sync/${encodeURIComponent(props.collection)}`, corps)
    edition.value = false
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    envoi.value = false
  }
  await charger()
}

function ouvrirEdition () {
  choisis.value = (statut.value?.dossiers || []).map(d => d.id)
  edition.value = true
}

function fermerEdition () {
  edition.value = false
}

onMounted(async () => {
  await charger()
  // Venue d'une invitation (« l'index semble ancien ») : le bouton est là, prêt, sans rien lancer seul.
  if (route.query.synchroniser && statut.value?.est_importeur) {
    await nextTick()
    bouton.value?.scrollIntoView({ block: 'center' })
    bouton.value?.focus()
  }
})
onBeforeUnmount(() => {
  clearTimeout(minuterie)
})
</script>

<template>
  <section
    v-if="statut?.configured"
    class="resana-carte fr-mb-4w"
    aria-labelledby="etat-resana-titre"
  >
    <div class="resana-carte__tete">
      <h2
        id="etat-resana-titre"
        class="fr-h5 fr-mb-0"
      >
        Espace Résana
      </h2>
      <span
        class="fr-badge fr-badge--sm fr-badge--no-icon"
        :class="statut.couverture === 'totale' ? 'fr-badge--success' : 'fr-badge--info'"
      >{{ etiquetteResana(statut) }}</span>
    </div>
    <p class="fr-text--sm fr-mt-1w fr-mb-1w">
      <strong>{{ statut.espace_nom }}</strong><template v-if="statut.espace?.entite">
        ({{ statut.espace.entite }})
      </template> › {{ statut.dossier_chemin }}{{ derniere ? ` — dernière lecture le ${derniere}` : '' }}.
    </p>
    <p class="fr-text--sm fr-mb-1w">
      {{ phraseCouverture(statut) }}
    </p>
    <p class="fr-text--xs resana-discret">
      Collection privée : seule la personne qui a importé le dossier l'interroge et la met à jour.
    </p>

    <div
      v-if="statut.avis && !enCours"
      class="fr-notice fr-notice--info fr-mb-2w"
    >
      <div class="fr-container">
        <div class="fr-notice__body">
          <p class="fr-notice__title fr-text--sm">
            {{ statut.avis.message }}
          </p>
        </div>
      </div>
    </div>

    <p
      v-if="phrase"
      class="fr-text--sm"
      role="status"
      aria-live="polite"
    >
      {{ phrase }}
      <a
        v-if="statut.travail?.url_connexion?.startsWith('https://')"
        :href="statut.travail.url_connexion"
        class="fr-link"
        target="_blank"
        rel="noopener"
      >Se connecter à Résana<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
    </p>
    <details
      v-if="ecartes.length"
      class="fr-text--xs fr-mb-2w"
    >
      <summary>Documents écartés ({{ ecartes.length }})</summary>
      <ul>
        <li
          v-for="(e, i) in ecartes"
          :key="i"
        >
          {{ e.titre }} — {{ e.raison }}
        </li>
      </ul>
    </details>
    <div
      v-if="erreur"
      class="fr-alert fr-alert--sm fr-mb-2w"
      :class="erreur.code === 'session_absente' ? 'fr-alert--warning' : 'fr-alert--error'"
      role="alert"
    >
      <p>{{ erreur.message }}</p>
      <p v-if="erreur.urlConnexion">
        <a
          :href="erreur.urlConnexion"
          class="fr-link"
          target="_blank"
          rel="noopener"
        >Se connecter à Résana<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
      </p>
    </div>

    <ul
      v-if="statut.est_importeur && !edition"
      class="fr-btns-group fr-btns-group--inline fr-btns-group--sm"
    >
      <li>
        <button
          ref="bouton"
          type="button"
          class="fr-btn fr-btn--sm"
          :class="statut.avis ? '' : 'fr-btn--secondary'"
          :disabled="enCours || envoi"
          @click="synchroniser()"
        >
          {{ enCours || envoi ? 'Mise à jour en cours…' : (statut.avis?.action.libelle || 'Mettre à jour') }}
        </button>
      </li>
      <li>
        <button
          type="button"
          class="fr-btn fr-btn--sm fr-btn--tertiary"
          :disabled="enCours || envoi"
          @click="ouvrirEdition"
        >
          Modifier la sélection
        </button>
      </li>
      <li>
        <button
          type="button"
          class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline"
          :disabled="enCours || envoi"
          title="Retélécharge chaque document pour comparer son empreinte, même si Résana annonce la même version"
          @click="synchroniser(undefined, true)"
        >
          Vérification complète
        </button>
      </li>
    </ul>

    <div
      v-if="edition"
      class="fr-mt-2w"
    >
      <DepotDossiersResana
        v-if="statut.espace_id"
        v-model="choisis"
        :espace="statut.espace_id"
        @dossiers="dossiersChoisis = $event"
      />
      <ul class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-2w">
        <li>
          <button
            type="button"
            class="fr-btn fr-btn--sm"
            :disabled="!dossiersChoisis.length || envoi"
            @click="synchroniser(dossiersChoisis)"
          >
            Enregistrer et mettre à jour
          </button>
        </li>
        <li>
          <button
            type="button"
            class="fr-btn fr-btn--sm fr-btn--tertiary"
            @click="fermerEdition"
          >
            Annuler
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.resana-carte { padding: 1.5rem 2rem; border: 1px solid var(--border-default-grey); }
.resana-carte__tete { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; }
.resana-discret { color: var(--text-mention-grey); }
@media (max-width: 36em) { .resana-carte { padding: 1rem; } }
</style>
