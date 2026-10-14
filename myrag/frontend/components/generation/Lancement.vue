<template>
  <section>
    <h3 class="fr-h6 fr-mb-1w">Lancer une génération</h3>
    <fieldset class="fr-fieldset" :disabled="!!actif || occupe">
      <legend class="fr-fieldset__legend fr-text--regular">Personas à faire parler (cinq au plus)</legend>
      <div v-for="p in personas" :key="p.id" class="fr-fieldset__element">
        <div class="fr-checkbox-group fr-checkbox-group--sm">
          <input :id="`gen-p-${p.id}`" v-model="choisis" type="checkbox" :value="p.id"
                 :disabled="!choisis.includes(p.id) && choisis.length >= 5">
          <label class="fr-label" :for="`gen-p-${p.id}`">{{ p.nom }}</label>
        </div>
      </div>
      <p v-if="!personas.length" class="fr-text--sm fr-ml-2w">Ajoutez d'abord un persona.</p>
    </fieldset>

    <div class="gen-lancement__reglages">
      <div class="fr-input-group">
        <label class="fr-label" for="gen-taille">Nombre de paires
          <span class="fr-hint-text">De 1 à 100. Comptez quelques minutes pour 30 paires.</span></label>
        <input id="gen-taille" v-model.number="taille" class="fr-input" type="number" min="1" max="100" :disabled="!!actif || occupe">
      </div>
      <div class="fr-checkbox-group fr-checkbox-group--sm">
        <input id="gen-mots-cles" v-model="avecMotsCles" type="checkbox" :disabled="!!actif || occupe">
        <label class="fr-label" for="gen-mots-cles">Varier les sujets (entités et mots-clés)
          <span class="fr-hint-text">Deux repérages par passage au lieu d'un : plus de variété, coût doublé pour cette étape.</span></label>
      </div>
    </div>
    <button class="fr-btn fr-icon-play-line fr-btn--icon-left fr-mt-2w" :disabled="!peutLancer" @click="lancer">
      Générer {{ taille }} paire{{ taille > 1 ? 's' : '' }}
    </button>
    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w" role="alert"><p>{{ erreur }}</p></div>

    <!-- Le run en cours, ou le dernier -->
    <div v-if="actif" class="fr-callout fr-mt-3w" aria-live="polite">
      <p class="fr-callout__title fr-h6">{{ libellePhase(actif.phase) }}…</p>
      <div class="gen-barre" role="progressbar" :aria-valuenow="progressionRun(actif)" aria-valuemin="0" aria-valuemax="100"
           :aria-label="`Avancement de la génération : ${progressionRun(actif)} %`">
        <div class="gen-barre__plein" :style="{ width: `${progressionRun(actif)}%` }" />
      </div>
      <p class="fr-text--sm fr-mt-1w fr-mb-0">
        {{ actif.morceaux_envoyes ? `${actif.morceaux_envoyes} passages lus · ` : '' }}{{ resumeCout(actif) }}
      </p>
    </div>

    <h3 class="fr-h6 fr-mt-4w fr-mb-1w">Générations</h3>
    <p v-if="!runs.length" class="fr-text--sm" style="color:var(--text-mention-grey)">Aucune génération pour l'instant.</p>
    <div v-else class="fr-table fr-table--sm fr-table--no-caption">
      <table>
        <caption>Les générations de cette collection</caption>
        <thead><tr><th>Date</th><th>Personas</th><th>Paires</th><th>État</th><th>Coût</th><th><span class="fr-sr-only">Actions</span></th></tr></thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id" :class="{ 'gen-run--choisi': r.id === choisi }">
            <td>{{ new Date(r.cree_le + 'Z').toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) }}</td>
            <td>{{ r.personas.map(p => p.nom).join(', ') }}</td>
            <td>{{ r.paires_obtenues }} / {{ r.taille }}<span v-if="r.paires_echouees"> ({{ r.paires_echouees }} en échec)</span></td>
            <td>
              <span class="fr-badge fr-badge--sm" :class="classeEtatRun(r.etat)">{{ libelleEtatRun(r.etat) }}</span>
              <p v-if="r.erreur" class="fr-text--xs fr-mb-0 fr-mt-1v">{{ r.erreur }}</p>
            </td>
            <td class="fr-text--xs">{{ r.actif ? '…' : resumeCout(r) }}</td>
            <td>
              <div class="gen-actions">
                <button v-if="r.etat === 'termine'" class="fr-btn fr-btn--sm fr-btn--secondary" :aria-pressed="r.id === choisi"
                        @click="emit('choisir', r.id)">Voir les paires</button>
                <button v-if="!r.actif" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline fr-icon-delete-line fr-btn--icon-only"
                        :title="`Supprimer la génération du ${new Date(r.cree_le + 'Z').toLocaleDateString('fr-FR')} et ses paires`"
                        @click="supprimer(r)">Supprimer</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { classeEtatRun, libelleEtatRun, libellePhase, progressionRun, resumeCout, type Run } from '~/utils/generation'
import { messageErreur } from '~/utils/collectif'

const props = defineProps<{ collection: string, personas: any[], runs: Run[], choisi: string | null }>()
const emit = defineEmits<{ change: [], choisir: [id: string] }>()
const g = useGeneration()
const choisis = ref<string[]>([])
const taille = ref(20)
const avecMotsCles = ref(false)
const occupe = ref(false)
const erreur = ref('')
const actif = computed(() => props.runs.find(r => r.actif) || null)
const peutLancer = computed(() => !actif.value && !occupe.value && choisis.value.length > 0
  && Number.isInteger(taille.value) && taille.value >= 1 && taille.value <= 100)

watch(() => props.personas, (ps) => {
  choisis.value = choisis.value.filter(id => ps.some(p => p.id === id))
  if (!choisis.value.length) choisis.value = ps.slice(0, 2).map(p => p.id)
}, { immediate: true })

async function lancer() {
  occupe.value = true
  erreur.value = ''
  try {
    await g.lancer(props.collection, {
      personas: choisis.value, taille: taille.value,
      distribution: avecMotsCles.value ? { entites: 1, mots_cles: 1 } : { entites: 1 },
    })
    emit('change')
  } catch (e) { erreur.value = messageErreur(e) } finally { occupe.value = false }
}

async function supprimer(r: Run) {
  if (!confirm('Supprimer cette génération et toutes ses paires, relues ou non ?')) return
  try { await g.supprimerRun(props.collection, r.id); emit('change') } catch (e) { erreur.value = messageErreur(e) }
}
</script>

<style scoped>
.gen-lancement__reglages { display: flex; flex-wrap: wrap; gap: 1rem 2rem; align-items: flex-end; }
.gen-lancement__reglages .fr-input-group { max-width: 14rem; margin-bottom: 0; }
.gen-barre { height: .5rem; background: var(--background-contrast-grey); border-radius: .25rem; overflow: hidden; }
.gen-barre__plein { height: 100%; background: var(--background-action-high-blue-france); transition: width .5s; }
.gen-run--choisi td { background: var(--background-alt-blue-france); }
.gen-actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
</style>
