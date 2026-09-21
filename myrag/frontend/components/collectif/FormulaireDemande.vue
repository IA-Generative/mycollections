<template>
  <form class="fr-callout" @submit.prevent="envoyer">
    <h3 class="fr-callout__title">Un jeu de données vous manque ?</h3>
    <div class="fr-input-group">
      <label class="fr-label" for="d-titre">Quel jeu de données ?
        <span class="fr-hint-text">En tapant, les demandes proches apparaissent : soutenez plutôt que de doublonner.</span></label>
      <input id="d-titre" v-model="f.titre" class="fr-input" required maxlength="200" @input="chercherDoublons">
    </div>
    <div v-if="doublons.length" class="collectif-doublons fr-mb-2w">
      <div v-for="d in doublons" :key="d.id">
        <span>Peut-être déjà demandé — <NuxtLink :to="`/demandes/${d.id}`"><strong>{{ d.titre }}</strong></NuxtLink>
          <span class="fr-badge fr-badge--sm fr-badge--info fr-ml-1w">{{ d.nb_soutiens }} / {{ d.seuil }} soutiens</span></span>
        <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary" :disabled="d.soutenue_par_moi" @click="$emit('moi-aussi', d.id)">
          {{ d.soutenue_par_moi ? 'Déjà soutenue' : 'Moi aussi' }}
        </button>
      </div>
    </div>
    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-12 fr-col-md-6">
        <div class="fr-input-group">
          <label class="fr-label" for="d-usage">Pour quel usage ?</label>
          <textarea id="d-usage" v-model="f.usage" class="fr-input" rows="3" required></textarea>
        </div>
      </div>
      <div class="fr-col-12 fr-col-md-6">
        <div class="fr-select-group">
          <label class="fr-label" for="d-freq">À quelle fréquence ?</label>
          <select id="d-freq" v-model="f.frequence" class="fr-select" required>
            <option v-for="fr in FREQUENCES" :key="fr.valeur" :value="fr.valeur">{{ fr.libelle }}</option>
          </select>
        </div>
        <div class="fr-input-group">
          <label class="fr-label" for="d-serv">Votre service</label>
          <input id="d-serv" v-model="f.service" class="fr-input" maxlength="120">
        </div>
      </div>
    </div>
    <div class="fr-input-group">
      <label class="fr-label" for="d-acces">Comment vous procurez-vous cette donnée aujourd'hui ? <span class="collectif-obligatoire">*</span>
        <span class="fr-hint-text">{{ MESSAGE_ACCES_ACTUEL }}</span></label>
      <textarea id="d-acces" v-model="f.acces_actuel" class="fr-input" rows="3" required></textarea>
    </div>
    <!-- Plus une question (décision PO du 2026-09-21) : l'auteur est joignable pour SA demande —
         sans lui, personne ne peut dire si la collection livrée y répond. On le dit, simplement. -->
    <div class="collectif-demandeur fr-mb-2w">
      <p class="fr-text--sm fr-mb-1w">
        <strong>Vous serez le demandeur</strong> — environ une demi-heure par semaine pendant le chantier :
        répondre aux questions de ceux qui construisent la collection, essayer les premières réponses, puis
        <strong>confirmer qu'elle répond à votre besoin</strong>.
      </p>
      <p v-if="mail" class="fr-text--sm fr-mb-0">Nous vous recontacterons à <strong>{{ mail }}</strong>.</p>
      <div v-else class="fr-input-group fr-mb-0">
        <label class="fr-label" for="d-contact">Votre courriel professionnel <span class="collectif-obligatoire">*</span></label>
        <input id="d-contact" v-model="f.contact" class="fr-input" type="email" required autocomplete="email">
      </div>
      <p class="fr-text--xs fr-mb-0 fr-mt-1w" style="color:var(--text-mention-grey)">
        Il n'est lu que par le garant de la demande et l'administration, et il est effacé quand la demande se termine.
      </p>
    </div>
    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"><p>{{ erreur }}</p></div>
    <button class="fr-btn" type="submit" :disabled="envoi">{{ envoi ? 'Dépôt…' : 'Déposer la demande' }}</button>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { FREQUENCES, MESSAGE_ACCES_ACTUEL, messageErreur } from '~/utils/collectif'
const props = defineProps<{ mail?: string; chercher: (q: string) => Promise<any[]>; deposer: (corps: any) => Promise<any> }>()
const emit = defineEmits<{ (e: 'deposee', demande: any): void; (e: 'moi-aussi', id: string): void }>()
const f = ref<any>({ titre: '', usage: '', frequence: 'hebdomadaire', service: '', acces_actuel: '', contact: '' })
const doublons = ref<any[]>([])
const erreur = ref('')
const envoi = ref(false)
let minuteur: any = null
function chercherDoublons() {
  clearTimeout(minuteur)
  const q = f.value.titre.trim()
  if (q.length < 4) { doublons.value = []; return }
  minuteur = setTimeout(async () => { try { doublons.value = (await props.chercher(q)).slice(0, 3) } catch { doublons.value = [] } }, 350)
}
async function envoyer() {
  erreur.value = ''
  const contact = (props.mail || f.value.contact || '').trim()
  if (!contact) { erreur.value = 'Votre courriel est attendu : c\'est par lui que le garant vous recontactera.'; return }
  envoi.value = true
  try {
    const corps = { ...f.value, contact }
    const r = await props.deposer(corps)
    emit('deposee', r.demande)
    f.value = { titre: '', usage: '', frequence: 'hebdomadaire', service: f.value.service, acces_actuel: '', contact: '' }
    doublons.value = []
  } catch (e) { erreur.value = messageErreur(e) }
  envoi.value = false
}
</script>
