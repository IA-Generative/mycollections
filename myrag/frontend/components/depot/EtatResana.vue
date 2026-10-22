<script setup lang="ts">
/**
 * Où en est une collection Résana (docs/resana.md) : le dossier relié, l'import ou la
 * synchronisation en cours, et le bouton « Synchroniser », réservé à la personne qui a importé.
 */
import type { ErreurResana, StatutResana } from '~/utils/resana'
import { erreurResana, libelleTravail, travailEnCours } from '~/utils/resana'

const props = defineProps<{ collection: string }>()

const { get, post } = useApi()
const statut = ref<StatutResana | null>(null)
const erreur = ref<ErreurResana | null>(null)
const envoi = ref(false)
let minuterie: ReturnType<typeof setTimeout> | undefined

const enCours = computed(() => travailEnCours(statut.value?.travail))
const phrase = computed(() => libelleTravail(statut.value?.travail))
const ecartes = computed(() => statut.value?.travail?.documents_ecartes || [])
const derniere = computed(() => {
  const d = statut.value?.last_sync_at
  return d ? new Date(d.endsWith('Z') || d.includes('+') ? d : `${d}Z`).toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'short' }) : ''
})

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

async function synchroniser () {
  envoi.value = true
  erreur.value = null
  try {
    await post(`/api/sources/resana/sync/${encodeURIComponent(props.collection)}`)
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    envoi.value = false
  }
  await charger()
}

onMounted(charger)
onBeforeUnmount(() => clearTimeout(minuterie))
</script>

<template>
  <section
    v-if="statut?.configured"
    class="resana-carte fr-mb-4w"
    aria-labelledby="etat-resana-titre"
  >
    <div>
      <div>
        <h2
          id="etat-resana-titre"
          class="fr-h5"
        >
          Dossier Résana
        </h2>
        <p class="fr-text--sm fr-mb-1w">
          <strong>{{ statut.espace_nom }}</strong> › {{ statut.dossier_chemin }} —
          {{ statut.documents }} document{{ statut.documents > 1 ? 's' : '' }} importé{{ statut.documents > 1 ? 's' : '' }}{{ derniere ? `, dernière lecture le ${derniere}` : '' }}.
        </p>
        <p class="fr-text--xs resana-discret">
          Collection privée : seule la personne qui a importé le dossier l'interroge et la synchronise.
        </p>
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
        <button
          v-if="statut.est_importeur"
          type="button"
          class="fr-btn fr-btn--secondary fr-btn--sm fr-icon-refresh-line fr-btn--icon-left"
          :disabled="enCours || envoi"
          @click="synchroniser"
        >
          {{ enCours || envoi ? 'Synchronisation en cours…' : 'Synchroniser' }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.resana-carte { padding: 1.5rem 2rem; border: 1px solid var(--border-default-grey); }
.resana-discret { color: var(--text-mention-grey); }
@media (max-width: 36em) { .resana-carte { padding: 1rem; } }
</style>
