<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ titre }}</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Publication</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Publication — {{ titre }}</h1>

    <div class="fr-callout fr-mb-4w">
      <h2 class="fr-callout__title fr-h6">Publier, qu'est-ce que ça change ?</h2>
      <p class="fr-callout__text fr-text--sm">
        Tant qu'une collection n'est pas publiée, elle ne s'interroge qu'ici, dans son bac à sable.
        <strong>La publier la fait apparaître dans l'assistant MirAI</strong>, là où vos collègues posent
        leurs questions : ils la choisissent dans la liste des modèles, et l'assistant leur répond à
        partir de vos documents, en citant ses sources.
      </p>
      <p class="fr-text--sm fr-mb-0">
        Rien n'est définitif : « Désactiver » la retire de l'assistant sans toucher aux documents,
        et vous pouvez republier quand vous voulez.
      </p>
    </div>

    <div v-if="pub">
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
            <legend class="fr-fieldset__legend fr-h5">1. Dans l'assistant MirAI</legend>
            <div class="fr-fieldset__element">
              <div class="fr-checkbox-group">
                <input type="checkbox" id="alias" v-model="form.alias_enabled" />
                <label class="fr-label" for="alias">
                  Proposer la collection dans la liste des modèles de l'assistant
                  <span class="fr-hint-text">
                    Vos collègues la verront sous le nom ci-dessous, à côté des autres modèles. Ils la
                    sélectionnent, posent leur question, et la réponse s'appuie sur vos documents.
                    C'est la façon normale de publier — laissez cette case cochée.
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
              <NuxtLink :to="`/c/${id}/config`" class="fr-link fr-text--xs">Configurer → Portée</NuxtLink>.
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
            <button v-if="pub.state !== 'published'" class="fr-btn" @click="publish" :disabled="publishing"
                    title="Fait apparaître la collection dans l'assistant, pour les personnes choisies ci-dessus.">
              {{ publishing ? 'Publication…' : 'Publier' }}
            </button>
            <button v-if="pub.state === 'published'" class="fr-btn" @click="publish" :disabled="publishing"
                    title="Applique vos changements (nom, description, qui la voit) à la collection déjà publiée.">
              {{ publishing ? 'Mise à jour…' : 'Mettre à jour' }}
            </button>
            <button v-if="pub.state === 'published'" class="fr-btn fr-btn--secondary" @click="unpublish"
                    title="Retire la collection de l'assistant. Les documents restent, et vous pourrez republier.">
              Désactiver
            </button>
            <button v-if="pub.state !== 'archived'" class="fr-btn fr-btn--tertiary" @click="archive"
                    title="Retire la collection de l'assistant ET du catalogue. Les documents sont conservés : un administrateur peut la désarchiver.">
              Archiver
            </button>
          </div>

          <div v-if="result" class="fr-alert fr-mt-2w"
               :class="owuiError ? 'fr-alert--warning' : 'fr-alert--success'">
            <p>{{ result }}</p>
            <p v-if="owuiError" class="fr-text--sm" style="margin-top:0.4rem;">
              <strong>OWUI :</strong> {{ owuiError }}
            </p>
          </div>
        </div>

        <!-- Right: History -->
        <div class="fr-col-4">
          <h3 class="fr-h5">Historique</h3>
          <div v-if="pub.history && pub.history.length > 0">
            <div v-for="(h, i) in pub.history.slice().reverse()" :key="i" class="fr-mb-1w">
              <p class="fr-text--sm">
                <strong>{{ h.action }}</strong> — {{ h.at }}<br>
                <span v-if="h.by">par {{ h.by }}</span>
              </p>
            </div>
          </div>
          <p v-else class="fr-text--sm">Aucun historique.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { libelleEtat } from '~/utils/collectif'
const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
const { get, post } = useApi()

const pub = ref<any>(null)
const etat = ref<any>(null)
const publishing = ref(false)
const result = ref('')
const owuiError = ref('')

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
  return { draft: 'Brouillon', published: 'Publie', disabled: 'Desactive', archived: 'Archive' }[s] || s
}

async function publish() {
  publishing.value = true
  result.value = ''
  try {
    owuiError.value = ''
    const data = await post(`/api/collections/${id}/publish`, form.value)
    pub.value = await get(`/api/collections/${id}/publication`)
    const m = data?.modes || data || {}
    const active = [m.alias_enabled && 'alias', m.tool_enabled && 'tool', m.embed_enabled && '#collection']
      .filter(Boolean).join(' + ')
    const base = active ? `Publie en mode ${active}` : 'Publie'
    if (data?.owui?.synced) {
      result.value = `${base} — modele '${data.owui.model_id}' synchronise avec OWUI.`
    } else if (data?.owui?.error) {
      result.value = base
      owuiError.value = data.owui.error
    } else {
      result.value = base
    }
  } catch (e: any) {
    result.value = `Erreur: ${e.message}`
  }
  publishing.value = false
}

async function unpublish() {
  await post(`/api/collections/${id}/unpublish`)
  pub.value = await get(`/api/collections/${id}/publication`)
}

async function archive() {
  await post(`/api/collections/${id}/archive`)
  pub.value = await get(`/api/collections/${id}/publication`)
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
      form.value.visibility_group = pub.value.visibility_group || `myrag/${id}`
    }
  } catch (e) {}
})
</script>
