<script setup lang="ts">
import { messageErreur } from '~/utils/collectif'
import { ongletDeLAdresse } from '~/utils/filAriane'
import { cibleAction } from '~/utils/qualite'

/** La page Qualité d'une collection (docs/qualite.md) : synthèse, courbe, à faire, quatre onglets. */
const route = useRoute()
const router = useRouter()
const id = route.params.id as string
const api = useQualite(id)
const { titre } = useTitreCollection(id)
const synthese = ref<any>(null)
const erreur = ref('')
const ouvert = ref<string | null>(null)
const filtre = ref<Record<string, string> | undefined>(undefined)
const signale = ref('')
const jeu = ref<any>(null)
const mesures = ref<any>(null)
const mesurer = ref<any>(null)
const BOUTONS: Record<string, string> = {
  constituer_jeu: 'Constituer le jeu',
  valider_questions: 'Relire',
  lancer_mesure: 'Mesurer',
  corriger_echecs: 'Voir',
  redecouper: 'Voir la réindexation',
  regle_de_garde: 'Voir les consignes',
  traiter_avis: 'Voir les avis',
}

const onglets = computed(() => {
  const q = synthese.value?.questions || {}
  const s = synthese.value?.satisfaction || {}
  return [
    { cle: 'jeu', libelle: `Jeu de questions (${q.total || 0})` },
    { cle: 'mesures', libelle: 'Mesures' },
    { cle: 'avis', libelle: `Avis des usagers (${s.total || 0})` },
    { cle: 'leviers', libelle: 'Leviers' },
  ]
})
const CLES = ['jeu', 'mesures', 'avis', 'leviers']
const tab = ref(ongletDeLAdresse(route.query.onglet, CLES, 'jeu'))
const vus = reactive<Record<string, boolean>>({ [tab.value]: true })
watch(tab, (t) => {
  vus[t] = true
  const query = { ...route.query }
  if (t === 'jeu') {
    delete query.onglet
  }
  else { query.onglet = t }
  router.replace({ query })
})

async function rechargerSynthese () {
  try {
    synthese.value = await api.synthese()
    erreur.value = ''
  }
  catch (e) {
    erreur.value = `La qualité de la collection n'a pas pu être lue : ${messageErreur(e)}`
  }
}
onMounted(() => {
  rechargerSynthese()
  // Un lien `…?onglet=leviers#levier-consignes` (volet de l'assistant) signale le levier visé.
  const m = /^#levier-(decoupage|consignes)$/.exec(route.hash || '')
  if (m) { signale.value = m[1] }
})

function mesureFinie () {
  rechargerSynthese()
  jeu.value?.charger()
  mesures.value?.charger()
}
function questionChange () {
  rechargerSynthese()
  jeu.value?.charger()
}
function avisChange () {
  rechargerSynthese()
  jeu.value?.charger()
}

function aller (code: string) {
  if (code === 'fiables') {
    filtre.value = { fiable: 'true' }
    tab.value = 'jeu'
    return
  }
  if (code === 'lancer_mesure') {
    mesurer.value?.lancer()
    return
  }
  const c = cibleAction(code, id)
  if (c.lien) { return router.push(c.lien) }
  if (c.filtre) { filtre.value = { ...c.filtre } }
  if (c.onglet) { tab.value = c.onglet }
  if (code === 'redecouper') { signale.value = 'decoupage' }
  if (code === 'regle_de_garde') { signale.value = 'consignes' }
}

function levier (nom: 'decoupage' | 'consignes') {
  signale.value = nom
  tab.value = 'leviers'
  nextTick(() => document.getElementById(`levier-${nom}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

function panneau (cle: string) {
  return {
    'id': `qpanneau-${cle}`,
    'class': ['fr-tabs__panel', { 'fr-tabs__panel--selected': tab.value === cle }],
    'role': 'tabpanel',
    'aria-labelledby': `qonglet-${cle}`,
    'tabindex': 0,
  }
}
function clavierOnglets (ev: KeyboardEvent) {
  const i = CLES.indexOf(tab.value)
  const vers = { ArrowRight: (i + 1) % CLES.length, ArrowLeft: (i - 1 + CLES.length) % CLES.length, Home: 0, End: CLES.length - 1 }[ev.key]
  if (vers === undefined) { return }
  ev.preventDefault()
  tab.value = CLES[vers]
  nextTick(() => document.getElementById(`qonglet-${CLES[vers]}`)?.focus())
}
</script>

<template>
  <div>
    <FilAriane
      :collection="id"
      :titre="titre"
      rubrique="Qualité"
    />

    <div class="qualite__entete fr-mb-3w">
      <div>
        <h1 class="fr-h2 fr-mb-1w">
          Qualité — {{ titre }}
        </h1>
        <p class="fr-text--sm fr-mb-0 qualite__discret">
          Le jeu de questions de référence, les mesures qui le posent à la collection, les avis des usagers et les
          leviers pour améliorer les réponses. <NuxtLink
            to="/guide"
            class="fr-link fr-text--sm"
          >
            Le guide
          </NuxtLink>
        </p>
      </div>
      <QualiteMesurer
        v-if="synthese"
        ref="mesurer"
        :collection="id"
        :synthese="synthese"
        @fini="mesureFinie"
      />
    </div>

    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-mb-3w"
      role="alert"
    >
      <p>{{ erreur }}</p>
    </div>
    <p
      v-if="!synthese && !erreur"
      class="fr-text--sm"
      aria-live="polite"
    >
      Chargement…
    </p>

    <template v-if="synthese">
      <div class="qualite__haut fr-mb-3w">
        <QualiteSynthese
          :synthese="synthese"
          class="qualite__bloc"
        />
        <QualiteCourbe
          :tendance="synthese.tendance || []"
          class="qualite__bloc"
        />
      </div>

      <section
        v-if="synthese.actions?.length"
        class="qualite__afaire fr-mb-4w"
        aria-labelledby="afaire-titre"
      >
        <h2
          id="afaire-titre"
          class="fr-h6 fr-mb-1w"
        >
          À faire
        </h2>
        <ul class="qualite__actions">
          <li
            v-for="a in synthese.actions"
            :key="a.code"
          >
            <span class="fr-text--sm">{{ a.libelle }}</span>
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary"
              @click="aller(a.code)"
            >
              {{ BOUTONS[a.code] || 'Voir' }}
            </button>
          </li>
        </ul>
      </section>

      <div class="fr-tabs">
        <ul
          class="fr-tabs__list"
          role="tablist"
          aria-label="Rubriques de la qualité"
          @keydown="clavierOnglets"
        >
          <li
            v-for="o in onglets"
            :key="o.cle"
            role="presentation"
          >
            <button
              :id="`qonglet-${o.cle}`"
              type="button"
              class="fr-tabs__tab"
              role="tab"
              :aria-selected="tab === o.cle"
              :aria-controls="`qpanneau-${o.cle}`"
              :tabindex="tab === o.cle ? 0 : -1"
              @click="tab = o.cle"
            >
              {{ o.libelle }}
            </button>
          </li>
        </ul>
        <div
          v-show="tab === 'jeu'"
          v-bind="panneau('jeu')"
        >
          <QualiteJeuDeQuestions
            ref="jeu"
            :collection="id"
            :filtre="filtre"
            @change="rechargerSynthese"
            @ouvrir="i => ouvert = i"
          />
        </div>
        <div
          v-show="tab === 'mesures'"
          v-bind="panneau('mesures')"
        >
          <QualiteMesures
            v-if="vus.mesures"
            ref="mesures"
            :collection="id"
            @ouvrir="i => ouvert = i"
            @change="rechargerSynthese"
          />
        </div>
        <div
          v-show="tab === 'avis'"
          v-bind="panneau('avis')"
        >
          <QualiteAvis
            v-if="vus.avis"
            :collection="id"
            @change="avisChange"
          />
        </div>
        <div
          v-show="tab === 'leviers'"
          v-bind="panneau('leviers')"
        >
          <QualiteLeviers
            v-if="vus.leviers"
            :collection="id"
            :synthese="synthese"
            :signale="signale"
            @voir-fiables="aller('fiables')"
            @change="rechargerSynthese"
          />
        </div>
      </div>
    </template>

    <QualiteVolet
      :collection="id"
      :ident="ouvert"
      @fermer="ouvert = null"
      @change="questionChange"
      @levier="levier"
    />
  </div>
</template>

<style scoped>
.qualite__entete { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 1rem; }
.qualite__entete > div:first-child { flex: 1 1 28rem; min-width: 0; }
.qualite__haut { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr)); gap: 1rem; }
.qualite__bloc { border: 1px solid var(--border-default-grey); padding: 1rem 1.25rem; min-width: 0; }
.qualite__afaire { border-left: 4px solid var(--border-plain-info); background: var(--background-alt-blue-france); padding: 1rem 1.25rem; }
.qualite__actions { list-style: none; padding: 0; margin: 0; display: grid; gap: .25rem; }
.qualite__actions li { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; }
.qualite__actions .fr-btn { margin: 0; }
.qualite__discret { color: var(--text-mention-grey); }
</style>
