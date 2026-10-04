<template>
  <div class="corpus-docs">
    <div class="corpus-docs__tete">
      <div>
        <h3 class="fr-h6 fr-mb-0">Les documents de la collection</h3>
        <p class="fr-text--sm fr-mb-0" style="color:var(--text-mention-grey)">
          Ce que l'assistant a sous les yeux quand il vous répond. Cliquez sur un document pour le lire.
        </p>
      </div>
      <form class="fr-search-bar corpus-docs__recherche" role="search" @submit.prevent="chercher(true)">
        <label class="fr-label" :for="idRecherche">Chercher un document</label>
        <input :id="idRecherche" v-model="q" class="fr-input" type="search"
               placeholder="Titre, nom de fichier, numéro d'article…" @input="chercherBientot">
        <button class="fr-btn" type="submit" title="Chercher">Chercher</button>
      </form>
    </div>

    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"><p>{{ erreur }}</p></div>
    <p v-else-if="!resultat" class="fr-text--sm fr-mt-2w" aria-live="polite">Lecture des documents…</p>

    <template v-else>
      <p class="fr-text--sm fr-mt-2w fr-mb-1w corpus-docs__plage" aria-live="polite">
        <strong>{{ plage }}</strong>
        <template v-if="q.trim()"> pour « {{ q.trim() }} » — <button type="button" class="corpus-docs__effacer" @click="effacer">tout afficher</button></template>
      </p>

      <p v-if="!resultat.total && !q.trim()" class="fr-text--sm">
        Cette collection n'a encore aucun document.
      </p>

      <ul v-else class="corpus-docs__liste" :aria-busy="charge">
        <li v-for="d in resultat.documents" :key="d.file_id">
          <button type="button" class="corpus-docs__doc" @click="ouvrir(d)">
            <span class="fr-icon-file-text-line fr-icon--sm" aria-hidden="true"></span>
            <span class="corpus-docs__titre">{{ d.titre }}</span>
            <span v-if="d.fichier && d.fichier !== d.titre" class="corpus-docs__fichier">{{ d.fichier }}</span>
          </button>
          <span class="corpus-docs__meta">
            <span class="fr-badge fr-badge--sm fr-badge--no-icon">{{ libelleType(d) }}</span>
            <span v-if="d.taille">{{ d.taille }}</span>
            <a v-if="d.url_source" :href="d.url_source" target="_blank" rel="noopener noreferrer"
               class="fr-link fr-text--xs" :title="`Source d'origine de « ${d.titre} » — nouvelle fenêtre`">source</a>
          </span>
        </li>
      </ul>

      <nav v-if="resultat.pages > 1" class="corpus-docs__pages" role="navigation" aria-label="Pages de documents">
        <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary" :disabled="resultat.page <= 1 || charge" @click="aller(resultat.page - 1)">Précédents</button>
        <span class="fr-text--sm">Page {{ resultat.page }} sur {{ resultat.pages }}</span>
        <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary" :disabled="resultat.page >= resultat.pages || charge" @click="aller(resultat.page + 1)">Suivants</button>
      </nav>
    </template>

    <PlaygroundSourceViewer :open="!!lu" url=""
                            :titre="lu?.doc.titre || ''"
                            :sous-titre="lu && lu.doc.fichier !== lu.doc.titre ? lu.doc.fichier : undefined"
                            :contenu-initial="lu?.texte || ''"
                            :contexte="lu?.contexte || ''"
                            :avis="lu?.avis || ''"
                            :en-chargement="!!lu?.enCours"
                            :lien-source="lu?.doc.url_source || ''"
                            @close="lu = null" />
  </div>
</template>

<script setup lang="ts">
import { avertissementLecture, libellePlage, libelleType, texteDuDocument, type DocumentCorpus, type DocumentLu } from '~/utils/corpus'

/**
 * L'onglet « Documents » de la fiche : consulter le corpus lui-même, pas seulement ce
 * qu'une question en fait remonter. La liste est cherchée et paginée par le serveur
 * (un code entier compte des milliers de fichiers) ; un document s'ouvre dans la fenêtre
 * de lecture du bac à sable.
 */
const props = defineProps<{ collection: string }>()
const { get } = useApi()

interface Page { total: number, page: number, pages: number, par_page: number, documents: DocumentCorpus[] }
const resultat = ref<Page | null>(null)
const q = ref('')
const charge = ref(false)
const erreur = ref('')
const idRecherche = `corpus-recherche-${useId()}`
const lu = ref<{ doc: DocumentCorpus, texte: string, contexte: string, avis: string, enCours: boolean } | null>(null)
const plage = computed(() => resultat.value ? libellePlage(resultat.value, resultat.value.documents.length) : '')

let demande = 0
async function charger(page = 1) {
  const moi = ++demande
  charge.value = true
  erreur.value = ''
  try {
    const params: Record<string, string> = { page: String(page) }
    if (q.value.trim()) params.q = q.value.trim()
    const r = await get(`/api/collections/${props.collection}/documents`, params)
    if (moi === demande) resultat.value = r  // une réponse en retard ne remplace pas la plus récente
  } catch {
    if (moi === demande) erreur.value = "Les documents n'ont pas pu être lus. Réessayez dans un instant."
  } finally {
    if (moi === demande) charge.value = false
  }
}

let minuterie: ReturnType<typeof setTimeout> | null = null
function chercher(tout_de_suite = false) {
  if (minuterie) { clearTimeout(minuterie); minuterie = null }
  if (tout_de_suite) charger(1)
}
function chercherBientot() {
  if (minuterie) clearTimeout(minuterie)
  minuterie = setTimeout(() => charger(1), 350)
}
function effacer() { q.value = ''; charger(1) }
function aller(page: number) { charger(page) }

// Un jeton, pas une comparaison d'objets : `lu.value` est un proxy réactif, jamais égal à l'objet posé.
let lecture = 0
async function ouvrir(d: DocumentCorpus) {
  const moi = ++lecture
  lu.value = { doc: d, texte: '', contexte: '', avis: '', enCours: true }
  try {
    const r: DocumentLu = await get(`/api/collections/${props.collection}/documents/${encodeURIComponent(d.file_id)}`)
    if (moi !== lecture || !lu.value) return  // fermé, ou un autre document ouvert entre-temps
    lu.value = { doc: d, texte: texteDuDocument(r), contexte: r.contexte, avis: avertissementLecture(r), enCours: false }
  } catch {
    if (moi === lecture && lu.value) lu.value = { doc: d, texte: '', contexte: '', avis: "Ce document n'a pas pu être lu. Réessayez dans un instant.", enCours: false }
  }
}

onMounted(() => charger(1))
onBeforeUnmount(() => { if (minuterie) clearTimeout(minuterie) })
</script>

<style scoped>
.corpus-docs__tete { display: flex; flex-wrap: wrap; gap: 1rem 2rem; align-items: flex-end; justify-content: space-between; }
.corpus-docs__recherche { flex: 1 1 320px; max-width: 460px; }
.corpus-docs__effacer { background: none; border: 0; padding: 0; color: var(--text-action-high-blue-france); text-decoration: underline; cursor: pointer; font-size: inherit; }
.corpus-docs__liste { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--border-default-grey); }
.corpus-docs__liste[aria-busy="true"] { opacity: .55; }
.corpus-docs__liste li { display: flex; align-items: center; justify-content: space-between; gap: .5rem 1.5rem; padding: 0; border-bottom: 1px solid var(--border-default-grey); }
.corpus-docs__doc { flex: 1 1 auto; min-width: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: .15rem .6rem; padding: .65rem .5rem; background: none; border: 0; text-align: left; cursor: pointer; color: var(--text-default-grey); }
.corpus-docs__doc:hover { background: var(--background-alt-blue-france); }
.corpus-docs__doc:hover .corpus-docs__titre { text-decoration: underline; }
.corpus-docs__titre { color: var(--text-action-high-blue-france); font-weight: 500; word-break: break-word; }
.corpus-docs__fichier { flex-basis: 100%; padding-left: 1.6rem; font-size: .78rem; color: var(--text-mention-grey); word-break: break-all; }
.corpus-docs__meta { flex: 0 0 auto; display: flex; align-items: center; gap: .75rem; padding-right: .5rem; font-size: .78rem; color: var(--text-mention-grey); white-space: nowrap; }
.corpus-docs__pages { display: flex; align-items: center; justify-content: center; gap: 1rem; margin-top: 1rem; }
@media (max-width: 48em) { .corpus-docs__liste li { flex-direction: column; align-items: stretch; } .corpus-docs__meta { padding: 0 .5rem .6rem 2.1rem; } }
</style>
