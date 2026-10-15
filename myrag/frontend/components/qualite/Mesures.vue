<template>
  <div class="mesures">
    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w" role="alert"><p>{{ erreur }}</p></div>
    <p v-if="mesures === null" class="fr-text--sm" aria-live="polite">Chargement…</p>
    <div v-else-if="!mesures.length" class="fr-callout">
      <p class="fr-callout__text fr-text--sm">
        Aucune mesure pour l'instant. Une mesure pose chaque question validée à la collection et compare sa réponse
        à la réponse de référence ; elle s'enregistre ici, pour suivre la qualité dans le temps.
      </p>
    </div>
    <div v-else class="fr-table fr-table--no-caption fr-table--layout-fixed mesures__table">
      <div class="fr-table__wrapper">
        <div class="fr-table__container">
          <div class="fr-table__content">
            <table>
              <caption>Les mesures de la collection</caption>
              <thead>
                <tr><th scope="col">Date</th><th scope="col">Qualité</th><th scope="col">Détail</th><th scope="col">Comparaison</th><th scope="col">Actions</th></tr>
              </thead>
              <tbody>
                <tr v-for="m in mesures" :key="m.id" :aria-selected="choisie === m.id">
                  <td>{{ dateMesure(m.cree_le) }}</td>
                  <td>
                    <template v-if="m.etat === 'termine'">
                      <strong>{{ m.score }} %</strong>
                      <span class="fr-badge fr-badge--sm fr-badge--no-icon fr-ml-1v" :class="appreciation(m.score).classe">{{ appreciation(m.score).libelle }}</span>
                    </template>
                    <span v-else-if="m.actif" class="fr-badge fr-badge--sm fr-badge--info">En cours ({{ m.nb_traitees }}/{{ m.nb_questions }})</span>
                    <span v-else class="fr-badge fr-badge--sm fr-badge--error" :title="m.erreur || ''">En échec</span>
                  </td>
                  <td class="fr-text--sm">
                    {{ m.etat === 'termine' ? resumeVerdicts(m.verdicts) : (m.erreur || `${m.nb_questions} questions`) }}
                    <span v-if="m.duree_s" class="mesures__discret"> · {{ dureeLisible(m.duree_s) }}</span>
                  </td>
                  <td class="fr-text--sm">{{ m.methode === 'judge' ? 'Juge IA' : 'Similarité' }}</td>
                  <td>
                    <div class="mesures__actions">
                      <button v-if="m.etat === 'termine'" type="button" class="fr-btn fr-btn--sm fr-btn--secondary" @click="choisir(m.id)">
                        {{ choisie === m.id ? 'Détail affiché' : 'Voir le détail' }}
                      </button>
                      <button v-if="!m.actif && confirmer !== m.id" type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-delete-line"
                              :title="`Supprimer la mesure du ${dateMesure(m.cree_le)}`" @click="confirmer = m.id">Supprimer</button>
                      <button v-if="confirmer === m.id" type="button" class="fr-btn fr-btn--sm fr-btn--secondary" @click="supprimer(m.id)">Confirmer</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Le détail d'une mesure : question par question -->
    <section v-if="choisie" class="fr-mt-3w" aria-labelledby="mesure-detail-titre">
      <div class="mesures__entete">
        <h3 id="mesure-detail-titre" class="fr-h6 fr-mb-0">Question par question</h3>
        <div class="fr-select-group fr-mb-0">
          <label class="fr-label" for="mesure-filtre">Verdict</label>
          <select id="mesure-filtre" v-model="filtre" class="fr-select">
            <option value="">Tous</option>
            <option value="echecs">Non conformes et partielles</option>
            <option v-for="v in VERDICTS" :key="v" :value="v">{{ libelleVerdict(v) }}</option>
          </select>
        </div>
      </div>
      <p v-if="!resultats.length" class="fr-text--sm fr-mt-2w">Aucune question pour ce verdict.</p>
      <ul class="mesures__liste fr-mt-2w">
        <li v-for="x in resultats" :key="x.id" class="mesures__resultat">
          <p class="fr-mb-1v">
            <span class="fr-badge fr-badge--sm" :class="classeVerdict(x.verdict)">{{ libelleVerdict(x.verdict) }}</span>
            <strong class="fr-ml-1w">{{ x.question }}</strong>
          </p>
          <p v-if="x.justification" class="fr-text--sm fr-mb-1v">« {{ x.justification }} »</p>
          <details>
            <summary class="fr-text--sm mesures__resume">Comparer les réponses</summary>
            <div class="mesures__comparaison">
              <div>
                <p class="fr-text--xs fr-mb-1v mesures__discret">Référence</p>
                <p class="fr-text--sm mesures__texte">{{ x.hors_sujet ? 'Hors sujet : refuser.' : x.reponse_reference }}</p>
              </div>
              <div>
                <p class="fr-text--xs fr-mb-1v mesures__discret">Obtenue<template v-if="x.sources?.length"> · {{ x.sources.map((s: any) => s.fichier).join(', ') }}</template></p>
                <p class="fr-text--sm mesures__texte">{{ x.reponse_obtenue }}</p>
              </div>
            </div>
          </details>
          <button v-if="x.question_id" type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-eye-line fr-btn--icon-left"
                  @click="emit('ouvrir', x.question_id)">Ouvrir la question</button>
        </li>
      </ul>
      <button v-if="suite" type="button" class="fr-btn fr-btn--sm fr-btn--tertiary fr-mt-1w" @click="chargerResultats(true)">Afficher la suite</button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { dureeLisible } from '~/utils/generation'
import { appreciation, classeVerdict, dateMesure, libelleVerdict, resumeVerdicts, type Mesure } from '~/utils/qualite'
import { messageErreur } from '~/utils/collectif'

/** L'historique des mesures, et le détail de l'une d'elles question par question. */
const props = defineProps<{ collection: string }>()
const emit = defineEmits<{ ouvrir: [id: string], change: [] }>()
const api = useQualite(props.collection)
const VERDICTS = ['conforme', 'partiel', 'non_conforme', 'refus_ok', 'refus_ko', 'sans_source', 'erreur']
const mesures = ref<Mesure[] | null>(null)
const choisie = ref('')
const filtre = ref('echecs')
const resultats = ref<any[]>([])
const page = ref(1)
const suite = ref(false)
const confirmer = ref('')
const erreur = ref('')

async function charger() {
  try {
    mesures.value = (await api.mesures()).mesures
    if (!choisie.value) {
      const t = mesures.value!.find(m => m.etat === 'termine')
      if (t) choisir(t.id)
    }
  } catch (e) {
    erreur.value = `Les mesures n'ont pas pu être lues : ${messageErreur(e)}`
    mesures.value = []
  }
}

async function chargerResultats(plus = false) {
  if (!choisie.value) return
  page.value = plus ? page.value + 1 : 1
  try {
    const verdicts = filtre.value === 'echecs' ? ['non_conforme', 'partiel'] : [filtre.value]
    // Le serveur filtre sur un verdict : « échecs » en demande deux.
    const lots = await Promise.all(verdicts.map(v => api.resultats(choisie.value, { page: String(page.value), par_page: '25', ...(v ? { verdict: v } : {}) })))
    const items = lots.flatMap(l => l.resultats || [])
    resultats.value = plus ? [...resultats.value, ...items] : items
    suite.value = lots.some(l => (l.pages || 1) > page.value)
  } catch (e) {
    erreur.value = `Le détail de la mesure n'a pas pu être lu : ${messageErreur(e)}`
  }
}

function choisir(id: string) {
  choisie.value = id
  chargerResultats()
}
watch(filtre, () => chargerResultats())

async function supprimer(id: string) {
  confirmer.value = ''
  try {
    await api.supprimerMesure(id)
    if (choisie.value === id) {
      choisie.value = ''
      resultats.value = []
    }
    await charger()
    emit('change')
  } catch (e) {
    erreur.value = messageErreur(e)
  }
}

onMounted(charger)
defineExpose({ charger })
</script>

<style scoped>
.mesures__actions { display: flex; flex-wrap: wrap; gap: .25rem; }
.mesures__actions .fr-btn { margin: 0; }
.mesures__entete { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 1rem; }
.mesures__liste { list-style: none; padding: 0; margin: 0; display: grid; gap: .75rem; }
.mesures__resultat { border: 1px solid var(--border-default-grey); padding: .75rem 1rem; min-width: 0; }
.mesures__comparaison { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1rem; margin-top: .5rem; }
@media (max-width: 48em) { .mesures__comparaison { grid-template-columns: minmax(0, 1fr); } }
.mesures__texte { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--background-alt-grey); padding: .5rem; margin: 0; max-height: 16rem; overflow-y: auto; }
.mesures__resume { cursor: pointer; }
.mesures__discret { color: var(--text-mention-grey); }
</style>
