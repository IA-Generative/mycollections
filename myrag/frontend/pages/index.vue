<template>
  <div>
    <div class="fr-mb-4w">
      <h1>Mes collections</h1>
      <p class="fr-text--lead">
        En tant que gestionnaire, administrez et maintenez en qualite vos collections
        de donnees documentaires. Suivez l'usage et mettez-les a disposition de tout
        le ministere, de votre communaute ou de votre service.
      </p>
    </div>

    <!-- Action tiles -->
    <h2 class="fr-h3">Que souhaitez-vous faire ?</h2>
    <div class="fr-grid-row fr-grid-row--gutters fr-mb-6w">
      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <NuxtLink to="/admin/create" class="fr-tile__link">
                  {{ collections.length === 0 ? 'Creer ma premiere collection' : 'Creer une collection' }}
                </NuxtLink>
              </h3>
              <p class="fr-tile__desc">
                Assistant guide en 5 etapes : source, identification, donnees, evaluation, publication.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-add-circle-line fr-icon--lg" aria-hidden="true"></span>
            </div>
          </div>
        </div>
      </div>

      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <NuxtLink to="/admin/catalog" class="fr-tile__link">
                  Explorer le catalogue
                </NuxtLink>
              </h3>
              <p class="fr-tile__desc">
                Parcourez les collections existantes. Contactez les responsables pour y contribuer plutot que dupliquer.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-search-line fr-icon--lg" aria-hidden="true"></span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="isAdmin" class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <NuxtLink to="/admin" class="fr-tile__link">
                  Administration
                </NuxtLink>
              </h3>
              <p class="fr-tile__desc">
                Synchronisation Keycloak, jobs d'ingestion, templates de prompt, monitoring.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-settings-5-line fr-icon--lg" aria-hidden="true"></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Comment ça se passe : le collectif -->
    <section class="fr-callout fr-mb-6w">
      <h2 class="fr-callout__title">Comment ça se passe ?</h2>
      <p class="fr-callout__text" style="max-width:65ch">
        Un jeu de données vous manque ? Dites-le. Rassemblez {{ capacites.seuil_chantier }} collègues et un garant, amorcez depuis ce qui existe,
        vérifiez avant de publier, entretenez. Tant qu'une collection n'est pas publiée à tous, ses réponses portent la mention
        « en cours de vérification ».
      </p>
      <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-2w">
        <NuxtLink v-if="capacites.demandes" to="/demandes" class="fr-btn fr-btn--sm">Demandes de la communauté</NuxtLink>
        <NuxtLink to="/guide" class="fr-btn fr-btn--secondary fr-btn--sm">Le guide « Soyez acteurs vous-mêmes »</NuxtLink>
      </div>
    </section>

    <!-- Collections list -->
    <section>
      <h2 class="fr-h3">Mes collections ({{ collections.length }})</h2>

      <div v-if="loading" class="fr-callout"><p>Chargement...</p></div>

      <div v-else-if="collections.length === 0" class="fr-notice fr-notice--info">
        <div class="fr-container">
          <div class="fr-notice__body">
            <p class="fr-notice__title">Vous n'avez pas encore de collection.</p>
            <p class="fr-notice__desc">
              Commencez par choisir une source de donnees (Legifrance, fichier, Drive, etc.)
              et suivez l'assistant de creation.
            </p>
          </div>
        </div>
      </div>

      <div v-else class="fr-grid-row fr-grid-row--gutters">
        <div v-if="collections.length > 3" class="fr-col-12">
          <div class="fr-search-bar" role="search" style="max-width:32rem;">
            <label class="fr-label" for="recherche-accueil">Rechercher une collection</label>
            <input id="recherche-accueil" v-model="recherche" class="fr-input" type="search"
                   placeholder="Un thème, un sigle, un service…" />
            <button class="fr-btn" type="button">Rechercher</button>
          </div>
        </div>
        <p v-if="recherche && !groupes.length" class="fr-col-12 fr-text--sm">
          Aucune collection pour « {{ recherche }} ».
          <NuxtLink to="/admin/catalog" class="fr-link fr-text--sm">Voir le catalogue complet</NuxtLink>
        </p>
        <template v-for="groupe in groupes" :key="groupe.cle || '__aucune__'">
          <div class="fr-col-12 fr-mt-2w">
            <h3 class="fr-h5 fr-mb-0">
              {{ groupe.libelle }}
              <span class="fr-text--sm" style="font-weight:400;color:var(--text-mention-grey);">({{ groupe.collections.length }})</span>
            </h3>
            <p v-if="groupe.description" class="fr-text--sm fr-mb-0" style="color:var(--text-mention-grey);">{{ groupe.description }}</p>
          </div>
          <div v-for="col in groupe.collections" :key="col.name" class="fr-col-12 fr-col-md-6 fr-col-lg-4">
            <CarteCollection :col="col" />
          </div>
        </template>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { Categorie, Collection } from '~/types/collection'
import { filtrerCollections, grouperParCategorie } from '~/utils/catalogue'

const { get } = useApi()
const { isAdmin } = useAdminAuth()
const { capacites } = useCapacites()
const { lister: listerCategories } = useCategories()
const collections = ref<Collection[]>([])
const categories = ref<Categorie[]>([])
const recherche = ref('')
const loading = ref(true)

const groupes = computed(() => grouperParCategorie(filtrerCollections(collections.value, recherche.value), categories.value))

onMounted(async () => {
  try {
    const data = await get('/api/collections')
    collections.value = data.collections || []
  } catch (e) {}
  loading.value = false
  // Sans les rubriques, le catalogue reste lisible : tout tombe dans « Non classées ».
  try { categories.value = await listerCategories() } catch (e) {}
})
</script>
