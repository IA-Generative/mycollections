<script setup lang="ts">
/**
 * Où en est une collection Résana (docs/resana.md) : le dossier relié, ce que l'index en couvre
 * (complet ou partiel, et pourquoi), l'import ou la mise à jour en cours, l'invitation à mettre à
 * jour un index ancien, et — pour la personne qui a importé — « Mettre à jour » et « Modifier la
 * sélection » (ajouter ou retirer des sous-dossiers, pour poursuivre l'indexation).
 */
import type { AvisResana, CouvertureResana, ErreurResana, StatutResana } from '~/utils/resana'
import { erreurResana, etiquetteResana, grouperEcartes, libelleTravail, phraseCouverture, phrasesQualite, travailEnCours } from '~/utils/resana'

const props = withDefaults(defineProps<{
  collection: string
  /** Étape 3 de l'assistant, juste après l'import : seule « Modifier la sélection » a un sens. */
  compact?: boolean
}>(), { compact: false })

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
const groupesEcartes = computed(() => grouperEcartes(ecartes.value))
// Des écarts notés avant que l'adresse Résana ne soit gardée : une mise à jour la retrouvera.
const sansLien = computed(() => ecartes.value.some(e => !e.url))
// Le total réel : la carte n'en reçoit que les premiers (ECARTES_MAX côté serveur).
const totalEcartes = computed(() => Math.max(statut.value?.travail?.ecartes || 0, ecartes.value.length))
const { telecharger } = useTelechargement()
// « Se connecter à Résana » : la fenêtre s'ouvre, on guette la session, puis la mise à jour repart.
const connexion = useConnexionResana()
const seConnecter = (url: string) => connexion.ouvrir(url, () => synchroniser())
const exportEnCours = ref(false)
const erreurExport = ref('')
async function exporterEcartes () {
  exportEnCours.value = true
  erreurExport.value = ''
  try {
    await telecharger(`/api/sources/resana/ecartes/${encodeURIComponent(props.collection)}?format=csv`, `${props.collection}-documents-ecartes.csv`)
  }
  catch {
    erreurExport.value = 'L\'export n\'a pas pu être téléchargé. Réessayez dans un instant.'
  }
  finally {
    exportEnCours.value = false
  }
}
const qualite = computed(() => phrasesQualite(statut.value?.qualite))
const aReprendre = computed(() => statut.value?.qualite?.a_reprendre ?? 0)
const inconnus = computed(() => statut.value?.qualite?.par_etat?.inconnue ?? 0)

async function relireQualite () {
  envoi.value = true
  erreur.value = null
  try {
    await post(`/api/sources/resana/qualite/${encodeURIComponent(props.collection)}`)
  }
  catch (e) {
    erreur.value = erreurResana(e)
  }
  finally {
    envoi.value = false
  }
  await charger()
}
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

async function synchroniser (dossiers?: { id: string, chemin: string }[], complet = false, incomplets = false) {
  envoi.value = true
  erreur.value = null
  try {
    // Changer la sélection remplace la liste des dossiers inclus (et efface d'anciennes exclusions).
    const corps = dossiers || complet || incomplets
      ? { ...(dossiers ? { dossiers, exclus: [] } : {}), ...(complet ? { complet: true } : {}), ...(incomplets ? { incomplets: true } : {}) }
      : undefined
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
      v-if="qualite.length && !enCours"
      class="fr-callout fr-callout--yellow-moutarde fr-py-2w fr-px-3w fr-mb-2w"
    >
      <p class="fr-callout__text fr-text--sm fr-mb-1w">
        <strong>Ce que vaut l'index</strong>
      </p>
      <ul class="fr-text--sm fr-mb-0">
        <li
          v-for="(p, i) in qualite"
          :key="i"
        >
          {{ p }}
        </li>
      </ul>
    </div>

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
        @click.prevent="seConnecter(statut.travail!.url_connexion!)"
      >Se connecter à Résana<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
    </p>
    <p
      v-if="connexion.enAttente.value"
      class="fr-text--sm"
      role="status"
    >
      ⏳ Connectez-vous dans la fenêtre Résana : la mise à jour repartira d'elle-même.
    </p>
    <div
      v-if="connexion.retablie.value"
      class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w"
      role="status"
    >
      <p>Connexion à Résana établie : la mise à jour a repris.</p>
    </div>
    <details
      v-if="ecartes.length"
      class="fr-text--sm fr-mb-2w ecartes"
    >
      <summary>Documents écartés ({{ totalEcartes }})</summary>
      <p class="fr-text--xs fr-mt-1w fr-mb-1w">
        Un document écarté n'est pas indexé : le chat ne s'en servira pas. Chaque raison dit ce que vous pouvez faire.
        <span v-if="totalEcartes > ecartes.length">Seuls les {{ ecartes.length }} premiers sont listés ici ; l'export les donne tous.</span>
        <span v-if="sansLien">Les liens vers Résana apparaîtront après une « Mise à jour ».</span>
      </p>
      <p class="fr-mb-2w">
        <button
          type="button"
          class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-download-line fr-btn--icon-left"
          :disabled="exportEnCours"
          @click="exporterEcartes"
        >
          {{ exportEnCours ? 'Export en cours…' : 'Exporter la liste (CSV)' }}
        </button>
        <span
          v-if="erreurExport"
          class="fr-error-text"
        >{{ erreurExport }}</span>
      </p>
      <section
        v-for="g in groupesEcartes"
        :key="g.code"
        class="fr-mb-2w"
      >
        <h3 class="fr-text--md fr-text--bold fr-mb-0">
          {{ g.libelle }}<template v-if="g.code === 'format' && g.extensions.length"> : {{ g.extensions.join(', ') }}</template> ({{ g.documents.length }})
        </h3>
        <p class="fr-text--xs fr-mb-1v ecartes__explication">
          {{ g.explication }} <strong>{{ g.quoiFaire }}</strong>
        </p>
        <ul class="fr-text--xs fr-mb-0">
          <li
            v-for="(e, i) in g.documents"
            :key="e.id || i"
          >
            <a
              v-if="e.url"
              :href="e.url"
              target="_blank"
              rel="noopener"
            >{{ e.titre }}<span class="fr-sr-only"> (ouvrir dans Résana, nouvelle fenêtre)</span></a>
            <span v-else>{{ e.titre }}</span>
            <span
              v-if="e.extension"
              class="ecartes__dossier"
            > ({{ e.extension }})</span>
            <span
              v-if="e.chemin"
              class="ecartes__dossier"
            > — {{ e.chemin }}</span>
          </li>
        </ul>
      </section>
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
          @click.prevent="seConnecter(erreur.urlConnexion)"
        >Se connecter à Résana<span class="fr-sr-only"> (nouvelle fenêtre)</span></a>
        <span
          v-if="connexion.enAttente.value"
          class="fr-text--sm fr-ml-2w"
        >⏳ cette page reprendra d'elle-même.</span>
      </p>
    </div>

    <div
      v-if="statut.est_importeur && !edition"
      class="gestes"
    >
      <!-- Deux intentions, séparées : tenir l'index à jour / changer ce qui est indexé. -->
      <section
        v-if="!compact"
        class="gestes__zone"
      >
        <h3 class="fr-text--md fr-text--bold fr-mb-1v">
          Tenir l'index à jour
        </h3>
        <ul class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mb-0">
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
          <li v-if="aReprendre">
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--secondary"
              :disabled="enCours || envoi"
              @click="synchroniser(undefined, false, true)"
            >
              Ré-indexer les documents incomplets ({{ aReprendre }})
            </button>
          </li>
          <li v-if="inconnus">
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary"
              :disabled="enCours || envoi"
              @click="relireQualite"
            >
              Relire le bilan auprès du moteur
            </button>
          </li>
          <li>
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline"
              :disabled="enCours || envoi"
              @click="synchroniser(undefined, true)"
            >
              Tout revérifier
            </button>
          </li>
        </ul>
        <ul class="fr-text--xs gestes__aide">
          <li><strong>Mettre à jour</strong> relit les dossiers choisis dans Résana et n'indexe que ce qui a changé : à faire quand des documents ont bougé dans Résana.</li>
          <li v-if="aReprendre">
            <strong>Ré-indexer les documents incomplets</strong> renvoie au moteur les {{ aReprendre }} documents lus sans tout leur contexte ou sans texte.
          </li>
          <li v-if="inconnus"><strong>Relire le bilan</strong> demande au moteur ce que vaut chaque document déjà indexé, sans rien renvoyer.</li>
          <li><strong>Tout revérifier</strong> retélécharge chaque document pour comparer son contenu : utile si un document modifié dans Résana n'a pas été repris par la mise à jour.</li>
        </ul>
      </section>
      <section class="gestes__zone">
        <h3 class="fr-text--md fr-text--bold fr-mb-1v">
          Changer ce qui est indexé
        </h3>
        <ul class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mb-0">
          <li>
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--secondary"
              :disabled="enCours || envoi"
              @click="ouvrirEdition"
            >
              Modifier la sélection
            </button>
          </li>
        </ul>
        <p class="fr-text--xs gestes__aide">
          Ajouter ou retirer des dossiers de l'espace : un dossier ajouté s'indexe, un dossier retiré sort de l'index.
        </p>
      </section>
    </div>

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
.ecartes__explication, .ecartes__dossier { color: var(--text-mention-grey); }
.gestes { display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem; }
.gestes__zone + .gestes__zone { border-top: 1px solid var(--border-default-grey); padding-top: 1rem; }
.gestes__aide { color: var(--text-mention-grey); margin: .25rem 0 0; }
@media (max-width: 36em) { .resana-carte { padding: 1rem; } }
</style>
