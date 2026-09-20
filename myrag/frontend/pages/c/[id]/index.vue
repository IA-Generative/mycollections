<template>
  <div>
    <!-- Breadcrumb -->
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">{{ titre }}</a></li>
      </ol>
    </nav>

    <div v-if="loading" class="fr-callout"><p>Chargement...</p></div>

    <!-- Collection not found in MyRAG DB (may exist as bare OpenRAG partition) -->
    <div v-else-if="!collection" class="fr-alert fr-alert--warning">
      <h3 class="fr-alert__title">Collection « {{ id }} » sans configuration MyRAG</h3>
      <p>
        Cette collection existe peut-être côté OpenRAG mais n'a pas encore de
        configuration MyRAG (description, stratégie, responsable…).
        <span v-if="loadError" class="fr-text--sm" style="color:#666;">({{ loadError }})</span>
      </p>
      <p>
        Tu peux la rattacher à une config MyRAG minimale puis compléter les
        métadonnées depuis les onglets habituels — aucune donnée OpenRAG n'est
        touchée.
      </p>
      <div v-if="adoptError" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w">
        <p>{{ adoptError }}</p>
      </div>
      <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
        <button class="fr-btn" @click="adoptCollection" :disabled="adopting">
          {{ adopting ? 'Création en cours…' : 'Rattacher cette collection' }}
        </button>
        <NuxtLink to="/admin/catalog" class="fr-btn fr-btn--secondary">
          Retour au catalogue
        </NuxtLink>
      </div>
    </div>

    <div v-else>
      <div class="fr-grid-row fr-grid-row--gutters fr-mb-3w">
        <!-- Left: collection info -->
        <div class="fr-col-8">
          <h1 class="fr-h2 fr-mb-1w">{{ titre }}</h1>
          <p class="fr-text--sm fr-mb-2w" style="color:var(--text-mention-grey);">
            Identifiant : <code title="Ce que tapent les applications : openrag-…">{{ collection.name }}</code>
            <template v-if="libelleCategorie"> · {{ libelleCategorie }}</template>
          </p>
          <p v-if="etat && etat.mention" class="collectif-mention fr-mb-1w">⚠ {{ etat.mention }} — servie à son groupe seulement</p>
          <p class="fr-text--lg">{{ collection.description || 'Pas de description' }}</p>

          <!-- Où interroger : servi par l'API seulement quand la collection est
               publiée à tous — on ne promet rien qui ne soit pas servi. -->
          <div v-if="collection.acces" class="fr-callout fr-callout--green-emeraude fr-mb-3w">
            <h3 class="fr-callout__title fr-h6">Où interroger cette collection</h3>
            <p class="fr-callout__text fr-text--sm">
              Ici, dans le bac à sable, pour l'essayer — mais aussi :
            </p>
            <ul class="fr-text--sm">
              <li><strong>dans l'agent conversationnel de MirAI Next</strong>, en choisissant le modèle
                <code>{{ collection.acces.assistant.model_id }}</code> ;</li>
              <li v-if="collection.acces.api"><strong>par l'API, depuis vos SI</strong> :
                <code>POST {{ collection.acces.api.chat }}</code> avec <code>"model": "{{ collection.acces.api.model }}"</code>
                (format OpenAI), ou <code>GET {{ collection.acces.api.search }}</code> pour la recherche seule —
                sur clé d'API à demander à l'équipe de la bêta ;</li>
              <li><strong>dans vos outils bureautiques</strong> : greffon LibreOffice à venir.</li>
            </ul>
            <p class="fr-text--sm fr-mb-0"><NuxtLink to="/guide/interroger-depuis-vos-si" class="fr-link">Le guide : interroger depuis vos SI</NuxtLink></p>
          </div>

          <!-- Badges : trois réglages techniques, chacun expliqué au survol et au focus -->
          <div class="fr-mt-2w fr-mb-4w fiche-badges">
            <span v-for="b in badges" :key="b.cle" class="fr-badge" :class="b.classe" :title="b.aide" tabindex="0">{{ b.libelle }}</span>
          </div>

          <!-- Dans un groupe DSFR, la position de l'icône se déclare sur le GROUPE : sans
               `fr-btns-group--icon-left`, il réduit chaque bouton à son icône, libellé masqué. -->
          <div class="fr-btns-group fr-btns-group--inline fr-btns-group--icon-left fr-mb-4w">
            <NuxtLink v-for="a in actions" :key="a.vers" :to="a.vers" class="fr-btn fr-btn--icon-left"
                      :class="[a.icone, a.rang]" :title="a.aide">
              {{ a.libelle }}
            </NuxtLink>
          </div>
        </div>

        <!-- Right: état du circuit, puis qualité -->
        <div class="fr-col-4">
          <CollectifEtapesCollection v-if="etat" :etat="etat" :superadmin="isAdmin" class="fr-mb-2w" @changer="changerEtat" @forcer="forcerEtat" />
          <div v-if="erreurEtat" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"><p>{{ erreurEtat }}</p></div>
          <!-- Un simple encadré, comme le parcours d'états au-dessus — pas une `.fr-card` : elle vaut
               `height: 100%` (posée sous le parcours d'états, elle débordait sur les onglets) et
               réordonne son contenu (le titre passait sous la jauge). -->
          <section class="fiche-qualite" aria-labelledby="fiche-qualite-titre">
            <h3 id="fiche-qualite-titre" class="fr-h6 fr-mb-1w">Qualité</h3>
            <div class="myrag-quality-bar">
              <div class="myrag-quality-bar__fill"
                   :class="qualityClass(feedbackStats.satisfaction_rate)"
                   :style="{ width: `${feedbackStats.satisfaction_rate * 100}%` }">
              </div>
            </div>
            <p class="fr-text--sm fr-mt-1w fr-mb-0">
              <template v-if="feedbackStats.total">
                {{ Math.round(feedbackStats.satisfaction_rate * 100) }} % de satisfaction
                ({{ feedbackStats.positive }} 👍 / {{ feedbackStats.negative }} 👎)
              </template>
              <template v-else>Aucun avis pour l'instant.</template>
            </p>
            <p v-if="feedbackStats.pending_review > 0" class="fr-text--sm fr-mt-1w fr-mb-0">
              ⚠ {{ feedbackStats.pending_review }} avis en attente de relecture
            </p>
          </section>
        </div>
      </div>

      <!-- Tabs -->
      <div class="fr-tabs">
        <!-- Le DSFR cache tout panneau qui n'a pas `fr-tabs__panel--selected` (visibility: hidden) :
             c'est son JavaScript qui pose cette classe, et nous ne le chargeons pas. Vue la pose. -->
        <ul class="fr-tabs__list" role="tablist" aria-label="Rubriques de la collection" @keydown="clavierOnglets">
          <li v-for="o in onglets" :key="o.cle" role="presentation">
            <button :id="`onglet-${o.cle}`" type="button" class="fr-tabs__tab" role="tab"
                    :aria-selected="tab === o.cle" :aria-controls="`panneau-${o.cle}`"
                    :tabindex="tab === o.cle ? 0 : -1" @click="tab = o.cle">
              {{ o.libelle }}
            </button>
          </li>
        </ul>

        <!-- Consulter : la grille de contrôle, toujours affichée, même vide -->
        <div v-show="tab === 'consulter'" v-bind="panneau('consulter')">
          <CollectifGrilleControle v-if="grille" :grille="grille" :garant="estGarant" @enregistrer="enregistrerGrille" @relire="relire" />
          <p v-else class="fr-text--sm" style="color:var(--text-mention-grey)">Grille de contrôle indisponible.</p>
          <div v-if="erreurGrille" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"><p>{{ erreurGrille }}</p></div>
          <p class="fr-text--sm fr-mt-3w">
            <NuxtLink to="/guide/verifier-avant-de-publier" class="fr-link fr-text--sm">Vérifier avant de publier — le guide</NuxtLink>
          </p>
        </div>

        <!-- Documents : le corpus lui-même. Monté à la première ouverture — la liste d'un code
             entier ne se lit pas tant que personne ne la demande. -->
        <div v-show="tab === 'documents'" v-bind="panneau('documents')">
          <CorpusDocuments v-if="documentsVus" :collection="id" />
        </div>

        <!-- Signaler un défaut -->
        <div v-show="tab === 'signaler'" v-bind="panneau('signaler')">
          <CollectifSignalements :signalements="signalements" :garant="estGarant" :actif="capacites.signalements" :fichiers="fichiers"
                                 :signaler="corps => c.signaler(id, corps)" @depose="rechargerCollectif" @traiter="traiterSignalement" />
        </div>

        <!-- Proposer une modification -->
        <div v-show="tab === 'proposer'" v-bind="panneau('proposer')">
          <CollectifPropositions :propositions="propositions" :garant="estGarant" :proposer="corps => c.proposer(id, corps)"
                                 @deposee="rechargerCollectif" @publier="publierProposition" @refuser="refuserProposition" />
        </div>

        <!-- Historique : le fil -->
        <div v-show="tab === 'historique'" v-bind="panneau('historique')">
          <CollectifAvancement :evenements="evenements" :suivant="suivant" abonnable :abonne="abonne" @abonner="abonner" @suite="suite" />
        </div>

        <!-- Discussion -->
        <div v-show="tab === 'discussion'" v-bind="panneau('discussion')">
          <div class="fr-callout">
            <h3 class="fr-callout__title">La discussion se tient dans les forums Mirai</h3>
            <p class="fr-callout__text">
              Les échanges entre contributeurs passent par le salon Tchap de la bêta. Ce qui engage la collection
              — un défaut, une modification — se dépose ici, dans les onglets « Signaler » et « Proposer », pour rester tracé.
            </p>
            <button class="fr-btn fr-btn--sm fr-btn--secondary fr-mt-2w" @click="abonner(!abonne)">{{ abonne ? 'Abonné·e au fil' : "S'abonner au fil d'avancement" }}</button>
          </div>
        </div>

        <!-- Prompt tab -->
        <div v-show="tab === 'prompt'" v-bind="panneau('prompt')">
          <h3>System prompt actuel</h3>
          <p class="fr-text--sm fr-mb-1w">Template: {{ collection.prompt_template }}</p>
          <pre class="fr-p-2w" style="background:#f6f6f6;border-radius:4px;white-space:pre-wrap;font-size:0.85rem;max-height:400px;overflow-y:auto;">{{ collection.system_prompt }}</pre>
          <NuxtLink :to="`/c/${id}/prompt`" class="fr-btn fr-btn--sm fr-mt-2w">
            Editer le prompt
          </NuxtLink>
        </div>

        <!-- Feedback tab -->
        <div v-show="tab === 'feedback'" v-bind="panneau('feedback')">
          <div v-if="feedbackItems.length === 0" class="fr-callout">
            <p>Aucun feedback pour cette collection.</p>
          </div>
          <div v-else class="fr-table">
            <table>
              <thead>
                <tr><th>Question</th><th>Note</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                <tr v-for="fb in feedbackItems" :key="fb.id">
                  <td>{{ fb.question.substring(0, 80) }}...</td>
                  <td>{{ fb.rating > 0 ? '👍' : '👎' }}</td>
                  <td><span class="fr-badge fr-badge--sm">{{ fb.status }}</span></td>
                  <td>
                    <button v-if="fb.status === 'pending'" class="fr-btn fr-btn--sm fr-btn--tertiary"
                            @click="reviewFeedback(fb.id, 'reviewed')">Valider</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Q&R tab -->
        <div v-show="tab === 'qr'" v-bind="panneau('qr')">
          <p class="fr-text--sm">Cache Q&R — reponses curees pour les questions frequentes.</p>
          <NuxtLink :to="`/c/${id}/config`" class="fr-btn fr-btn--sm fr-mt-2w">
            Gerer le cache Q&R
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { messageErreur } from '~/utils/collectif'
const route = useRoute()
const id = route.params.id as string
const { get, patch } = useApi()
const c = useCollectif()
const { isAdmin } = useAdminAuth()
const { capacites, charger: chargerCapacites } = useCapacites()

// ─── Le circuit collaboratif ─────────────────────────────────────────────────
const etat = ref<any>(null)
const grille = ref<any>(null)
const propositions = ref<any[] | null>([])
const signalements = ref<any[] | null>([])
const evenements = ref<any[] | null>([])
const suivant = ref<string | null>(null)
const abonne = ref(false)
const fichiers = ref<any[]>([])
const erreurEtat = ref('')
const erreurGrille = ref('')
const estGarant = computed(() => !!(etat.value && (etat.value.je_suis_garant || isAdmin.value)))

async function chargerCollectif() {
  await chargerCapacites()
  try { etat.value = await c.etat(id) } catch { etat.value = null }
  try { grille.value = (await c.grille(id)).grille } catch { grille.value = null }
  await rechargerCollectif()
  try { fichiers.value = (await get(`/api/ingest/${id}/sources`)).sources || [] } catch { fichiers.value = [] }
}
async function rechargerCollectif() {
  try { propositions.value = (await c.propositions(id)).propositions } catch { propositions.value = null }
  try { signalements.value = (await c.signalements(id)).signalements } catch { signalements.value = null }
  try { const j = await c.journalCollection(id); evenements.value = j.evenements; suivant.value = j.suivant } catch { evenements.value = null }
}
async function suite(avant: string) { const j = await c.journalCollection(id, { avant }); evenements.value = [...(evenements.value || []), ...j.evenements]; suivant.value = j.suivant }
async function changerEtat(cible: string) {
  erreurEtat.value = ''
  try { etat.value = await c.changerEtat(id, cible); await rechargerCollectif() } catch (e) { erreurEtat.value = messageErreur(e) }
}
async function forcerEtat(cible: string, motif: string) {
  erreurEtat.value = ''
  try { etat.value = await c.changerEtat(id, cible, true, motif); await rechargerCollectif() } catch (e) { erreurEtat.value = messageErreur(e) }
}
async function enregistrerGrille(champs: any) {
  erreurGrille.value = ''
  try { grille.value = (await c.majGrille(id, champs)).grille; etat.value = await c.etat(id); await rechargerCollectif() } catch (e) { erreurGrille.value = messageErreur(e) }
}
async function relire() {
  erreurGrille.value = ''
  try { grille.value = (await c.relire(id)).grille; etat.value = await c.etat(id); await rechargerCollectif() } catch (e) { erreurGrille.value = messageErreur(e) }
}
async function publierProposition(pid: string) { try { await c.publierProposition(id, pid); await rechargerCollectif() } catch (e) { erreurGrille.value = messageErreur(e) } }
async function refuserProposition(pid: string, motif: string) { try { await c.refuserProposition(id, pid, motif); await rechargerCollectif() } catch (e) { erreurGrille.value = messageErreur(e) } }
async function traiterSignalement(sid: string, e2: string) { try { await c.traiterSignalement(id, sid, e2); await rechargerCollectif() } catch (e) { erreurGrille.value = messageErreur(e) } }
async function abonner(oui: boolean) { try { await c.abonnerCollection(id, oui); abonne.value = oui } catch (e) { erreurGrille.value = messageErreur(e) } }

const collection = ref<any>(null)
const { titre, retenir } = useTitreCollection(id, { charger: false })
const libelleCategorie = ref('')
const loadError = ref<string>('')
const adopting = ref(false)
const adoptError = ref<string>('')
const feedbackStats = ref({ satisfaction_rate: 0, positive: 0, negative: 0, total: 0, pending_review: 0 })
const feedbackItems = ref<any[]>([])
const loading = ref(true)
const tab = ref('consulter')

/** Les rubriques de la fiche, dans l'ordre de la rangée d'onglets. */
const onglets = computed(() => {
  const ouverts = (l: any[] | null, garde: (x: any) => boolean) => { const n = (l || []).filter(garde).length; return n ? ` (${n})` : '' }
  return [
    { cle: 'consulter', libelle: 'Consulter' },
    { cle: 'documents', libelle: 'Documents' },
    { cle: 'signaler', libelle: `Signaler un défaut${ouverts(signalements.value, s => s.etat !== 'clos')}` },
    { cle: 'proposer', libelle: `Proposer une modification${ouverts(propositions.value, p => p.etat === 'proposee')}` },
    { cle: 'historique', libelle: 'Historique' },
    { cle: 'discussion', libelle: 'Discussion' },
    { cle: 'prompt', libelle: 'Prompt système' },
    { cle: 'feedback', libelle: `Avis (${feedbackStats.value.total})` },
    { cle: 'qr', libelle: 'Cache Q&R' },
  ]
})

/** Les cinq gestes de la fiche. `aide` s'affiche au survol et au focus : dire ce que le bouton FAIT. */
const actions = computed(() => [
  { vers: `/c/${id}/playground`, libelle: 'Tester le RAG', icone: 'fr-icon-chat-3-line', rang: '',
    aide: "Le bac à sable : posez une question à la collection et voyez la réponse, avec les passages sur lesquels elle s'appuie." },
  { vers: `/c/${id}/graph`, libelle: 'Voir le graph', icone: 'fr-icon-share-line', rang: 'fr-btn--secondary',
    aide: "La carte des renvois entre documents : quel article cite quel autre. Disponible quand le graphe est activé pour la collection." },
  { vers: `/c/${id}/upload`, libelle: 'Uploader', icone: 'fr-icon-upload-line', rang: 'fr-btn--secondary',
    aide: "Ajouter des documents à la collection : fichiers de votre poste, adresse web, dossier Drive." },
  { vers: `/c/${id}/config`, libelle: 'Configurer', icone: 'fr-icon-settings-5-line', rang: 'fr-btn--tertiary',
    aide: "Les réglages : titre et description, qui peut lire la collection, sensibilité des données, contact, cache de réponses." },
  { vers: `/c/${id}/publish`, libelle: 'Publier', icone: 'fr-icon-send-plane-line', rang: 'fr-btn--tertiary',
    aide: "Rendre la collection disponible dans l'assistant MirAI, et choisir qui la voit." },
])

const STRATEGIES: Record<string, string> = {
  auto: "Découpage automatique : l'outil choisit comment couper chaque document en passages, selon sa forme.",
  article: "Découpage par article : un passage par article — fait pour les codes et les textes juridiques.",
  chunk: "Découpage par longueur : des passages de taille régulière, sans tenir compte de la structure.",
  directory: "Découpage par dossier : la structure des dossiers d'origine est conservée.",
}
const SENSIBILITES: Record<string, string> = {
  public: "Données publiques : rien de sensible, la collection peut être ouverte largement.",
  internal: "Données internes au ministère : à ne pas diffuser à l'extérieur.",
  personal: "Contient des données personnelles : diffusion à limiter, et à justifier.",
  restricted: "Diffusion restreinte : réservée aux personnes habilitées.",
  confidential: "Confidentiel : accès au plus petit nombre.",
}
/** Les réglages affichés en badges, avec ce qu'ils veulent dire pour qui ne les a pas choisis. */
const badges = computed(() => {
  const col = collection.value || {}
  const liste = [
    { cle: 'strategie', libelle: col.strategy, classe: 'fr-badge--info',
      aide: STRATEGIES[col.strategy] || `Mode de découpage des documents en passages : « ${col.strategy} ».` },
    { cle: 'sensibilite', libelle: col.sensitivity, classe: sensitivityBadge(col.sensitivity),
      aide: SENSIBILITES[col.sensitivity] || `Sensibilité des données : « ${col.sensitivity} ».` },
  ]
  if (col.graph_enabled) liste.push({ cle: 'graphe', libelle: 'Graph actif', classe: 'fr-badge--new', aide: "Les renvois entre documents sont cartographiés : voir « Voir le graph »." })
  if (col.ai_summary_enabled) liste.push({ cle: 'resume', libelle: 'Résumé IA', classe: 'fr-badge--new', aide: "Chaque document reçoit un résumé automatique, qui aide la recherche à le retrouver." })
  liste.push({ cle: 'prompt', libelle: col.prompt_template, classe: '',
    aide: `Modèle de consigne donné à l'assistant : « ${col.prompt_template} ». Il fixe le ton et la façon de citer — voir l'onglet « Prompt système ».` })
  return liste.filter(b => b.libelle)
})

const documentsVus = ref(false)
watch(tab, (t) => { if (t === 'documents') documentsVus.value = true })

/** Ce qu'un panneau doit porter pour que le DSFR le montre, et pour qu'un lecteur d'écran le relie à son onglet. */
function panneau(cle: string) {
  return {
    id: `panneau-${cle}`,
    class: ['fr-tabs__panel', { 'fr-tabs__panel--selected': tab.value === cle }],
    role: 'tabpanel',
    'aria-labelledby': `onglet-${cle}`,
    tabindex: 0,
  }
}

/** Flèches, Début et Fin parcourent la rangée, comme le veut le motif « onglets ». */
function clavierOnglets(ev: KeyboardEvent) {
  const cles = onglets.value.map(o => o.cle)
  const i = cles.indexOf(tab.value)
  const vers = { ArrowRight: (i + 1) % cles.length, ArrowLeft: (i - 1 + cles.length) % cles.length, Home: 0, End: cles.length - 1 }[ev.key]
  if (vers === undefined) return
  ev.preventDefault()
  tab.value = cles[vers]
  nextTick(() => document.getElementById(`onglet-${cles[vers]}`)?.focus())
}

function sensitivityBadge(s: string) {
  return { public: 'fr-badge--success', internal: 'fr-badge--info', restricted: 'fr-badge--warning', confidential: 'fr-badge--error' }[s] || ''
}

function qualityClass(rate: number) {
  if (rate >= 0.7) return 'myrag-quality-bar__fill--good'
  if (rate >= 0.4) return 'myrag-quality-bar__fill--medium'
  return 'myrag-quality-bar__fill--bad'
}

async function reviewFeedback(fbId: string, status: string) {
  await patch(`/api/feedback/${id}/${fbId}/review`, { status })
  feedbackItems.value = feedbackItems.value.map(f => f.id === fbId ? { ...f, status } : f)
}

/**
 * Create a minimal MyRAG config for a collection that exists as an OpenRAG
 * partition but has no DB record. Backend POST is idempotent on the OpenRAG
 * side (create_partition returns {status: exists} if the partition is
 * already there), so this is safe to call on an orphan partition.
 */
async function adoptCollection() {
  adopting.value = true
  adoptError.value = ''
  try {
    const { post } = useApi()
    await post('/api/collections', {
      name: id,
      description: '',
      strategy: 'auto',
      sensitivity: 'public',
      scope: 'group',
    })
    // Reload the whole page so onMounted re-runs with the new DB record.
    window.location.reload()
  } catch (e: any) {
    adoptError.value = e?.message || 'Echec de la creation.'
    adopting.value = false
  }
}

onMounted(async () => {
  try {
    collection.value = await get(`/api/collections/${id}`)
    retenir(collection.value)
  } catch (e: any) {
    loadError.value = e?.message || 'erreur de chargement'
    collection.value = null
    loading.value = false
    return
  }
  if (collection.value?.categorie) {
    useCategories().lister()
      .then((cats) => { libelleCategorie.value = cats.find(k => k.cle === collection.value.categorie)?.libelle || '' })
      .catch(() => {})
  }
  // Le circuit collaboratif — chaque bloc tombe seul, jamais la page.
  chargerCollectif()
  // Feedback is optional — missing stats shouldn't blank the page.
  try {
    feedbackStats.value = await get(`/api/feedback/${id}/stats`)
    const fbData = await get(`/api/feedback/${id}`)
    feedbackItems.value = fbData.feedback || []
  } catch {
    // best-effort
  }
  loading.value = false
})
</script>

<style scoped>
.fiche-badges { display: flex; flex-wrap: wrap; gap: .4rem; }
.fiche-badges .fr-badge { cursor: help; }
.fiche-qualite { border: 1px solid var(--border-default-grey); padding: 1rem 1.25rem; background: var(--background-default-grey); }
</style>
