<template>
  <div>
    <form v-if="actif" class="fr-callout fr-mb-3w" @submit.prevent="envoyer">
      <h4 class="fr-callout__title">Signaler un défaut</h4>
      <fieldset class="fr-fieldset">
        <legend class="fr-fieldset__legend fr-text--regular">Motif</legend>
        <div class="collectif-roles">
          <button v-for="m in MOTIFS" :key="m.valeur" type="button" class="collectif-roles__role" :class="{ pris: f.motif === m.valeur }" @click="f.motif = m.valeur">{{ m.libelle }}</button>
        </div>
      </fieldset>
      <div class="fr-input-group"><label class="fr-label" for="s-txt">Que s'est-il passé ? <span class="collectif-obligatoire">*</span></label>
        <textarea id="s-txt" v-model="f.texte" class="fr-input" rows="3" required></textarea></div>
      <div v-if="fichiers && fichiers.length" class="fr-select-group"><label class="fr-label" for="s-fic">Document concerné (facultatif)</label>
        <select id="s-fic" v-model="f.fichier_id" class="fr-select"><option :value="null">—</option><option v-for="x in fichiers" :key="x.id" :value="x.id">{{ x.filename }}</option></select></div>
      <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"><p>{{ erreur }}</p></div>
      <button class="fr-btn" type="submit" :disabled="!f.motif">Envoyer le signalement</button>
    </form>
    <p v-else class="fr-text--sm" style="color:var(--text-mention-grey)">Le signalement n'est pas activé sur cette plateforme.</p>

    <p v-if="signalements === null" class="fr-text--sm" style="color:var(--text-mention-grey)">Signalements indisponibles.</p>
    <p v-else-if="signalements.length === 0" class="fr-text--sm" style="color:var(--text-mention-grey)">Aucun signalement.</p>
    <article v-for="s in signalements" :key="s.id" class="collectif-prop">
      <header>
        <strong>{{ { obsolete: 'Obsolète', erreur: 'Erreur', manquant: 'Manquant' }[s.motif] || s.motif }}</strong>
        <span class="fr-badge fr-badge--sm" :class="{ ouvert: 'fr-badge--new', pris_en_compte: 'fr-badge--info', clos: 'fr-badge--success' }[s.etat]">{{ s.etat.replace('_', ' ') }}</span>
      </header>
      <p class="fr-text--sm" style="margin:0">{{ s.texte }}</p>
      <p class="fr-text--xs" style="margin:0;color:var(--text-mention-grey)">déposé le {{ dateCourte(s.cree_le) }}<template v-if="s.fichier_id"> · document n° {{ s.fichier_id }}</template></p>
      <div v-if="garant && s.etat !== 'clos'" class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-1w">
        <button v-if="s.etat === 'ouvert'" class="fr-btn fr-btn--sm fr-btn--secondary" @click="$emit('traiter', s.id, 'pris_en_compte')">Prendre en compte</button>
        <button class="fr-btn fr-btn--sm" @click="$emit('traiter', s.id, 'clos')">Clore</button>
      </div>
    </article>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { dateCourte, messageErreur } from '~/utils/collectif'
const props = defineProps<{ signalements: any[] | null; garant?: boolean; actif?: boolean; fichiers?: any[]; signaler: (corps: any) => Promise<any> }>()
const emit = defineEmits<{ (e: 'depose'): void; (e: 'traiter', id: string, etat: string): void }>()
const MOTIFS = [{ valeur: 'obsolete', libelle: 'obsolète' }, { valeur: 'erreur', libelle: 'erreur' }, { valeur: 'manquant', libelle: 'manquant' }]
const f = ref<any>({ motif: '', texte: '', fichier_id: null })
const erreur = ref('')
async function envoyer() {
  erreur.value = ''
  try {
    await props.signaler({ ...f.value })
    f.value = { motif: '', texte: '', fichier_id: null }
    emit('depose')
  } catch (e) { erreur.value = messageErreur(e) }
}
</script>
