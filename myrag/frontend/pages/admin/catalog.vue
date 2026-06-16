<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Catalogue des collections</a></li>
      </ol>
    </nav>

    <h1 class="fr-h3">Catalogue des collections existantes</h1>
    <p class="fr-text--lg fr-mb-2w">Avant de creer une collection, verifiez qu'elle n'existe pas deja.</p>

    <div class="fr-callout fr-callout--brown-caramel fr-mb-4w">
      <p class="fr-callout__text">
        <strong>Evitez les doublons.</strong> Dupliquer une collection degrade la qualite du RAG
        (reponses inconsistantes, cout d'indexation double, maintenance multiple).
        Preferez contacter le responsable d'une collection existante pour y contribuer.
      </p>
    </div>

    <!-- Search + toggle -->
    <div class="fr-grid-row fr-grid-row--gutters fr-mb-4w">
      <div class="fr-col-12 fr-col-md-8">
        <div class="fr-search-bar" role="search">
          <label class="fr-label" for="search">Rechercher une collection</label>
          <input class="fr-input" id="search" type="search" v-model="search"
                 placeholder="CESEDA, code civil, documentation technique..." />
          <button class="fr-btn" @click="">Rechercher</button>
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-4" style="display:flex;align-items:flex-end;">
        <div class="fr-toggle">
          <input type="checkbox" class="fr-toggle__input" id="show-archived" v-model="showArchived" @change="loadCollections" />
          <label class="fr-toggle__label" for="show-archived">Afficher les archivees</label>
        </div>
      </div>
    </div>

    <!-- Results -->
    <div v-if="filtered.length === 0 && search" class="fr-callout fr-mb-4w">
      <h3 class="fr-callout__title">Aucune collection trouvee pour "{{ search }}"</h3>
      <p class="fr-callout__text">Vous pouvez creer une nouvelle collection.</p>
      <NuxtLink to="/admin/create" class="fr-btn fr-mt-2w">Creer une collection</NuxtLink>
    </div>

    <div v-else>
      <div class="fr-table">
        <table>
          <thead>
            <tr>
              <th>Collection</th>
              <th>Description</th>
              <th>Source</th>
              <th>Etat</th>
              <th>Responsable</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="col in filtered" :key="col.name" :style="col.archived_at ? 'opacity:0.65;' : ''">
              <td>
                <NuxtLink :to="`/c/${col.name}`" class="fr-link">{{ col.name }}</NuxtLink>
              </td>
              <td>{{ col.description || '—' }}</td>
              <td>
                <span class="fr-badge fr-badge--sm">{{ col.source?.type || col.strategy }}</span>
              </td>
              <td>
                <span v-if="col.archived_at" class="fr-badge fr-badge--sm fr-badge--warning">Archivee</span>
                <span v-else class="fr-badge fr-badge--sm" :class="stateBadge(col.publication?.state)">
                  {{ stateLabel(col.publication?.state) }}
                </span>
              </td>
              <td>
                <div v-if="col.contact_name">
                  {{ col.contact_name }}
                  <br v-if="col.contact_email" />
                  <a v-if="col.contact_email" :href="`mailto:${col.contact_email}?subject=Collection MyRAG : ${col.name}`"
                     class="fr-link fr-text--sm">
                    {{ col.contact_email }}
                  </a>
                </div>
                <span v-else class="fr-text--sm" style="color:#666;">Non renseigne</span>
              </td>
              <td>
                <div class="fr-btns-group fr-btns-group--sm fr-btns-group--inline fr-btns-group--inline-sm">
                  <button v-if="!col.archived_at"
                          class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-inbox-archive-line fr-btn--icon-left"
                          @click="onArchive(col)">
                    Archiver
                  </button>
                  <button v-else
                          class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-refresh-line fr-btn--icon-left"
                          @click="onUnarchive(col)">
                    Desarchiver
                  </button>
                  <button v-if="col.archived_at"
                          class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-delete-line fr-btn--icon-left"
                          style="color:#ce0500;"
                          @click="askPurge(col)">
                    Purger
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="fr-text--sm fr-mt-2w">{{ filtered.length }} collection(s) trouvee(s)</p>
    </div>

    <div class="fr-btns-group fr-mt-4w">
      <NuxtLink to="/admin/create" class="fr-btn">
        Creer une nouvelle collection
      </NuxtLink>
    </div>

    <!-- Purge confirmation modal -->
    <dialog v-if="purgeTarget" open class="fr-modal fr-modal--opened"
            aria-labelledby="purge-title" style="display:block;">
      <div class="fr-container fr-container--fluid fr-container-md">
        <div class="fr-grid-row fr-grid-row--center">
          <div class="fr-col-12 fr-col-md-8 fr-col-lg-6">
            <div class="fr-modal__body">
              <div class="fr-modal__header">
                <button class="fr-btn--close fr-btn" @click="purgeTarget = null">Fermer</button>
              </div>
              <div class="fr-modal__content">
                <h1 id="purge-title" class="fr-modal__title">
                  <span class="fr-icon-warning-fill" aria-hidden="true"></span>
                  Purger definitivement {{ purgeTarget.name }} ?
                </h1>
                <p>Cette action est <strong>irreversible</strong>. Elle supprime :</p>
                <ul>
                  <li>La partition OpenRAG (tous les documents indexes)</li>
                  <li>Les fichiers sources stockes sur disque</li>
                  <li>Toutes les donnees liees (publications, jobs, feedback, evaluations)</li>
                </ul>
                <div class="fr-input-group" :class="purgeError ? 'fr-input-group--error' : ''">
                  <label class="fr-label" for="purge-confirm">
                    Pour confirmer, tapez le nom de la collection : <strong>{{ purgeTarget.name }}</strong>
                  </label>
                  <input class="fr-input" id="purge-confirm" type="text" v-model="purgeConfirm"
                         @keyup.enter="confirmPurge" />
                  <p v-if="purgeError" class="fr-error-text">{{ purgeError }}</p>
                </div>
              </div>
              <div class="fr-modal__footer">
                <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-reverse fr-btns-group--inline-lg">
                  <li>
                    <button class="fr-btn" style="background:#ce0500;color:#fff;" @click="confirmPurge"
                            :disabled="purging">
                      {{ purging ? 'Purge en cours...' : 'Purger definitivement' }}
                    </button>
                  </li>
                  <li>
                    <button class="fr-btn fr-btn--secondary" @click="purgeTarget = null">Annuler</button>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </dialog>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ middleware: 'admin-only' })
const { get, post, del } = useApi()

const collections = ref<any[]>([])
const search = ref('')
const showArchived = ref(false)

const purgeTarget = ref<any | null>(null)
const purgeConfirm = ref('')
const purgeError = ref('')
const purging = ref(false)

const filtered = computed(() => {
  if (!search.value.trim()) return collections.value
  const q = search.value.toLowerCase()
  return collections.value.filter(c =>
    c.name?.toLowerCase().includes(q) ||
    c.description?.toLowerCase().includes(q) ||
    c.contact_name?.toLowerCase().includes(q) ||
    c.source?.type?.toLowerCase().includes(q) ||
    c.legifrance_source_id?.toLowerCase().includes(q)
  )
})

function stateBadge(state: string) {
  return {
    draft: 'fr-badge--info', published: 'fr-badge--success',
    disabled: 'fr-badge--warning', archived: '',
  }[state] || ''
}

function stateLabel(state: string) {
  return { draft: 'Brouillon', published: 'Publie', disabled: 'Desactive', archived: 'Archive' }[state] || 'Brouillon'
}

async function loadCollections() {
  try {
    const data = await get('/api/collections', showArchived.value ? { include_archived: 'true' } : undefined)
    collections.value = data.collections || []
  } catch (e) { console.error(e) }
}

async function onArchive(col: any) {
  if (!confirm(`Archiver la collection "${col.name}" ? Elle sera depubliee et masquee du catalogue. Reversible.`)) return
  try {
    await post(`/api/collections/${col.name}/archive`)
    await loadCollections()
  } catch (e: any) { alert(`Erreur: ${e.message}`) }
}

async function onUnarchive(col: any) {
  try {
    await post(`/api/collections/${col.name}/unarchive`)
    await loadCollections()
  } catch (e: any) { alert(`Erreur: ${e.message}`) }
}

function askPurge(col: any) {
  purgeTarget.value = col
  purgeConfirm.value = ''
  purgeError.value = ''
}

async function confirmPurge() {
  if (!purgeTarget.value) return
  if (purgeConfirm.value !== purgeTarget.value.name) {
    purgeError.value = 'Le nom saisi ne correspond pas.'
    return
  }
  purging.value = true
  purgeError.value = ''
  try {
    await del(`/api/collections/${purgeTarget.value.name}`)
    purgeTarget.value = null
    await loadCollections()
  } catch (e: any) {
    purgeError.value = e.message
  } finally {
    purging.value = false
  }
}

onMounted(loadCollections)
</script>
