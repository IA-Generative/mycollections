<template>
  <section>
    <div class="gen-paires__tete">
      <h3 class="fr-h6 fr-mb-0">Paires générées</h3>
      <div class="gen-actions">
        <button class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-download-line fr-btn--icon-left" @click="exporter('csv')">Exporter en CSV</button>
        <button class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-download-line fr-btn--icon-left" @click="exporter('json')">Exporter en JSON</button>
      </div>
    </div>
    <p class="fr-text--sm fr-mb-2w">
      Relisez chaque paire : validez celles qui serviront de référence pour évaluer les réponses de l'assistant,
      rejetez les autres. Les questions imitent volontairement des façons d'écrire variées (fautes, mots-clés).
    </p>

    <div class="gen-paires__filtres">
      <div class="fr-select-group">
        <label class="fr-label" for="gen-f-persona">Persona</label>
        <select id="gen-f-persona" v-model="persona" class="fr-select">
          <option value="">Tous</option>
          <option v-for="p in personasDuRun" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>
      <div class="fr-select-group">
        <label class="fr-label" for="gen-f-relecture">Relecture</label>
        <select id="gen-f-relecture" v-model="relecture" class="fr-select">
          <option value="">Toutes</option>
          <option value="brut">À relire</option><option value="valide">Validées</option><option value="rejete">Rejetées</option>
        </select>
      </div>
      <p class="fr-text--sm fr-mb-0" aria-live="polite"><strong>{{ page?.total ?? 0 }}</strong> paire{{ (page?.total ?? 0) > 1 ? 's' : '' }}</p>
    </div>

    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w" role="alert"><p>{{ erreur }}</p></div>

    <div class="fr-table fr-table--no-caption">
      <table>
        <caption>Paires question / réponse de la génération</caption>
        <thead><tr><th>Question</th><th>Réponse de référence</th><th>Persona</th><th>Passages</th><th>Relecture</th></tr></thead>
        <tbody>
          <tr v-for="p in page?.paires || []" :key="p.id">
            <td class="gen-paires__q">
              {{ p.question }}
              <p class="fr-text--xs fr-mb-0 fr-mt-1v" style="color:var(--text-mention-grey)">
                question {{ libelleLongueur(p.longueur) }}, {{ libelleStyle(p.style) }}</p>
            </td>
            <td class="gen-paires__r">{{ p.reponse }}</td>
            <td>{{ p.persona }}</td>
            <td>
              <button v-for="(c, i) in p.contextes" :key="c.chunk_id || i" type="button" class="fr-tag fr-tag--sm fr-mb-1v"
                      :title="`Lire le passage ${c.fichier ? `de « ${c.fichier} »` : ''}`" @click="lu = c">
                {{ c.fichier || `passage ${i + 1}` }}
              </button>
            </td>
            <td>
              <span class="fr-badge fr-badge--sm fr-mb-1v" :class="classeRelecture(p.relecture)">{{ libelleRelecture(p.relecture) }}</span>
              <p v-if="p.commentaire" class="fr-text--xs fr-mb-1v">« {{ p.commentaire }} »</p>
              <div class="gen-actions">
                <button v-if="p.relecture !== 'valide'" class="fr-btn fr-btn--sm fr-btn--secondary" @click="relire(p, 'valide')">Valider</button>
                <button v-if="p.relecture !== 'rejete'" class="fr-btn fr-btn--sm fr-btn--tertiary" @click="rejeter(p)">Rejeter</button>
                <button v-if="p.relecture !== 'brut'" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline" @click="relire(p, 'brut')">Annuler</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav v-if="page && page.pages > 1" class="gen-paires__pages" aria-label="Pages de paires">
      <button class="fr-btn fr-btn--sm fr-btn--tertiary" :disabled="page.page <= 1" @click="charger(page.page - 1)">Précédentes</button>
      <span class="fr-text--sm">Page {{ page.page }} sur {{ page.pages }}</span>
      <button class="fr-btn fr-btn--sm fr-btn--tertiary" :disabled="page.page >= page.pages" @click="charger(page.page + 1)">Suivantes</button>
    </nav>

    <PlaygroundSourceViewer :open="!!lu" url="" :titre="lu?.fichier || 'Passage'"
                            :sous-titre="lu ? `Passage ${lu.chunk_id} — document ${lu.file_id}` : undefined"
                            :contenu-initial="lu?.texte || ''" @close="lu = null" />
  </section>
</template>

<script setup lang="ts">
import {
  classeRelecture, libelleLongueur, libelleRelecture, libelleStyle, type Contexte, type Paire, type Run,
} from '~/utils/generation'
import { messageErreur } from '~/utils/collectif'

const props = defineProps<{ collection: string, run: Run }>()
const g = useGeneration()
const persona = ref('')
const relecture = ref('')
const page = ref<{ total: number, page: number, pages: number, paires: Paire[] } | null>(null)
const erreur = ref('')
const lu = ref<Contexte | null>(null)
const personasDuRun = computed(() => props.run.personas.map(p => p.nom))

async function charger(n = 1) {
  erreur.value = ''
  const params: Record<string, string> = { page: String(n), par_page: '25' }
  if (persona.value) params.persona = persona.value
  if (relecture.value) params.relecture = relecture.value
  try { page.value = await g.paires(props.collection, props.run.id, params) } catch (e) { erreur.value = messageErreur(e) }
}
watch([persona, relecture, () => props.run.id], () => charger(1), { immediate: true })

async function relire(p: Paire, etat: 'brut' | 'valide' | 'rejete', commentaire?: string) {
  try {
    const r = await g.relire(props.collection, p.id, { relecture: etat, ...(commentaire !== undefined ? { commentaire } : {}) })
    Object.assign(p, r.paire)
  } catch (e) { erreur.value = messageErreur(e) }
}
function rejeter(p: Paire) {
  const motif = prompt('Pourquoi rejeter cette paire ? (facultatif)', p.commentaire || '')
  if (motif === null) return
  relire(p, 'rejete', motif.trim())
}
async function exporter(format: 'csv' | 'json') {
  try { await g.exporter(props.collection, props.run.id, format) } catch (e) { erreur.value = messageErreur(e) }
}
</script>

<style scoped>
.gen-paires__tete { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: .5rem; margin-bottom: .5rem; }
.gen-paires__filtres { display: flex; flex-wrap: wrap; gap: 0 1.5rem; align-items: flex-end; margin-bottom: 1rem; }
.gen-paires__filtres .fr-select-group { min-width: 12rem; margin-bottom: 0; }
.gen-paires__q { min-width: 14rem; }
.gen-paires__r { min-width: 18rem; font-size: .875rem; }
.gen-paires__pages { display: flex; gap: 1rem; align-items: center; justify-content: center; }
.gen-actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
</style>
