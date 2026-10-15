<template>
  <div class="avis">
    <p class="fr-text--sm">
      Les votes 👍 / 👎 des usagers, dans le bac à sable et dans l'assistant. Un avis négatif est souvent une
      question de référence toute trouvée : écrivez la bonne réponse, elle rejoint le jeu, validée.
    </p>
    <div class="avis__filtres">
      <div class="fr-select-group fr-mb-0">
        <label class="fr-label" for="avis-statut">Afficher</label>
        <select id="avis-statut" v-model="statut" class="fr-select">
          <option value="pending">À relire</option>
          <option value="">Tous</option>
          <option value="promoted">Devenus des questions</option>
          <option value="reviewed">Lus</option>
        </select>
      </div>
      <div class="fr-select-group fr-mb-0">
        <label class="fr-label" for="avis-note">Note</label>
        <select id="avis-note" v-model="note" class="fr-select">
          <option value="">Toutes</option>
          <option value="-1">👎 négatifs</option>
          <option value="1">👍 positifs</option>
        </select>
      </div>
    </div>

    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w" role="alert"><p>{{ erreur }}</p></div>
    <div v-if="message" class="fr-alert fr-alert--success fr-alert--sm fr-mt-2w" role="status"><p>{{ message }}</p></div>
    <p v-if="avis === null" class="fr-text--sm fr-mt-2w">Chargement…</p>
    <div v-else-if="!avis.length" class="fr-callout fr-mt-2w"><p class="fr-callout__text fr-text--sm">Aucun avis pour ces critères.</p></div>

    <ul v-else class="avis__liste fr-mt-2w">
      <li v-for="a in avis" :key="a.id" class="avis__item" :class="a.rating < 0 ? 'avis__item--neg' : 'avis__item--pos'">
        <p class="fr-mb-1v">
          <span aria-hidden="true">{{ a.rating > 0 ? '👍' : '👎' }}</span>
          <span class="fr-sr-only">{{ a.rating > 0 ? 'Avis positif' : 'Avis négatif' }}</span>
          <strong class="fr-ml-1v">{{ a.question }}</strong>
        </p>
        <p class="fr-text--xs fr-mb-1v avis__discret">
          {{ dateMesure(a.created_at) }} · {{ libelleStatutAvis(a.status) }}
          <template v-if="a.reason"> · motif : « {{ a.reason }} »</template>
        </p>
        <details v-if="a.response">
          <summary class="fr-text--sm avis__resume">Réponse donnée</summary>
          <p class="fr-text--sm avis__texte">{{ a.response }}</p>
        </details>

        <form v-if="ouvert === a.id" class="avis__form" @submit.prevent="enFaireUneQuestion(a)">
          <div class="fr-input-group fr-mb-1w">
            <label class="fr-label" :for="`avis-rep-${a.id}`">Bonne réponse
              <span class="fr-hint-text">Laissée vide, la question rejoint le jeu « à relire ».</span>
            </label>
            <textarea :id="`avis-rep-${a.id}`" v-model="reponse" class="fr-input" rows="4" maxlength="8000" />
          </div>
          <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
            <button type="submit" class="fr-btn">Ajouter au jeu de questions</button>
            <button type="button" class="fr-btn fr-btn--tertiary" @click="ouvert = null">Annuler</button>
          </div>
        </form>
        <div v-else-if="a.status !== 'promoted'" class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-btns-group--icon-left fr-mt-1w">
          <button type="button" class="fr-btn fr-btn--secondary fr-icon-add-line fr-btn--icon-left" @click="ouvrir(a)">En faire une question de référence</button>
          <button v-if="a.status === 'pending'" type="button" class="fr-btn fr-btn--tertiary" @click="marquerLu(a)">Marquer comme lu</button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { dateMesure } from '~/utils/qualite'
import { libelleStatutAvis } from '~/utils/libelles'
import { messageErreur } from '~/utils/collectif'

/** Les avis des usagers, et le geste qui en fait une question de référence. */
const props = defineProps<{ collection: string }>()
const emit = defineEmits<{ change: [] }>()
const api = useQualite(props.collection)
const avis = ref<any[] | null>(null)
const statut = ref('pending')
const note = ref('')
const ouvert = ref<number | null>(null)
const reponse = ref('')
const erreur = ref('')
const message = ref('')

async function charger() {
  erreur.value = ''
  const params: Record<string, string> = {}
  if (statut.value) params.status = statut.value
  if (note.value) params.rating = note.value
  try {
    avis.value = (await api.avis(params)).feedback || []
  } catch (e) {
    erreur.value = `Les avis n'ont pas pu être lus : ${messageErreur(e)}`
    avis.value = []
  }
}
watch([statut, note], charger)
onMounted(charger)

function ouvrir(a: any) {
  ouvert.value = a.id
  message.value = ''
  // Un avis positif : la réponse donnée était bonne, on la propose comme référence.
  reponse.value = a.rating > 0 ? (a.response || '') : ''
}

async function enFaireUneQuestion(a: any) {
  erreur.value = ''
  try {
    await api.depuisAvis(a.id, reponse.value.trim())
    message.value = reponse.value.trim()
      ? 'La question a rejoint le jeu, validée, avec votre réponse.'
      : 'La question a rejoint le jeu « à relire » : ajoutez sa réponse de référence.'
    ouvert.value = null
    await charger()
    emit('change')
  } catch (e) {
    erreur.value = messageErreur(e)
  }
}

async function marquerLu(a: any) {
  try {
    await api.marquerLu(a.id)
    await charger()
    emit('change')
  } catch (e) {
    erreur.value = messageErreur(e)
  }
}
</script>

<style scoped>
.avis__filtres { display: flex; flex-wrap: wrap; gap: 1rem; }
.avis__liste { list-style: none; padding: 0; margin: 0; display: grid; gap: .75rem; }
.avis__item { border: 1px solid var(--border-default-grey); border-left-width: 4px; padding: .75rem 1rem; min-width: 0; }
.avis__item--neg { border-left-color: var(--border-plain-error); }
.avis__item--pos { border-left-color: var(--border-plain-success); }
.avis__form { margin-top: .75rem; }
.avis__texte { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--background-alt-grey); padding: .5rem; max-height: 14rem; overflow-y: auto; }
.avis__resume { cursor: pointer; }
.avis__discret { color: var(--text-mention-grey); }
</style>
