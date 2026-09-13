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
    <fieldset class="fr-fieldset">
      <legend class="fr-fieldset__legend fr-text--regular">Acceptez-vous d'être recontacté·e pour soutenir cette initiative ? <span class="collectif-obligatoire">*</span>
        <span class="fr-hint-text">Votre courriel n'est enregistré qu'avec votre accord, et ne sert qu'à cette demande.</span></legend>
      <div class="fr-fieldset__element fr-fieldset__element--inline">
        <div class="fr-radio-group fr-radio-group--sm"><input id="d-rc-oui" v-model="f.recontact" type="radio" :value="true" name="recontact" required><label class="fr-label" for="d-rc-oui">Oui{{ mail ? `, à ${mail}` : '' }}</label></div>
      </div>
      <div class="fr-fieldset__element fr-fieldset__element--inline">
        <div class="fr-radio-group fr-radio-group--sm"><input id="d-rc-non" v-model="f.recontact" type="radio" :value="false" name="recontact"><label class="fr-label" for="d-rc-non">Non</label></div>
      </div>
    </fieldset>
    <div v-if="f.recontact === true && !mail" class="fr-input-group">
      <label class="fr-label" for="d-contact">Votre courriel</label>
      <input id="d-contact" v-model="f.contact" class="fr-input" type="email" required>
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
const f = ref<any>({ titre: '', usage: '', frequence: 'hebdomadaire', service: '', acces_actuel: '', recontact: null, contact: '' })
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
  if (f.value.recontact === null) { erreur.value = 'La réponse à la question du recontact est attendue.'; return }
  envoi.value = true
  try {
    const corps = { ...f.value, contact: f.value.recontact ? (props.mail || f.value.contact || null) : null }
    const r = await props.deposer(corps)
    emit('deposee', r.demande)
    f.value = { titre: '', usage: '', frequence: 'hebdomadaire', service: f.value.service, acces_actuel: '', recontact: null, contact: '' }
    doublons.value = []
  } catch (e) { erreur.value = messageErreur(e) }
  envoi.value = false
}
</script>
