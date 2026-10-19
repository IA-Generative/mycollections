<script setup lang="ts">
import type { Question } from '~/utils/qualite'
import { messageErreur } from '~/utils/collectif'
import { classeRelecture, libelleRelecture } from '~/utils/generation'
import { classeVerdict, conseils, dateMesure, libelleOrigine, libelleVerdict } from '~/utils/qualite'
import { renderMarkdownSafe } from '~/utils/sanitize'

/**
 * Le volet d'une question : sa référence (modifiable), ce que la collection a répondu à la
 * dernière mesure, le verdict et sa raison, et ce qu'on peut faire selon le défaut.
 */
const props = defineProps<{ collection: string, ident: string | null }>()
const emit = defineEmits<{ fermer: [], change: [], levier: [nom: 'decoupage' | 'consignes'] }>()
const api = useQualite(props.collection)
const uid = `volet-${useId()}`
const boite = ref<HTMLDialogElement | null>(null)
const zoneReponse = ref<HTMLTextAreaElement | null>(null)
const q = ref<Question | null>(null)
const r = ref<any>(null)
const test = ref(false)
const reponse = ref('')
const enTest = ref(false)
const erreur = ref('')

const pistes = computed(() => (q.value ? conseils(r.value?.verdict ?? q.value.dernier_verdict, q.value.hors_sujet) : []))
const nomsSources = (s: any[]) => [...new Set(s.map(x => (typeof x === 'string' ? x : (x.fichier || x.filename || x.source || ''))).filter(Boolean))]

async function charger (id: string) {
  q.value = null
  r.value = null
  test.value = false
  erreur.value = ''
  try {
    const d = await api.question(id)
    q.value = d.question
    r.value = d.dernier_resultat
    reponse.value = d.question.reponse
  }
  catch (e) {
    erreur.value = `La question n'a pas pu être lue : ${messageErreur(e)}`
  }
}

watch(() => props.ident, (id) => {
  if (id) {
    charger(id)
    if (!boite.value?.open) { boite.value?.showModal() }
  }
  else if (boite.value?.open) {
    boite.value.close()
  }
})

onMounted(() => {
  if (props.ident) {
    charger(props.ident)
    boite.value?.showModal()
  }
})

function fermer () {
  boite.value?.close()
}

async function modifier (champs: Record<string, unknown>) {
  if (!q.value) { return }
  erreur.value = ''
  try {
    q.value = (await api.modifier(q.value.id, champs)).question
    reponse.value = q.value!.reponse
    if ('reponse' in champs) { r.value = null } // la mesure ne vaut plus pour une référence changée
    emit('change')
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
}

async function tester () {
  if (!q.value) { return }
  enTest.value = true
  erreur.value = ''
  try {
    r.value = await api.tester(q.value.id)
    test.value = true
  }
  catch (e) {
    erreur.value = `Le test a échoué : ${messageErreur(e)}`
  }
  finally {
    enTest.value = false
  }
}

function levier (nom: 'decoupage' | 'consignes') {
  emit('levier', nom)
  fermer()
}
</script>

<template>
  <dialog
    ref="boite"
    class="volet"
    :aria-labelledby="`${uid}-titre`"
    @close="emit('fermer')"
    @cancel="emit('fermer')"
  >
    <div
      v-if="q"
      class="volet__contenu"
    >
      <div class="volet__entete">
        <div>
          <p class="fr-text--xs fr-mb-1v volet__discret">
            {{ libelleOrigine(q.origine) }}<template v-if="q.persona">
              · {{ q.persona }}
            </template>
            · <span
              class="fr-badge fr-badge--sm fr-badge--no-icon"
              :class="classeRelecture(q.relecture)"
            >{{ libelleRelecture(q.relecture) }}</span>
          </p>
          <h2
            :id="`${uid}-titre`"
            class="fr-h5 fr-mb-0"
          >
            « {{ q.question }} »
          </h2>
        </div>
        <button
          type="button"
          class="fr-btn--close fr-btn"
          title="Fermer le volet"
          @click="fermer"
        >
          Fermer
        </button>
      </div>

      <div class="volet__colonnes">
        <section :aria-labelledby="`${uid}-ref`">
          <h3
            :id="`${uid}-ref`"
            class="fr-h6 fr-mb-1w"
          >
            {{ q.hors_sujet ? 'Attendu' : 'Réponse de référence' }}
          </h3>
          <p
            v-if="q.hors_sujet"
            class="fr-text--sm"
          >
            Question hors sujet : la collection doit refuser poliment d'y répondre.
          </p>
          <div
            v-else
            class="fr-input-group"
          >
            <label
              class="fr-label fr-sr-only"
              :for="`${uid}-reponse`"
            >Réponse de référence</label>
            <textarea
              :id="`${uid}-reponse`"
              ref="zoneReponse"
              v-model="reponse"
              class="fr-input"
              rows="7"
              maxlength="8000"
            />
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--secondary fr-mt-1w"
              :disabled="reponse.trim() === q.reponse.trim()"
              @click="modifier({ reponse: reponse.trim() })"
            >
              Enregistrer la réponse
            </button>
          </div>
          <details
            v-if="q.contextes?.length"
            class="fr-mt-1w"
          >
            <summary class="fr-text--sm volet__resume">
              Passage{{ q.contextes.length > 1 ? 's' : '' }} d'où elle est tirée ({{ q.contextes.length }})
            </summary>
            <blockquote
              v-for="c in q.contextes"
              :key="c.chunk_id"
              class="fr-text--xs volet__passage"
            >
              <strong>{{ c.fichier }}</strong><br>{{ c.texte }}
            </blockquote>
          </details>
        </section>

        <section :aria-labelledby="`${uid}-obt`">
          <h3
            :id="`${uid}-obt`"
            class="fr-h6 fr-mb-1w"
          >
            Réponse obtenue
          </h3>
          <template v-if="r">
            <p class="fr-text--xs fr-mb-1w volet__discret">
              {{ test ? 'Test à l\'instant' : `Mesure du ${dateMesure(q.derniere_mesure_le)}` }}
            </p>
            <div
              class="fr-text--sm volet__obtenue"
              v-html="renderMarkdownSafe(r.reponse_obtenue || '(aucune réponse)')"
            />
            <p
              v-if="r.sources?.length"
              class="fr-text--xs fr-mt-1w volet__discret"
            >
              Sources : {{ nomsSources(r.sources).join(', ') }}
            </p>
            <p
              v-else
              class="fr-text--xs fr-mt-1w volet__discret"
            >
              Aucun passage trouvé par la recherche.
            </p>
            <p class="fr-mt-1w fr-mb-0">
              <span
                class="fr-badge fr-badge--sm"
                :class="classeVerdict(r.verdict)"
              >{{ libelleVerdict(r.verdict) }}</span>
            </p>
            <p
              v-if="r.justification"
              class="fr-text--sm fr-mt-1v"
            >
              « {{ r.justification }} »
            </p>
          </template>
          <p
            v-else
            class="fr-text--sm"
          >
            Cette question n'a pas encore été mesurée. Testez-la pour voir ce que répond la collection.
          </p>
          <button
            type="button"
            class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-refresh-line fr-btn--icon-left"
            :disabled="enTest"
            @click="tester"
          >
            {{ enTest ? 'Question posée à la collection…' : 'Re-tester cette question' }}
          </button>
        </section>
      </div>

      <section
        v-if="pistes.length"
        class="volet__conseils"
        :aria-labelledby="`${uid}-faire`"
      >
        <h3
          :id="`${uid}-faire`"
          class="fr-h6 fr-mb-1w"
        >
          Que faire ?
        </h3>
        <ul class="volet__pistes">
          <li v-if="pistes.includes('corriger')">
            <strong>La réponse de référence est fausse ou incomplète</strong> : corrigez-la ci-dessus, puis re-testez.
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline"
              @click="zoneReponse?.focus()"
            >
              Corriger
            </button>
          </li>
          <li v-if="pistes.includes('decoupage')">
            <strong>Le bon passage n'a pas été trouvé, ou il est coupé</strong> (une liste séparée en deux, par exemple) :
            réindexer les documents peut aider.
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline"
              @click="levier('decoupage')"
            >
              Réindexer les documents
            </button>
          </li>
          <li v-if="pistes.includes('consignes')">
            <strong>{{ q.hors_sujet ? 'La collection a répondu à une question hors sujet' : 'Les consignes doivent demander autre chose' }}</strong>
            ({{ q.hors_sujet ? 'une règle de garde l\'en empêche' : 'citer la liste complète, préciser les délais…' }}).
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline"
              @click="levier('consignes')"
            >
              Voir les consignes
            </button>
          </li>
          <li v-if="pistes.includes('fiable') && q.relecture === 'valide'">
            <strong>Cette réponse doit être donnée telle quelle</strong> : marquez-la « réponse fiable ».
            Elle sera servie en priorité (fonction à venir).
          </li>
        </ul>
      </section>

      <div
        v-if="erreur"
        class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"
        role="alert"
      >
        <p>{{ erreur }}</p>
      </div>

      <div class="volet__pied">
        <button
          v-if="q.relecture !== 'valide'"
          type="button"
          class="fr-btn fr-btn--sm"
          :disabled="!q.hors_sujet && !q.reponse.trim()"
          @click="modifier({ relecture: 'valide' })"
        >
          Valider
        </button>
        <button
          v-if="q.relecture !== 'rejete'"
          type="button"
          class="fr-btn fr-btn--sm fr-btn--secondary"
          @click="modifier({ relecture: 'rejete' })"
        >
          Rejeter
        </button>
        <div
          v-if="q.relecture === 'valide' && !q.hors_sujet"
          class="fr-checkbox-group fr-checkbox-group--sm volet__fiable"
        >
          <input
            :id="`${uid}-fiable`"
            type="checkbox"
            :checked="q.fiable"
            @change="modifier({ fiable: !q.fiable })"
          >
          <label
            class="fr-label"
            :for="`${uid}-fiable`"
          >Réponse fiable</label>
        </div>
      </div>
    </div>
    <p
      v-else
      class="volet__contenu"
      aria-live="polite"
    >
      {{ erreur || 'Chargement…' }}
    </p>
  </dialog>
</template>

<style scoped>
.volet {
  margin: 0 0 0 auto; height: 100%; max-height: 100%; width: min(56rem, 100%); max-width: 100%;
  border: none; padding: 0; background: var(--background-default-grey); color: var(--text-default-grey);
  box-shadow: 0 0 2rem rgba(0, 0, 0, .25);
}
.volet::backdrop { background: rgba(22, 22, 22, .45); }
.volet__contenu { padding: 1.5rem; display: grid; gap: 1.5rem; }
.volet__entete { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
.volet__colonnes { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1.5rem; }
@media (max-width: 48em) { .volet__colonnes { grid-template-columns: minmax(0, 1fr); } }
.volet__obtenue { background: var(--background-alt-grey); padding: .75rem; max-height: 18rem; overflow-y: auto; }
.volet__obtenue :deep(p), .volet__obtenue :deep(ul), .volet__obtenue :deep(ol) { margin: 0 0 .5rem; }
.volet__obtenue :deep(h1), .volet__obtenue :deep(h2), .volet__obtenue :deep(h3) { font-size: 1rem; margin: .5rem 0 .25rem; }
.volet__passage { margin: .5rem 0; padding-left: .75rem; border-left: 3px solid var(--border-default-grey); white-space: pre-wrap; max-height: 12rem; overflow-y: auto; }
.volet__resume { cursor: pointer; }
.volet__conseils { border-top: 1px solid var(--border-default-grey); padding-top: 1rem; }
.volet__pistes { display: grid; gap: .5rem; }
.volet__pistes .fr-btn { margin-left: .25rem; vertical-align: baseline; }
.volet__pied { border-top: 1px solid var(--border-default-grey); padding-top: 1rem; display: flex; flex-wrap: wrap; gap: .75rem; align-items: center; }
.volet__fiable { margin: 0; }
.volet__discret { color: var(--text-mention-grey); }
</style>
