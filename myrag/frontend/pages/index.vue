<template>
  <div class="accueil">
    <div class="fr-mb-4w">
      <h1>Mes collections</h1>
      <p class="fr-text--lead">
        Interrogez les données de votre ministère en langage courant — ou constituez les vôtres.
      </p>
    </div>

    <!-- À celui qui partage déjà : ce que son travail a rendu possible. Absent pour qui ne gère rien. -->
    <section v-if="merci" class="accueil-merci fr-mb-5w" aria-label="Ce que vos collections ont rendu possible">
      <div class="accueil-merci__chiffres">
        <div><b>{{ nombre(bilan!.actives) }}</b><span>collection{{ bilan!.actives > 1 ? 's' : '' }} active{{ bilan!.actives > 1 ? 's' : '' }}</span></div>
        <div><b>{{ nombre(bilan!.questions) }}</b><span>question{{ bilan!.questions > 1 ? 's' : '' }} en {{ bilan!.fenetre_jours }} jours</span></div>
        <div v-if="bilan!.personnes"><b>{{ nombre(bilan!.personnes) }}</b><span>collègues aidés</span></div>
      </div>
      <div class="accueil-merci__mots">
        <strong>{{ merci.titre }}</strong>
        <p class="fr-text--sm fr-mb-0">
          {{ merci.texte }}
          <template v-if="bilan!.signalements_ouverts">
            <NuxtLink to="/mes-collections" class="fr-link fr-text--sm">{{ bilan!.signalements_ouverts }} signalement{{ bilan!.signalements_ouverts > 1 ? 's vous attendent' : ' vous attend' }}</NuxtLink> :
            y répondre, c'est aider les suivants.
          </template>
        </p>
      </div>
      <button v-if="merci.action.libelle.startsWith('Copier')" type="button" class="fr-btn fr-btn--secondary fr-btn--sm" @click="copierLien(merci.action.vers)">
        {{ lienCopie ? 'Lien copié' : merci.action.libelle }}
      </button>
      <NuxtLink v-else :to="merci.action.vers" class="fr-btn fr-btn--secondary fr-btn--sm">{{ merci.action.libelle }}</NuxtLink>
    </section>

    <h2 class="fr-h3">Que souhaitez-vous faire ?</h2>
    <div class="fr-grid-row fr-grid-row--gutters fr-mb-5w">
      <!-- 1. Découvrir : ce qui existe, un exemple, un seul geste. -->
      <div class="fr-col-12 fr-col-lg-4">
        <div class="accueil-decouvrir">
          <div class="accueil-decouvrir__tete">
            <h3 class="fr-h6 fr-mb-0">Découvrir</h3>
            <span class="fr-badge fr-badge--sm fr-badge--success fr-badge--no-icon">Prêt à l'emploi</span>
          </div>
          <div class="accueil-decouvrir__chiffres" aria-label="Ce qui existe déjà">
            <div><b>{{ loading ? '…' : nombre(chiffres.collections) }}</b><span>collection{{ chiffres.collections > 1 ? 's' : '' }} à interroger</span></div>
            <div><b>{{ loading ? '…' : nombre(chiffres.categories) }}</b><span>catégorie{{ chiffres.categories > 1 ? 's' : '' }}</span></div>
            <!-- Le compte vient d'OpenRAG : s'il ne répond pas, on ne montre pas un « 0 » qui mentirait. -->
            <div v-if="loading || chiffres.documents"><b>{{ loading ? '…' : nombre(chiffres.documents) }}</b><span>documents indexés</span></div>
          </div>
          <div v-if="exemple" class="accueil-decouvrir__exemple" aria-live="polite">
            <span v-if="exemple.categorie_libelle" class="accueil-decouvrir__rubrique">{{ exemple.categorie_libelle }}</span>
            <h4 class="fr-text--md fr-mb-0" style="font-weight:700;">{{ exemple.titre }}</h4>
            <p class="accueil-decouvrir__question fr-mb-0">« {{ exemple.question }} »</p>
          </div>
          <p v-else-if="!loading" class="fr-text--sm fr-mb-0">
            Parcourez le catalogue : chaque collection s'interroge en langage courant.
          </p>
          <div class="accueil-decouvrir__actions">
            <NuxtLink v-if="exemple" :to="{ path: `/c/${exemple.name}/playground`, query: { q: exemple.question } }" class="fr-btn fr-btn--sm">
              Poser cette question
            </NuxtLink>
            <NuxtLink v-else to="/admin/catalog" class="fr-btn fr-btn--sm">Voir le catalogue</NuxtLink>
            <button v-if="exemple?.autres" type="button" class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-btn--icon-right fr-icon-refresh-line"
                    :disabled="tirage" @click="autreIdee">
              Une autre idée
            </button>
          </div>
        </div>
      </div>

      <!-- 2. Explorer -->
      <div class="fr-col-12 fr-col-md-6 fr-col-lg-4">
        <div class="fr-tile fr-enlarge-link" style="height:100%;">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title"><NuxtLink to="/admin/catalog" class="fr-tile__link">Explorer le catalogue</NuxtLink></h3>
              <p class="fr-tile__desc">Toutes les collections, rangées par catégorie. Contactez leurs responsables pour y contribuer plutôt que dupliquer.</p>
            </div>
          </div>
          <div class="fr-tile__header"><div class="fr-tile__pictogram"><span class="fr-icon-search-line fr-icon--lg" aria-hidden="true"></span></div></div>
        </div>
      </div>

      <!-- 3. Créer -->
      <div class="fr-col-12 fr-col-md-6 fr-col-lg-4">
        <div class="fr-tile fr-enlarge-link" style="height:100%;">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title"><NuxtLink to="/admin/create" class="fr-tile__link">Créer une collection</NuxtLink></h3>
              <p class="fr-tile__desc">Assistant guidé en 5 étapes : source, identification, données, évaluation, publication.</p>
            </div>
          </div>
          <div class="fr-tile__header"><div class="fr-tile__pictogram"><span class="fr-icon-add-circle-line fr-icon--lg" aria-hidden="true"></span></div></div>
        </div>
      </div>
    </div>

    <!-- Il vous manque une donnée ? Le mode d'emploi du collectif, en quatre temps. -->
    <section class="accueil-demande fr-mb-5w">
      <h2 class="fr-h4 fr-mb-1w">Il vous manque une donnée pour travailler ?</h2>
      <p class="fr-mb-3w" style="max-width:68ch">
        Dites-le : vous n'avez rien à construire vous-même. Une demande qui rassemble assez de collègues devient un chantier,
        et la collection qui en sort profite à tout le ministère.
      </p>
      <ol class="accueil-demande__etapes">
        <li><b>Dites ce qui manque</b><span>Le jeu de données, et comment vous vous le procurez aujourd'hui. Deux minutes.</span></li>
        <li><b>Rassemblez {{ capacites.seuil_chantier }} collègues et un garant</b><span>Chacun soutient d'un clic. Le garant répond de la qualité.</span></li>
        <li><b>On amorce depuis ce qui existe</b><span>Open data, Légifrance, fichiers du service : la collection démarre.</span></li>
        <li><b>Vérifiée, puis publiée à tous</b><span>D'ici là, ses réponses portent la mention « en cours de vérification ».</span></li>
      </ol>
      <div v-if="capacites.demandes && enVue" class="accueil-demande__en-cours fr-mt-3w">
        <span><b>En ce moment :</b> « {{ enVue.titre }} » — {{ enVue.nb_soutiens }} soutien{{ enVue.nb_soutiens > 1 ? 's' : '' }} sur {{ enVue.seuil }}</span>
        <span class="accueil-jauge" aria-hidden="true"><i v-for="n in enVue.seuil" :key="n" :class="{ ok: n <= enVue.nb_soutiens }"></i></span>
        <NuxtLink :to="`/demandes/${enVue.id}`" class="fr-link fr-text--sm">{{ enVue.soutenue_par_moi ? 'Voir la demande' : 'Soutenir cette demande' }}</NuxtLink>
      </div>
      <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-3w">
        <!-- Le formulaire de dépôt ouvre la page des demandes, au-dessus de celles de la communauté. -->
        <NuxtLink v-if="capacites.demandes" to="/demandes" class="fr-btn fr-btn--sm">Demander un jeu de données</NuxtLink>
        <NuxtLink to="/guide" class="fr-btn fr-btn--tertiary fr-btn--sm">Le guide « Soyez acteurs vous-mêmes »</NuxtLink>
      </div>
    </section>

    <!-- Les portes d'entrée du catalogue. La grande liste de cartes vit au catalogue (toutes)
         et dans le menu « Mes collections » (celles que je gère). -->
    <section v-if="entrees.length">
      <h2 class="fr-h4">Parcourir par catégorie</h2>
      <div class="accueil-portes">
        <NuxtLink v-for="p in entrees" :key="p.cle" :to="{ path: '/admin/catalog', query: { categorie: p.cle } }">
          {{ p.libelle }} <span>{{ p.nb }} collection{{ p.nb > 1 ? 's' : '' }}</span>
        </NuxtLink>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { Categorie, Collection } from '~/types/collection'
import { type BilanPartage, type DemandeResumee, demandeEnVue, indicateurs, messageMerci, nombre, portes } from '~/utils/accueil'

const { get } = useApi()
const { capacites } = useCapacites()
const { lister: listerCategories } = useCategories()

const collections = ref<Collection[]>([])
const categories = ref<Categorie[]>([])
const bilan = ref<BilanPartage | null>(null)
const demandes = ref<DemandeResumee[]>([])
const exemple = ref<{ name: string; titre: string; categorie_libelle?: string; question: string; autres?: boolean } | null>(null)
const loading = ref(true)
const tirage = ref(false)
const lienCopie = ref(false)

const chiffres = computed(() => indicateurs(collections.value, categories.value))
const entrees = computed(() => portes(collections.value, categories.value))
const merci = computed(() => messageMerci(bilan.value))
const enVue = computed(() => demandeEnVue(demandes.value))

async function autreIdee() {
  tirage.value = true
  try {
    const r = await get('/api/accueil/exemple', exemple.value ? { sauf: exemple.value.name } : undefined)
    if (r.exemple) exemple.value = r.exemple
  } catch (e) {}
  tirage.value = false
}

async function copierLien(chemin: string) {
  try {
    await navigator.clipboard.writeText(`${window.location.origin}${chemin}`)
    lienCopie.value = true
    setTimeout(() => { lienCopie.value = false }, 2500)
  } catch (e) {
    navigateTo(chemin)
  }
}

// Chaque bloc tombe seul : une panne d'un appel ne vide jamais la page.
onMounted(() => {
  autreIdee()
  get('/api/accueil/mes-collections').then((r) => { bilan.value = r }).catch(() => {})
  listerCategories().then((r) => { categories.value = r }).catch(() => {})
  get('/api/demandes').then((r) => { demandes.value = r.demandes || [] }).catch(() => {})
  get('/api/collections')
    .then((r) => { collections.value = r.collections || [] })
    .catch(() => {})
    .finally(() => { loading.value = false })
})
</script>

<style scoped>
.accueil-merci {
  display: grid; grid-template-columns: auto 1fr auto; gap: .5rem 1.5rem; align-items: center;
  border: 1px solid var(--border-default-grey); border-left: 4px solid var(--border-plain-success); padding: 1rem 1.25rem;
}
.accueil-merci__chiffres { display: flex; gap: 1.4rem; }
.accueil-merci__chiffres div { display: flex; flex-direction: column; }
.accueil-merci__chiffres b { font-size: 1.6rem; line-height: 1.1; color: var(--text-default-success); font-variant-numeric: tabular-nums; }
.accueil-merci__chiffres span { font-size: .75rem; color: var(--text-mention-grey); }
.accueil-merci__mots { display: flex; flex-direction: column; gap: .25rem; }
.accueil-merci__mots p { max-width: 62ch; }

.accueil-decouvrir {
  height: 100%; display: flex; flex-direction: column; gap: .85rem; padding: 1.35rem 1.35rem 1.25rem;
  background: var(--background-alt-blue-france); border: 1px solid var(--border-default-blue-france);
  border-bottom: 4px solid var(--border-active-blue-france);
}
.accueil-decouvrir__tete { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
.accueil-decouvrir__tete h3 { color: var(--text-title-blue-france); }
.accueil-decouvrir__chiffres {
  display: flex; gap: .5rem 1.25rem; flex-wrap: wrap; padding-block: .6rem;
  border-block: 1px solid var(--border-default-blue-france);
}
.accueil-decouvrir__chiffres div { display: flex; flex-direction: column; }
.accueil-decouvrir__chiffres b { font-size: 1.45rem; line-height: 1.1; color: var(--text-title-blue-france); font-variant-numeric: tabular-nums; }
.accueil-decouvrir__chiffres span { font-size: .75rem; line-height: 1.25; color: var(--text-mention-grey); }
.accueil-decouvrir__exemple { display: flex; flex-direction: column; gap: .35rem; }
.accueil-decouvrir__rubrique { font-size: .72rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--text-mention-grey); }
.accueil-decouvrir__question { font-size: .92rem; font-style: italic; border-left: 3px solid var(--border-default-blue-france); padding-left: .6rem; }
.accueil-decouvrir__actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-top: auto; }

.accueil-demande { background: var(--background-contrast-grey); border-left: 4px solid var(--border-default-blue-france); padding: 1.5rem; }
.accueil-demande__etapes { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; counter-reset: etape; }
.accueil-demande__etapes li { counter-increment: etape; display: flex; flex-direction: column; gap: .25rem; font-size: .9rem; border-top: 2px solid var(--border-active-blue-france); padding-top: .6rem; }
.accueil-demande__etapes li::before { content: counter(etape); font-weight: 700; font-size: 1.1rem; color: var(--text-title-blue-france); }
.accueil-demande__etapes span { color: var(--text-mention-grey); }
.accueil-demande__en-cours { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .9rem; font-size: .9rem; background: var(--background-default-grey); border: 1px solid var(--border-default-grey); padding: .6rem .9rem; }
.accueil-jauge { display: inline-flex; gap: 3px; }
.accueil-jauge i { width: 14px; height: 8px; display: block; background: var(--border-default-grey); }
.accueil-jauge i.ok { background: var(--border-active-blue-france); }

.accueil-portes { display: grid; grid-template-columns: repeat(3, 1fr); gap: .75rem; }
.accueil-portes a {
  display: flex; justify-content: space-between; align-items: baseline; gap: .75rem; padding: .75rem 1rem;
  border: 1px solid var(--border-default-grey); background-image: none; color: var(--text-default-grey);
}
.accueil-portes a:hover { background: var(--background-alt-grey); border-color: var(--border-default-blue-france); }
.accueil-portes a span { color: var(--text-mention-grey); font-size: .8rem; white-space: nowrap; font-variant-numeric: tabular-nums; }

@media (max-width: 62em) {
  .accueil-merci { grid-template-columns: 1fr; }
  .accueil-demande__etapes, .accueil-portes { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 36em) {
  .accueil-demande__etapes, .accueil-portes { grid-template-columns: 1fr; }
}
</style>
