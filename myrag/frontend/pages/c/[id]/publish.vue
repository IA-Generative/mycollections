<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ titre }}</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Partager dans Mon assistant</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Partager dans Mon assistant — {{ titre }}</h1>

    <div class="fr-callout fr-mb-4w">
      <h2 class="fr-callout__title fr-h6">Partager dans Mon assistant, qu'est-ce que ça change ?</h2>
      <p class="fr-callout__text fr-text--sm">
        Tant qu'une collection n'est pas partagée, elle ne s'interroge qu'ici, dans son bac à sable.
        <strong>La partager la fait apparaître dans Mon assistant</strong>, là où vos collègues posent
        leurs questions : ils la choisissent dans la liste des modèles, et l'assistant leur répond à
        partir de vos documents, en citant ses sources.
      </p>
      <p class="fr-text--sm fr-mb-0">
        Rien n'est définitif : « Désactiver » la retire de l'assistant sans toucher aux documents,
        et vous pouvez la partager à nouveau quand vous voulez.
      </p>
    </div>

    <div v-if="pub">
      <div v-if="pub.archivee" class="fr-alert fr-alert--warning fr-mb-4w">
        <h2 class="fr-alert__title">Cette collection est archivée</h2>
        <p>Elle n'apparaît plus dans le catalogue et ne peut pas être publiée. Ses documents sont conservés : la désarchiver la remet exactement où elle était.</p>
        <button class="fr-btn fr-btn--sm fr-mt-2w" :disabled="occupe" @click="desarchiver">Désarchiver</button>
      </div>
      <!-- State badge -->
      <div class="fr-mb-4w">
        <span class="fr-badge fr-badge--lg" :class="stateBadge(pub.state)">
          {{ stateLabel(pub.state) }}
        </span>
        <span v-if="pub.published_at" class="fr-text--sm fr-ml-2w">
          Publiée le {{ pub.published_at }} par {{ pub.published_by }}
        </span>
      </div>

      <div class="fr-grid-row fr-grid-row--gutters">
        <div class="fr-col-8">
          <!-- 1. Dans l'assistant -->
          <fieldset class="fr-fieldset fr-mb-4w">
            <legend class="fr-fieldset__legend fr-h5">1. Dans Mon assistant</legend>
            <div class="fr-fieldset__element">
              <div class="fr-checkbox-group">
                <input type="checkbox" id="alias" v-model="form.alias_enabled" />
                <label class="fr-label" for="alias">
                  Proposer la collection dans la liste des modèles de l'assistant
                  <span class="fr-hint-text">
                    Vos collègues la verront sous le nom ci-dessous, à côté des autres modèles. Ils la
                    sélectionnent, posent leur question, et la réponse s'appuie sur vos documents.
                    C'est la façon normale de partager — laissez cette case cochée.
                  </span>
                </label>
              </div>
            </div>
            <div v-if="form.alias_enabled" class="fr-fieldset__element fr-ml-4w">
              <div class="fr-input-group">
                <label class="fr-label" for="nom-fiche">
                  Nom dans l'assistant
                  <span class="fr-hint-text">Laissez vide : c'est le titre de la collection, et il suivra ses corrections.</span>
                </label>
                <input id="nom-fiche" class="fr-input" v-model="form.alias_name" :placeholder="titre" />
              </div>
              <div class="fr-input-group fr-mt-1w">
                <label class="fr-label" for="desc-fiche">
                  Description
                  <span class="fr-hint-text">Une phrase qui dit à quoi sert la collection : elle s'affiche sous son nom dans l'assistant.</span>
                </label>
                <input id="desc-fiche" class="fr-input" v-model="form.alias_description" placeholder="Répond aux questions sur le CESEDA, article par article" />
              </div>
            </div>
          </fieldset>

          <!-- 2. Qui la voit -->
          <fieldset class="fr-fieldset fr-mb-4w">
            <legend class="fr-fieldset__legend fr-h5">2. Qui la verra dans l'assistant</legend>
            <div class="fr-fieldset__element">
              <div v-if="etat && etat.mention" class="fr-alert fr-alert--info fr-alert--sm fr-mb-2w">
                <p>Cette collection est <strong>{{ libelleEtat(etat.etat).toLowerCase() }}</strong> : elle ne peut être partagée qu'avec son groupe.
                  Publier à tous demande de la faire d'abord « publiée à tous » dans son parcours de contrôle
                  (<NuxtLink :to="`/c/${id}`" class="fr-link fr-text--sm">fiche de la collection</NuxtLink>).</p>
              </div>
              <div class="fr-radio-group">
                <input type="radio" id="vis-all" value="all" v-model="form.visibility" :disabled="!!(etat && etat.mention)" />
                <label class="fr-label" for="vis-all">
                  Tout le monde
                  <span class="fr-hint-text">Toute personne connectée à l'assistant. Réservé aux collections vérifiées : leurs réponses engagent.</span>
                </label>
              </div>
            </div>
            <div class="fr-fieldset__element">
              <div class="fr-radio-group">
                <input type="radio" id="vis-group" value="group" v-model="form.visibility" />
                <label class="fr-label" for="vis-group">
                  Un groupe
                  <span class="fr-hint-text">Seuls les membres du groupe indiqué la verront. Pour tester à plusieurs avant d'ouvrir à tous.</span>
                </label>
              </div>
              <div v-if="form.visibility === 'group'" class="fr-input-group fr-ml-4w fr-mt-1w">
                <label class="fr-label" for="vis-groupe-nom">Groupe
                  <span class="fr-hint-text">Son chemin dans l'annuaire, par exemple <code>myrag/{{ id }}</code>.</span>
                </label>
                <input id="vis-groupe-nom" class="fr-input" v-model="form.visibility_group" :placeholder="`myrag/${id}`" />
              </div>
            </div>
            <p class="fr-fieldset__element fr-text--xs fr-mb-0" style="color:var(--text-mention-grey)">
              Ce réglage ne concerne que l'assistant. Qui peut ouvrir cette fiche et son bac à sable se règle dans
              <NuxtLink :to="`/c/${id}/config`" class="fr-link fr-text--xs">Réglages → Portée</NuxtLink>.
            </p>
          </fieldset>

          <!-- 3. Ce qui n'est pas encore en service : dit, plutôt que proposé -->
          <fieldset class="fr-fieldset fr-mb-4w" disabled>
            <legend class="fr-fieldset__legend fr-h5">
              3. Autres façons de l'interroger
              <span class="fr-badge fr-badge--sm fr-badge--no-icon fr-ml-1w">à venir</span>
            </legend>
            <div class="fr-fieldset__element">
              <p class="fr-text--sm" style="color:var(--text-mention-grey)">
                Ces deux modes sont prévus, mais <strong>pas encore en service</strong> : les cocher n'aurait aucun effet aujourd'hui.
              </p>
              <div class="fr-checkbox-group">
                <input type="checkbox" id="tool" v-model="form.tool_enabled" disabled />
                <label class="fr-label" for="tool">
                  Comme outil, dans n'importe quelle conversation
                  <span class="fr-hint-text">L'assistant irait chercher de lui-même dans la collection quand la question s'y prête, quel que soit le modèle choisi.</span>
                </label>
              </div>
              <div class="fr-checkbox-group fr-mt-1w">
                <input type="checkbox" id="embed" v-model="form.embed_enabled" disabled />
                <label class="fr-label" for="embed">
                  En tapant #{{ id }} dans une question
                  <span class="fr-hint-text">Un raccourci pour faire appel à la collection le temps d'une question.</span>
                </label>
              </div>
            </div>
          </fieldset>

          <!-- Actions -->
          <div class="fr-btns-group fr-btns-group--inline">
            <button v-if="pub.state !== 'published'" class="fr-btn" @click="publish" :disabled="publishing || pub.archivee"
                    title="Fait apparaître la collection dans l'assistant, pour les personnes choisies ci-dessus.">
              {{ publishing ? 'Partage en cours…' : 'Partager dans Mon assistant' }}
            </button>
            <button v-if="pub.state === 'published'" class="fr-btn" @click="publish" :disabled="publishing || pub.archivee"
                    title="Applique vos changements (nom, description, qui la voit) à la collection déjà publiée.">
              {{ publishing ? 'Mise à jour…' : 'Mettre à jour' }}
            </button>
            <button v-if="pub.state === 'published'" class="fr-btn fr-btn--secondary" :disabled="occupe" @click="unpublish"
                    title="Retire la collection de l'assistant. Les documents restent, et vous pourrez republier.">
              Désactiver
            </button>
          </div>

          <div v-if="erreur" class="fr-alert fr-alert--error fr-mt-2w"><p>{{ erreur }}</p></div>
          <div v-if="result" class="fr-alert fr-mt-2w"
               :class="owuiError ? 'fr-alert--warning' : 'fr-alert--success'">
            <p>{{ result }}</p>
            <p v-if="owuiError" class="fr-text--sm" style="margin-top:0.4rem;">
              <strong>Assistant :</strong> {{ owuiError }}
            </p>
          </div>
        </div>

        <!-- Archiver : loin de « Publier », et jamais sur un seul clic -->
        <div v-if="!pub.archivee" class="fr-col-12 fr-mt-4w">
          <div class="publier-retrait">
            <div>
              <h3 class="fr-h6 fr-mb-1v">Retirer la collection</h3>
              <p class="fr-text--sm fr-mb-0">
                Archiver la retire du catalogue et empêche de la publier. Rien n'est supprimé : ses documents sont conservés,
                et vous pourrez la désarchiver d'ici.
              </p>
            </div>
            <button class="fr-btn fr-btn--tertiary fr-btn--sm" :disabled="occupe" @click="confirmerArchivage = true">Archiver…</button>
          </div>
        </div>

        <!-- Right: History -->
        <div class="fr-col-4">
          <h3 class="fr-h5">Historique</h3>
          <div v-if="pub.history && pub.history.length > 0">
            <div v-for="(h, i) in pub.history.slice().reverse()" :key="i" class="fr-mb-1w">
              <p class="fr-text--sm">
                <strong>{{ libelleActionPublication(h.action) }}</strong> — {{ h.at }}<br>
                <span v-if="h.by">par {{ h.by }}</span>
              </p>
            </div>
          </div>
          <p v-else class="fr-text--sm">Aucun historique.</p>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <dialog v-if="confirmerArchivage" open class="fr-modal fr-modal--opened" aria-labelledby="archiver-titre"
              style="display:block;background:rgba(22,22,22,.64);z-index:1000;" @click.self="confirmerArchivage = false" @keydown.esc="confirmerArchivage = false">
        <div class="fr-container fr-container--fluid fr-container-md">
          <div class="fr-grid-row fr-grid-row--center">
            <div class="fr-col-12 fr-col-md-8 fr-col-lg-6">
              <div class="fr-modal__body">
                <div class="fr-modal__header">
                  <button class="fr-btn--close fr-btn" title="Fermer" @click="confirmerArchivage = false">Fermer</button>
                </div>
                <div class="fr-modal__content">
                  <h1 id="archiver-titre" class="fr-modal__title">Archiver « {{ titre }} » ?</h1>
                  <p>La collection disparaîtra du catalogue et ne pourra plus être publiée tant qu'elle sera archivée.</p>
                  <p class="fr-text--sm">Ses documents, ses réglages et son historique sont conservés. Vous pourrez la désarchiver depuis cette page.</p>
                </div>
                <div class="fr-modal__footer">
                  <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-lg">
                    <li><button ref="btnAnnuler" class="fr-btn fr-btn--secondary" @click="confirmerArchivage = false">Annuler</button></li>
                    <li><button class="fr-btn" :disabled="occupe" @click="archive">Archiver la collection</button></li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </dialog>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { libelleEtat, messageErreur } from '~/utils/collectif'
import { libelleActionPublication } from '~/utils/libelles'
const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
const { get, post } = useApi()

const pub = ref<any>(null)
const etat = ref<any>(null)
const publishing = ref(false)
const result = ref('')
const owuiError = ref('')
const erreur = ref('')
const occupe = ref(false)
const confirmerArchivage = ref(false)
const btnAnnuler = ref<HTMLButtonElement | null>(null)
// Le bouton sûr reçoit le focus : « Entrée » par réflexe n'archive pas.
watch(confirmerArchivage, (o) => { if (o) nextTick(() => btnAnnuler.value?.focus()) })

const allMethods = ['search_collection', 'view_article', 'explore_graph', 'browse_collection']

const form = ref({
  alias_enabled: true,
  alias_name: '',
  alias_description: '',
  tool_enabled: false,
  tool_methods: [...allMethods],
  embed_enabled: false,
  visibility: 'all',
  visibility_group: '',
})

function stateBadge(s: string) {
  return {
    draft: 'fr-badge--info',
    published: 'fr-badge--success',
    disabled: 'fr-badge--warning',
    archived: '',
  }[s] || ''
}

function stateLabel(s: string) {
  return { draft: 'Brouillon', published: 'Publiée', disabled: 'Désactivée', archived: 'Archivée' }[s] || s
}

async function publish() {
  publishing.value = true
  result.value = ''
  try {
    owuiError.value = ''
    erreur.value = ''
    // L'API lit `visibility_groups` (une LISTE). La page envoyait `visibility_group` (une chaîne),
    // que l'API ignorait : publier « à un groupe » publiait pour personne.
    const groupe = form.value.visibility_group.trim()
    const corps = { ...form.value, visibility_groups: form.value.visibility === 'group' && groupe ? [groupe] : [] }
    const data = await post(`/api/collections/${id}/publish`, corps)
    pub.value = await get(`/api/collections/${id}/publication`)
    const base = 'Collection partagée'
    if (data?.owui?.synced) {
      result.value = `${base} : elle apparaît dans l'assistant sous le modèle « ${data.owui.model_id} ».`
    } else if (data?.owui?.error) {
      result.value = base
      owuiError.value = data.owui.error
    } else {
      result.value = base
    }
  } catch (e: any) {
    erreur.value = messageErreur(e)
  }
  publishing.value = false
}

/** Un geste d'écriture : jamais deux à la fois, et un refus (403, 409…) se dit au lieu de se perdre. */
async function geste(chemin: string) {
  occupe.value = true
  erreur.value = ''
  result.value = ''
  try {
    await post(`/api/collections/${id}/${chemin}`)
    pub.value = await get(`/api/collections/${id}/publication`)
  } catch (e) {
    erreur.value = messageErreur(e)
  }
  occupe.value = false
}
const unpublish = () => geste('unpublish')
const desarchiver = () => geste('unarchive')
async function archive() {
  confirmerArchivage.value = false
  await geste('archive')
}

onMounted(async () => {
  try {
    etat.value = await get(`/api/collections/${id}/etat`)
    if (etat.value?.mention) form.value.visibility = 'group'
  } catch (e) {}
  try {
    pub.value = await get(`/api/collections/${id}/publication`)
    if (pub.value) {
      form.value.alias_enabled = pub.value.alias_enabled
      form.value.alias_name = pub.value.alias_name || ''
      form.value.alias_description = pub.value.alias_description || ''
      form.value.tool_enabled = pub.value.tool_enabled
      form.value.tool_methods = pub.value.tool_methods || [...allMethods]
      form.value.embed_enabled = pub.value.embed_enabled
      form.value.visibility = pub.value.visibility || (etat.value?.mention ? 'group' : 'all')
      if (etat.value?.mention && form.value.visibility === 'all') form.value.visibility = 'group'
      form.value.visibility_group = (pub.value.visibility_groups || [])[0] || pub.value.visibility_group || `myrag/${id}`
    }
  } catch (e) {}
})
</script>

<style scoped>
.publier-retrait { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem 2rem;
  border: 1px solid var(--border-default-grey); border-left: 4px solid var(--border-plain-warning); padding: 1rem 1.25rem; }
.publier-retrait > div { flex: 1 1 320px; max-width: 70ch; }
</style>
