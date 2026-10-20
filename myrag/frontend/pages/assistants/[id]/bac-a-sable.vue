<script setup lang="ts">
import type { ChatMessage } from '~/composables/useChat'
import type { FicheAssistant, ResultatAssistant } from '~/utils/assistants'
import { sourceDuPassage, traceDuPlan } from '~/utils/assistants'

/**
 * Le bac à sable d'un assistant (B4) : poser des questions comme un collègue et voir, sous chaque
 * réponse, comment l'assistant a cherché. Composé des briques du bac à sable d'une collection
 * (`PlaygroundChatMessage` : réponse en Markdown assaini, puces de source, fenêtre de lecture,
 * repli de la trace), pointées sur `POST /api/v1/assistants/{id}/executer`.
 */
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
const route = useRoute()
const id = route.params.id as string
useHead({ title: `Bac à sable — ${id} — Mes collections` })

const { executer } = useAssistants()
const { titre: titreSource } = useTitresSources()

type Tour = ChatMessage & { resultat?: ResultatAssistant }
const messages = ref<Tour[]>([])
const brouillon = ref('')
const enCours = ref(false)
const zoneMessages = ref<HTMLElement | null>(null)
const peutEnvoyer = computed(() => !enCours.value && brouillon.value.trim().length > 0)

function defiler () {
  nextTick(() => {
    if (zoneMessages.value) {
      zoneMessages.value.scrollTop = zoneMessages.value.scrollHeight
    }
  })
}

/** Le tour de l'assistant : sa réponse, ou, s'il n'en rédige pas, ce qu'il a trouvé. */
function tourDepuis (r: ResultatAssistant): Tour {
  const n = r.passages.length
  const contenu = r.reponse?.trim()
    || (n
      ? `L'assistant a trouvé ${n} passage${n > 1 ? 's' : ''}, sans rédiger de réponse : ouvrez-les ci-dessous.`
      : 'L\'assistant n\'a rien trouvé pour cette question.')
  return {
    role: 'assistant',
    content: contenu,
    sources: r.passages.map(p => sourceDuPassage(p, titreSource)),
    turnId: `tour-${Date.now()}`,
    resultat: r,
  }
}

async function envoyer (texte?: string) {
  const q = (texte ?? brouillon.value).trim().slice(0, 1000)
  if (!q || enCours.value) {
    return
  }
  brouillon.value = ''
  messages.value.push({ role: 'user', content: q })
  enCours.value = true
  defiler()
  try {
    messages.value.push(tourDepuis(await executer(id, q)))
  }
  catch (e) {
    messages.value.push({ role: 'assistant', content: `La question n'a pas pu aboutir : ${messageErreur(e)}`, error: true })
  }
  finally {
    enCours.value = false
    defiler()
  }
}

/** Les exemples des consignes : des questions toutes prêtes pour commencer. */
function exemples (fiche: FicheAssistant): string[] {
  return [...new Set(fiche.consignes.flatMap(c => c.exemples))].slice(0, 6)
}

onMounted(() => {
  // Une question arrive saisie (lien « Essayer cette question ») : il reste à l'envoyer.
  const q = String(route.query.q || '').trim()
  if (q) {
    brouillon.value = q.slice(0, 1000)
  }
})
</script>

<template>
  <AssistantsCadre
    :id="id"
    rubrique="Bac à sable"
  >
    <template #default="{ donnees }">
      <p class="fr-text--sm">
        Posez une question comme le ferait un collègue. Sous chaque réponse, « Comment l'assistant a
        cherché » montre la consigne retenue et les sources interrogées.
      </p>

      <div
        v-if="!messages.length && exemples(donnees.fiche).length"
        class="fr-mb-2w"
      >
        <p class="fr-text--sm fr-mb-1w">
          Pour commencer :
        </p>
        <ul class="fr-tags-group">
          <li
            v-for="q in exemples(donnees.fiche)"
            :key="q"
          >
            <button
              type="button"
              class="fr-tag"
              :disabled="enCours"
              @click="envoyer(q)"
            >
              {{ q }}
            </button>
          </li>
        </ul>
      </div>

      <div
        v-if="messages.length"
        ref="zoneMessages"
        class="bac-messages"
        aria-live="polite"
      >
        <PlaygroundChatMessage
          v-for="(m, i) in messages"
          :key="m.turnId || i"
          :message="m"
          titre-trace="Comment l'assistant a cherché"
          sans-avis
        >
          <template
            v-if="m.resultat"
            #trace
          >
            <AssistantsTrace :trace="traceDuPlan(m.resultat.plan, donnees.fiche, titreSource, m.resultat)" />
          </template>
        </PlaygroundChatMessage>
        <p
          v-if="enCours"
          class="fr-text--sm bac-discret"
        >
          L'assistant cherche…
        </p>
      </div>

      <form
        class="bac-saisie"
        @submit.prevent="envoyer()"
      >
        <div class="fr-input-group">
          <label
            class="fr-label"
            for="question"
          >Votre question</label>
          <textarea
            id="question"
            v-model="brouillon"
            class="fr-input"
            rows="2"
            maxlength="1000"
            placeholder="Votre question…"
            @keydown.enter.exact.prevent="peutEnvoyer && envoyer()"
          />
        </div>
        <ul class="fr-btns-group fr-btns-group--inline-sm fr-btns-group--icon-left">
          <li>
            <button
              type="submit"
              class="fr-btn fr-icon-send-plane-line"
              :disabled="!peutEnvoyer"
            >
              {{ enCours ? 'Envoi…' : 'Envoyer' }}
            </button>
          </li>
          <li>
            <button
              type="button"
              class="fr-btn fr-btn--secondary fr-icon-delete-line"
              :disabled="!messages.length || enCours"
              @click="messages = []"
            >
              Effacer
            </button>
          </li>
        </ul>
        <p class="fr-text--xs bac-discret fr-mb-0">
          Les questions posées ici servent à essayer l'assistant. Recueillir l'avis de vos collègues
          sur ses réponses viendra plus tard.
        </p>
      </form>
    </template>
  </AssistantsCadre>
</template>

<style scoped>
.bac-discret { color: var(--text-mention-grey); }
.bac-messages { max-height: 36rem; overflow-y: auto; padding-right: .3rem; margin-bottom: 1rem; }
/* Les messages défilent dans leur cadre : la saisie reste juste dessous, sans recouvrir la page. */
.bac-saisie { padding-top: .5rem; }
</style>
