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
      <div class="fr-grid-row fr-grid-row--gutters">
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

          <!-- Badges -->
          <div class="fr-mt-2w fr-mb-4w">
            <span class="fr-badge fr-badge--info">{{ collection.strategy }}</span>
            <span class="fr-badge" :class="sensitivityBadge(collection.sensitivity)">
              {{ collection.sensitivity }}
            </span>
            <span v-if="collection.graph_enabled" class="fr-badge fr-badge--new">Graph actif</span>
            <span v-if="collection.ai_summary_enabled" class="fr-badge fr-badge--new">Resume IA</span>
            <span class="fr-badge">{{ collection.prompt_template }}</span>
          </div>

          <!-- Quick actions -->
          <div class="fr-btns-group fr-btns-group--inline fr-mb-4w">
            <NuxtLink :to="`/c/${id}/playground`" class="fr-btn fr-icon-chat-3-line fr-btn--icon-left">
              Tester le RAG
            </NuxtLink>
            <NuxtLink :to="`/c/${id}/graph`" class="fr-btn fr-btn--secondary fr-icon-mind-map-line fr-btn--icon-left">
              Voir le graph
            </NuxtLink>
            <NuxtLink :to="`/c/${id}/upload`" class="fr-btn fr-btn--secondary fr-icon-upload-line fr-btn--icon-left">
              Uploader
            </NuxtLink>
            <NuxtLink :to="`/c/${id}/config`" class="fr-btn fr-btn--tertiary fr-icon-settings-5-line fr-btn--icon-left">
              Configurer
            </NuxtLink>
            <NuxtLink :to="`/c/${id}/publish`" class="fr-btn fr-btn--tertiary fr-icon-send-plane-line fr-btn--icon-left">
              Publier
            </NuxtLink>
          </div>
        </div>

        <!-- Right: état du circuit, puis qualité -->
        <div class="fr-col-4">
          <CollectifEtapesCollection v-if="etat" :etat="etat" :superadmin="isAdmin" class="fr-mb-2w" @changer="changerEtat" @forcer="forcerEtat" />
          <div v-if="erreurEtat" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"><p>{{ erreurEtat }}</p></div>
          <div class="fr-card">
            <div class="fr-card__body">
              <div class="fr-card__content">
                <h3 class="fr-card__title">Qualite</h3>
                <div class="myrag-quality-bar fr-mt-2w">
                  <div class="myrag-quality-bar__fill"
                       :class="qualityClass(feedbackStats.satisfaction_rate)"
                       :style="{ width: `${feedbackStats.satisfaction_rate * 100}%` }">
                  </div>
                </div>
                <p class="fr-text--sm fr-mt-1w">
                  {{ Math.round(feedbackStats.satisfaction_rate * 100) }}% satisfaction
                  ({{ feedbackStats.positive }} 👍 / {{ feedbackStats.negative }} 👎)
                </p>
                <p v-if="feedbackStats.pending_review > 0" class="fr-text--sm">
                  ⚠ {{ feedbackStats.pending_review }} feedback en attente
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="fr-tabs">
        <ul class="fr-tabs__list" role="tablist">
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'consulter'" @click="tab = 'consulter'">
              Consulter
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'signaler'" @click="tab = 'signaler'">
              Signaler un défaut{{ signalements && signalements.length ? ` (${signalements.filter(s => s.etat !== 'clos').length})` : '' }}
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'proposer'" @click="tab = 'proposer'">
              Proposer une modification{{ propositions && propositions.length ? ` (${propositions.filter(p => p.etat === 'proposee').length})` : '' }}
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'historique'" @click="tab = 'historique'">
              Historique
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'discussion'" @click="tab = 'discussion'">
              Discussion
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'prompt'" @click="tab = 'prompt'">
              System Prompt
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'feedback'" @click="tab = 'feedback'">
              Feedback ({{ feedbackStats.total }})
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'qr'" @click="tab = 'qr'">
              Cache Q&R
            </button>
          </li>
        </ul>

        <!-- Consulter : la grille de contrôle, toujours affichée, même vide -->
        <div v-show="tab === 'consulter'" class="fr-tabs__panel">
          <CollectifGrilleControle v-if="grille" :grille="grille" :garant="estGarant" @enregistrer="enregistrerGrille" @relire="relire" />
          <p v-else class="fr-text--sm" style="color:var(--text-mention-grey)">Grille de contrôle indisponible.</p>
          <div v-if="erreurGrille" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"><p>{{ erreurGrille }}</p></div>
          <p class="fr-text--sm fr-mt-3w">
            <NuxtLink to="/guide/verifier-avant-de-publier" class="fr-link fr-text--sm">Vérifier avant de publier — le guide</NuxtLink>
          </p>
        </div>

        <!-- Signaler un défaut -->
        <div v-show="tab === 'signaler'" class="fr-tabs__panel">
          <CollectifSignalements :signalements="signalements" :garant="estGarant" :actif="capacites.signalements" :fichiers="fichiers"
                                 :signaler="corps => c.signaler(id, corps)" @depose="rechargerCollectif" @traiter="traiterSignalement" />
        </div>

        <!-- Proposer une modification -->
        <div v-show="tab === 'proposer'" class="fr-tabs__panel">
          <CollectifPropositions :propositions="propositions" :garant="estGarant" :proposer="corps => c.proposer(id, corps)"
                                 @deposee="rechargerCollectif" @publier="publierProposition" @refuser="refuserProposition" />
        </div>

        <!-- Historique : le fil -->
        <div v-show="tab === 'historique'" class="fr-tabs__panel">
          <CollectifAvancement :evenements="evenements" :suivant="suivant" abonnable :abonne="abonne" @abonner="abonner" @suite="suite" />
        </div>

        <!-- Discussion -->
        <div v-show="tab === 'discussion'" class="fr-tabs__panel">
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
        <div v-show="tab === 'prompt'" class="fr-tabs__panel">
          <h3>System prompt actuel</h3>
          <p class="fr-text--sm fr-mb-1w">Template: {{ collection.prompt_template }}</p>
          <pre class="fr-p-2w" style="background:#f6f6f6;border-radius:4px;white-space:pre-wrap;font-size:0.85rem;max-height:400px;overflow-y:auto;">{{ collection.system_prompt }}</pre>
          <NuxtLink :to="`/c/${id}/prompt`" class="fr-btn fr-btn--sm fr-mt-2w">
            Editer le prompt
          </NuxtLink>
        </div>

        <!-- Feedback tab -->
        <div v-show="tab === 'feedback'" class="fr-tabs__panel">
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
        <div v-show="tab === 'qr'" class="fr-tabs__panel">
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
