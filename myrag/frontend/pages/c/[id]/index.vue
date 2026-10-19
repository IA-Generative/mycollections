<script setup lang="ts">
import type { CleOnglet } from '~/utils/fiche'
import { useMesAgents } from '~/composables/useMesAgents'
import { libelleEtat, messageErreur } from '~/utils/collectif'
import { actionsFiche, dateFiche, ligneMeta, ONGLET_PAR_DEFAUT, ongletDepuisAncien, ongletsFiche } from '~/utils/fiche'
import { libelleSansCompteur, ongletDeLAdresse } from '~/utils/filAriane'
import { appreciation, dateMesure } from '~/utils/qualite'

/**
 * La fiche d'une collection (refonte du 2026-10-19) : en-tête, actions, « Ce qu'en pensent vos
 * collègues », « Consignes données à l'assistant », lignes Qualité et Où l'interroger, puis
 * quatre onglets — Documents · Signalements · Propositions · Historique. Ce qu'elle affiche
 * vient de utils/fiche.ts (testé).
 */
const route = useRoute()
const router = useRouter()
const id = route.params.id as string
const { get } = useApi()
const c = useCollectif()
const { isAdmin } = useAdminAuth()
const { capacites, charger: chargerCapacites } = useCapacites()
const agents = useMesAgents()
// L'onglet « Interroger avec un agent » existe (Mes agents branché, liste obtenue sans refus).
const agentsDisponibles = ref(false)

// ─── Le circuit collaboratif ─────────────────────────────────────────────────
const etat = ref<any>(null)
const grille = ref<any>(null)
const propositions = ref<any[] | null>([])
const signalements = ref<any[] | null>([])
const evenements = ref<any[] | null>([])
const suivant = ref<string | null>(null)
const abonne = ref(false)
const fichiers = ref<any[] | null>(null)
const erreurEtat = ref('')
const erreurGrille = ref('')
const estGarant = computed(() => !!(etat.value && (etat.value.je_suis_garant || isAdmin.value)))

async function rechargerCollectif () {
  try {
    propositions.value = (await c.propositions(id)).propositions
  }
  catch {
    propositions.value = null
  }
  try {
    signalements.value = (await c.signalements(id)).signalements
  }
  catch {
    signalements.value = null
  }
  try {
    const j = await c.journalCollection(id)
    evenements.value = j.evenements
    suivant.value = j.suivant
  }
  catch {
    evenements.value = null
  }
}
async function chargerCollectif () {
  await chargerCapacites()
  try {
    etat.value = await c.etat(id)
  }
  catch {
    etat.value = null
  }
  try {
    grille.value = (await c.grille(id)).grille
  }
  catch {
    grille.value = null
  }
  await rechargerCollectif()
  try {
    fichiers.value = (await get(`/api/ingest/${id}/sources`)).sources || []
  }
  catch {
    fichiers.value = null
  }
}
async function suite (avant: string) {
  const j = await c.journalCollection(id, { avant })
  evenements.value = [...(evenements.value || []), ...j.evenements]
  suivant.value = j.suivant
}
async function geste (action: () => Promise<unknown>, erreur: Ref<string>) {
  erreur.value = ''
  try {
    await action()
    await rechargerCollectif()
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
}
function changerEtat (cible: string) {
  return geste(async () => {
    etat.value = await c.changerEtat(id, cible)
  }, erreurEtat)
}
function forcerEtat (cible: string, motif: string) {
  return geste(async () => {
    etat.value = await c.changerEtat(id, cible, true, motif)
  }, erreurEtat)
}
function enregistrerGrille (champs: any) {
  return geste(async () => {
    grille.value = (await c.majGrille(id, champs)).grille
    etat.value = await c.etat(id)
  }, erreurGrille)
}
function relire () {
  return geste(async () => {
    grille.value = (await c.relire(id)).grille
    etat.value = await c.etat(id)
  }, erreurGrille)
}
const publierProposition = (pid: string) => geste(() => c.publierProposition(id, pid), erreurGrille)
const refuserProposition = (pid: string, motif: string) => geste(() => c.refuserProposition(id, pid, motif), erreurGrille)
const traiterSignalement = (sid: string, e2: string) => geste(() => c.traiterSignalement(id, sid, e2), erreurGrille)
async function abonner (oui: boolean) {
  try {
    await c.abonnerCollection(id, oui)
    abonne.value = oui
  }
  catch (e) {
    erreurGrille.value = messageErreur(e)
  }
}

// ─── La fiche ────────────────────────────────────────────────────────────────
const collection = ref<any>(null)
const { titre, retenir } = useTitreCollection(id, { charger: false })
const libelleCategorie = ref('')
const loadError = ref<string>('')
const adopting = ref(false)
const adoptError = ref<string>('')
const stats = ref<any>(null)
const usage = ref<any>(null)
const derniersAvis = ref<any[] | null>(null)
const mesure = ref<any>(null)
const loading = ref(true)
const accesOuverts = ref(false)

/** Ce que l'appelant peut faire de la collection (dit par l'API) : on n'offre que ces gestes. */
const peutGerer = computed(() => !!collection.value?.mes_droits?.ecrire)
const actions = computed(() => actionsFiche(collection.value?.mes_droits, !!collection.value?.graph_enabled, id))

const meta = computed(() => {
  const col = collection.value || {}
  const cree = dateFiche(col.created_at)
  const maj = dateFiche(col.updated_at)
  return ligneMeta({
    categorie_libelle: libelleCategorie.value || (col.categorie ? '' : 'Non classée'),
    nb_documents: fichiers.value ? fichiers.value.length : null,
    cree_le: cree,
    mise_a_jour: maj && maj !== cree ? `le ${maj}` : '',
    responsable: col.contact_name,
  })
})

// ─── Les onglets ─────────────────────────────────────────────────────────────
const onglets = computed(() => ongletsFiche({
  documents: fichiers.value ? fichiers.value.length : null,
  signalements: signalements.value ? signalements.value.filter(s => s.etat !== 'clos').length : null,
  propositions: propositions.value ? propositions.value.filter(p => p.etat === 'proposee').length : null,
}, { agent: agentsDisponibles.value }))
const tab = ref<CleOnglet>(ONGLET_PAR_DEFAUT)

// L'onglet ouvert vit dans l'adresse (`?onglet=historique`). Les anciennes clés mènent à leur
// nouvelle place : Consulter et Discussion → Historique, Consignes → le bloc des consignes,
// Avis et jeux de questions → la page Qualité.
const ancien = ongletDepuisAncien(route.query.onglet, id)
if (ancien?.type === 'page') {
  navigateTo(ancien.vers, { replace: true })
}
function ongletDemande (): CleOnglet {
  const r = ongletDepuisAncien(route.query.onglet, id)
  if (r?.type === 'onglet') {
    return r.cle
  }
  return ongletDeLAdresse(route.query.onglet, onglets.value.map(o => o.cle), ONGLET_PAR_DEFAUT) as CleOnglet
}
tab.value = ongletDemande()
watch(tab, (t) => {
  if (t === ongletDemande() && !ongletDepuisAncien(route.query.onglet, id)) {
    return
  }
  const query = { ...route.query }
  if (t === ONGLET_PAR_DEFAUT) {
    delete query.onglet
  }
  else {
    query.onglet = t
  }
  router.replace({ query })
})
watch(() => route.query.onglet, () => {
  tab.value = ongletDemande()
})
watch(agentsDisponibles, () => {
  tab.value = ongletDemande()
})

/** Le dernier maillon du fil d'Ariane : l'onglet ouvert, sans son compteur. */
const rubrique = computed(() => libelleSansCompteur(onglets.value.find(o => o.cle === tab.value)?.libelle || ''))

const documentsVus = ref(false)
watch(tab, (t) => {
  if (t === 'documents') {
    documentsVus.value = true
  }
}, { immediate: true })
const agentVu = ref(false)
watch(tab, (t) => {
  if (t === 'agent') {
    agentVu.value = true
  }
}, { immediate: true })

/** Ce qu'un panneau doit porter pour que le DSFR le montre, et pour qu'un lecteur d'écran le relie à son onglet. */
function panneau (cle: string) {
  return {
    'id': `panneau-${cle}`,
    'class': ['fr-tabs__panel', { 'fr-tabs__panel--selected': tab.value === cle }],
    'role': 'tabpanel',
    'aria-labelledby': `onglet-${cle}`,
    'tabindex': 0,
  }
}

/** Flèches, Début et Fin parcourent la rangée, comme le veut le motif « onglets ». */
function clavierOnglets (ev: KeyboardEvent) {
  const cles = onglets.value.map(o => o.cle)
  const i = cles.indexOf(tab.value)
  const vers = ({ ArrowRight: (i + 1) % cles.length, ArrowLeft: (i - 1 + cles.length) % cles.length, Home: 0, End: cles.length - 1 } as Record<string, number>)[ev.key]
  if (vers === undefined) {
    return
  }
  ev.preventDefault()
  tab.value = cles[vers]!
  nextTick(() => document.getElementById(`onglet-${cles[vers]}`)?.focus())
}

function qualityClass (rate: number) {
  if (rate >= 0.7) {
    return 'myrag-quality-bar__fill--good'
  }
  if (rate >= 0.4) {
    return 'myrag-quality-bar__fill--medium'
  }
  return 'myrag-quality-bar__fill--bad'
}

/** Une partition OpenRAG sans fiche : en créer une minimale (idempotent côté OpenRAG). */
async function adoptCollection () {
  adopting.value = true
  adoptError.value = ''
  try {
    const { post } = useApi()
    await post('/api/collections', { name: id, description: '', sensitivity: 'public', scope: 'group' })
    window.location.reload()
  }
  catch (e: any) {
    adoptError.value = messageErreur(e)
    adopting.value = false
  }
}

onMounted(async () => {
  try {
    collection.value = await get(`/api/collections/${id}`)
    retenir(collection.value)
  }
  catch (e: any) {
    loadError.value = e?.message || 'erreur de chargement'
    collection.value = null
    loading.value = false
    return
  }
  loading.value = false
  if (ancien?.type === 'ancre') {
    nextTick(() => document.getElementById(ancien.cle)?.focus())
  }
  if (collection.value?.categorie) {
    useCategories().lister().then((cats) => {
      libelleCategorie.value = cats.find(k => k.cle === collection.value.categorie)?.libelle || ''
    }).catch(() => {})
  }
  // Chaque bloc tombe seul, jamais la page.
  chargerCollectif()
  if (agents.configure) {
    agents.lister().then(() => {
      agentsDisponibles.value = agents.disponible.value
    }).catch(() => {})
  }
  get(`/api/feedback/${id}/stats`).then((r) => {
    stats.value = r
  }).catch(() => {})
  get(`/api/collections/${id}/usage`).then((r) => {
    usage.value = r
  }).catch(() => {})
  if (peutGerer.value) {
    get(`/api/feedback/${id}`, { limit: '3' }).then((r) => {
      derniersAvis.value = r.feedback || []
    }).catch(() => {})
    useQualite(id).synthese().then((s) => {
      mesure.value = s.derniere_terminee
    }).catch(() => {})
  }
})
</script>

<template>
  <div>
    <FilAriane
      :collection="id"
      :titre="titre"
      :rubrique="collection ? rubrique : undefined"
    />

    <div
      v-if="loading"
      class="fr-callout"
    >
      <p>Chargement…</p>
    </div>

    <!-- Une partition OpenRAG sans fiche Mes collections. -->
    <div
      v-else-if="!collection"
      class="fr-alert fr-alert--warning"
    >
      <h1 class="fr-alert__title fr-h5">
        La collection « {{ id }} » n'a pas encore de fiche
      </h1>
      <p>
        Cette collection existe peut-être dans le moteur de recherche, mais n'a pas encore
        de fiche dans Mes collections (description, consignes, responsable…).
        <span
          v-if="loadError"
          class="fr-text--sm fiche-discret"
        >({{ loadError }})</span>
      </p>
      <p>
        Vous pouvez la rattacher à une fiche minimale puis compléter sa description — aucun document n'est touché.
      </p>
      <div
        v-if="adoptError"
        class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"
      >
        <p>{{ adoptError }}</p>
      </div>
      <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
        <button
          class="fr-btn"
          :disabled="adopting"
          @click="adoptCollection"
        >
          {{ adopting ? 'Création en cours…' : 'Rattacher cette collection' }}
        </button>
        <NuxtLink
          to="/admin/catalog"
          class="fr-btn fr-btn--secondary"
        >
          Retour au catalogue
        </NuxtLink>
      </div>
    </div>

    <div v-else>
      <!-- En-tête : titre et état, description, métadonnées ; à droite, les gestes. -->
      <div class="fiche-tete fr-mb-4w">
        <div class="fiche-tete__texte">
          <div class="fiche-tete__titre">
            <h1 class="fr-h2 fr-mb-0">
              {{ titre }}
            </h1>
            <span
              v-if="collection.etat_collab"
              class="fr-badge fr-badge--no-icon"
              :class="collection.etat_collab === 'publiee_tous' ? 'fr-badge--success' : 'fr-badge--warning'"
            >
              {{ libelleEtat(collection.etat_collab) }}
            </span>
          </div>
          <p
            v-if="etat && etat.mention"
            class="collectif-mention fr-mb-0"
          >
            {{ etat.mention }} — servie à son groupe seulement
          </p>
          <p class="fr-text--lg fr-mb-0">
            {{ collection.description || 'Pas de description' }}
          </p>
          <p
            v-if="meta"
            class="fr-text--sm fr-mb-0 fiche-discret"
          >
            {{ meta }}
          </p>
          <p class="fr-text--xs fr-mb-0 fiche-discret">
            Identifiant : <code title="Ce que tapent les applications : openrag-…">{{ collection.name }}</code>
          </p>
        </div>
        <div class="fiche-tete__actions">
          <NuxtLink
            v-for="(a, i) in actions.principales"
            :key="a.cle"
            :to="a.vers"
            :title="a.aide"
            class="fr-btn fr-btn--icon-left"
            :class="[a.icone, i ? 'fr-btn--secondary' : '']"
          >
            {{ a.libelle }}
          </NuxtLink>
          <FicheMenuPlus :actions="actions.plus" />
        </div>
      </div>

      <!-- Deux blocs côte à côte ; empilés sur mobile. -->
      <div class="fr-grid-row fr-grid-row--gutters fr-mb-2w">
        <div class="fr-col-12 fr-col-lg-6">
          <FicheAvisCollegues
            :id="id"
            :stats="stats"
            :usage="usage"
            :derniers="derniersAvis"
            :peut-gerer="peutGerer"
          />
        </div>
        <div class="fr-col-12 fr-col-lg-6">
          <FicheConsignes
            :id="id"
            :modele="collection.prompt_template"
            :consignes="collection.system_prompt"
            :peut-gerer="peutGerer"
          />
        </div>
      </div>

      <div class="fr-grid-row fr-grid-row--gutters fr-mb-4w">
        <!-- Qualité : pour qui gère. -->
        <div
          v-if="peutGerer"
          class="fr-col-12 fr-col-lg-6"
        >
          <div class="fiche-ligne">
            <template v-if="mesure">
              <div class="fiche-ligne__mesure">
                <strong>{{ mesure.score }} %</strong>
                <span class="fr-text--sm">de réponses justes · {{ appreciation(mesure.score).libelle }} · mesuré le {{ dateMesure(mesure.cree_le) }}</span>
                <div
                  class="myrag-quality-bar"
                  role="img"
                  :aria-label="`Qualité mesurée : ${mesure.score} sur 100`"
                >
                  <div
                    class="myrag-quality-bar__fill"
                    :class="qualityClass(mesure.score / 100)"
                    :style="{ width: `${mesure.score}%` }"
                  />
                </div>
              </div>
            </template>
            <span
              v-else
              class="fr-text--sm"
            >Qualité : aucune mesure pour l'instant.</span>
            <NuxtLink
              :to="`/c/${id}/qualite`"
              class="fr-link fiche-ligne__lien"
            >
              Piloter la qualité →
            </NuxtLink>
          </div>
        </div>
        <!-- Où l'interroger : le bloc détaillé ne s'ouvre qu'à la demande. -->
        <div
          class="fr-col-12"
          :class="{ 'fr-col-lg-6': peutGerer }"
        >
          <div class="fiche-ligne">
            <span
              v-if="collection.acces"
              class="fr-text--sm"
            ><strong>Où l'interroger :</strong> ici, dans Mon assistant (modèle <code>{{ collection.acces.assistant.model_id }}</code>), ou par l'API.</span>
            <span
              v-else
              class="fr-text--sm"
            ><strong>Où l'interroger :</strong> ici, dans son bac à sable, tant qu'elle n'est pas publiée à tous.</span>
            <button
              v-if="collection.acces"
              type="button"
              class="fr-link fiche-ligne__lien"
              aria-controls="fiche-acces"
              :aria-expanded="accesOuverts ? 'true' : 'false'"
              @click="accesOuverts = !accesOuverts"
            >
              {{ accesOuverts ? 'Masquer les accès' : 'Voir les accès' }}
            </button>
          </div>
          <div
            v-if="collection.acces"
            v-show="accesOuverts"
            id="fiche-acces"
            class="fr-callout fr-callout--green-emeraude fr-mt-2w"
          >
            <ul class="fr-text--sm">
              <li>
                <strong>dans l'agent conversationnel de MirAI Next</strong>, en choisissant le modèle
                <code>{{ collection.acces.assistant.model_id }}</code> ;
              </li>
              <li v-if="collection.acces.api">
                <strong>par l'API, depuis vos SI</strong> :
                <code>POST {{ collection.acces.api.chat }}</code> avec <code>"model": "{{ collection.acces.api.model }}"</code>
                (format OpenAI), ou <code>GET {{ collection.acces.api.search }}</code> pour la recherche seule —
                sur clé d'API à demander à l'équipe de la bêta ;
              </li>
              <li><strong>dans vos outils bureautiques</strong> : greffon LibreOffice à venir.</li>
              <li v-if="agentsDisponibles">
                <strong>avec un agent de Mes agents</strong>, sur les passages de la collection :
                <button
                  type="button"
                  class="fr-link fr-text--sm"
                  @click="tab = 'agent'"
                >
                  onglet « Interroger avec un agent »
                </button>.
              </li>
            </ul>
            <p class="fr-text--sm fr-mb-0">
              <NuxtLink
                to="/guide/interroger-depuis-vos-si"
                class="fr-link"
              >
                Le guide : interroger depuis vos SI
              </NuxtLink>
            </p>
          </div>
        </div>
      </div>

      <!-- Onglets -->
      <div class="fr-tabs">
        <!-- Le DSFR cache tout panneau qui n'a pas `fr-tabs__panel--selected` : c'est son
             JavaScript qui pose cette classe, et nous ne le chargeons pas. Vue la pose. -->
        <ul
          class="fr-tabs__list"
          role="tablist"
          aria-label="Rubriques de la collection"
          @keydown="clavierOnglets"
        >
          <li
            v-for="o in onglets"
            :key="o.cle"
            role="presentation"
          >
            <button
              :id="`onglet-${o.cle}`"
              type="button"
              class="fr-tabs__tab"
              role="tab"
              :aria-selected="tab === o.cle"
              :aria-controls="`panneau-${o.cle}`"
              :tabindex="tab === o.cle ? 0 : -1"
              @click="tab = o.cle"
            >
              {{ o.libelle }}
            </button>
          </li>
        </ul>

        <!-- Documents : le corpus, monté à la première ouverture. -->
        <div
          v-show="tab === 'documents'"
          v-bind="panneau('documents')"
        >
          <div
            v-if="peutGerer"
            class="fiche-panneau-tete"
          >
            <NuxtLink
              :to="`/c/${id}/upload`"
              class="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-left fr-icon-file-add-line"
            >
              Ajouter des documents
            </NuxtLink>
          </div>
          <CorpusDocuments
            v-if="documentsVus"
            :collection="id"
          />
        </div>

        <div
          v-show="tab === 'signalements'"
          v-bind="panneau('signalements')"
        >
          <CollectifSignalements
            :signalements="signalements"
            :garant="estGarant"
            :actif="capacites.signalements"
            :fichiers="fichiers || []"
            :signaler="corps => c.signaler(id, corps)"
            @depose="rechargerCollectif"
            @traiter="traiterSignalement"
          />
        </div>

        <div
          v-show="tab === 'propositions'"
          v-bind="panneau('propositions')"
        >
          <CollectifPropositions
            :propositions="propositions"
            :garant="estGarant"
            :proposer="corps => c.proposer(id, corps)"
            @deposee="rechargerCollectif"
            @publier="publierProposition"
            @refuser="refuserProposition"
          />
        </div>

        <!-- Historique : le circuit de vérification et la grille de contrôle en tête, puis le
             fil, puis la discussion. -->
        <div
          v-show="tab === 'historique'"
          v-bind="panneau('historique')"
        >
          <div class="fr-grid-row fr-grid-row--gutters fr-mb-3w">
            <div class="fr-col-12 fr-col-lg-4">
              <CollectifEtapesCollection
                v-if="etat"
                :etat="etat"
                :superadmin="isAdmin"
                @changer="changerEtat"
                @forcer="forcerEtat"
              />
              <div
                v-if="erreurEtat"
                class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"
              >
                <p>{{ erreurEtat }}</p>
              </div>
            </div>
            <div class="fr-col-12 fr-col-lg-8">
              <CollectifGrilleControle
                v-if="grille"
                :grille="grille"
                :garant="estGarant"
                @enregistrer="enregistrerGrille"
                @relire="relire"
              />
              <p
                v-else
                class="fr-text--sm fiche-discret"
              >
                Grille de contrôle indisponible.
              </p>
              <div
                v-if="erreurGrille"
                class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"
              >
                <p>{{ erreurGrille }}</p>
              </div>
              <p class="fr-text--sm fr-mt-2w">
                <NuxtLink
                  to="/guide/verifier-avant-de-publier"
                  class="fr-link fr-text--sm"
                >
                  Vérifier avant de publier — le guide
                </NuxtLink>
              </p>
            </div>
          </div>
          <CollectifAvancement
            :evenements="evenements"
            :suivant="suivant"
            abonnable
            :abonne="abonne"
            @abonner="abonner"
            @suite="suite"
          />
          <div class="fr-callout fr-mt-4w">
            <h2 class="fr-callout__title fr-h6">
              La discussion se tient dans les forums Mirai
            </h2>
            <p class="fr-callout__text fr-text--sm">
              Les échanges entre contributeurs passent par le salon Tchap de la bêta. Ce qui engage la collection
              — un défaut, une modification — se dépose ici, dans les onglets « Signalements » et « Propositions », pour rester tracé.
            </p>
            <button
              class="fr-btn fr-btn--sm fr-btn--secondary fr-mt-2w"
              @click="abonner(!abonne)"
            >
              {{ abonne ? 'Abonné·e au fil' : "S'abonner au fil d'avancement" }}
            </button>
          </div>
        </div>

        <div
          v-if="agentsDisponibles"
          v-show="tab === 'agent'"
          v-bind="panneau('agent')"
        >
          <AgentsInterrogerAvecAgent
            v-if="agentVu"
            :collection="collection.name"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style>
/* Les blocs de la fiche (composants components/fiche/) partagent ces règles. */
.fiche-bloc { height: 100%; display: flex; flex-direction: column; gap: .75rem; padding: 1.5rem; border: 1px solid var(--border-default-grey); }
.fiche-bloc h2 { margin: 0; }
.fiche-bloc__actions { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem 1rem; margin-top: auto; }
.fiche-discret { color: var(--text-mention-grey); }
.fiche-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: .75rem; margin: 0; padding: 0; }
.fiche-kpis dd { margin: 0; display: flex; flex-direction: column; }
.fiche-kpis b { font-size: 1.5rem; line-height: 1.2; color: var(--text-title-blue-france); font-variant-numeric: tabular-nums; }
.fiche-kpis span { font-size: .8rem; line-height: 1.3; color: var(--text-mention-grey); }
.fiche-avis { list-style: none; margin: 0; padding: 0; }
.fiche-avis li { display: flex; gap: .6rem; padding: .6rem 0; border-top: 1px solid var(--border-default-grey); }
.fiche-avis__question { display: block; font-weight: 500; }
.fiche-avis__motif { display: block; margin: 0; }
.fiche-avis--positif { color: var(--text-default-success); }
.fiche-avis--negatif { color: var(--text-default-warning); }
.fiche-consignes { margin: 0; padding: 1rem; white-space: pre-wrap; font-size: .85rem; background: var(--background-alt-grey); max-height: 24rem; overflow-y: auto; }
</style>

<style scoped>
.fiche-tete { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 1.5rem 2rem; }
.fiche-tete__texte { flex: 1 1 32rem; min-width: 0; display: flex; flex-direction: column; gap: .75rem; }
.fiche-tete__titre { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; }
.fiche-tete__actions { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; }
.fiche-ligne { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem 1.25rem; padding: 1rem 1.5rem; background: var(--background-alt-grey); }
.fiche-ligne__mesure { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25rem .75rem; flex: 1 1 16rem; }
.fiche-ligne__mesure .myrag-quality-bar { flex-basis: 100%; }
.fiche-ligne__lien { margin-left: auto; font-weight: 500; }
.fiche-panneau-tete { display: flex; justify-content: flex-end; margin-bottom: 1rem; }
</style>
