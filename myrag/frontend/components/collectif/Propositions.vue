<template>
  <div>
    <form class="fr-callout fr-mb-3w" @submit.prevent="envoyer">
      <h4 class="fr-callout__title">Nouvelle proposition</h4>
      <div class="fr-grid-row fr-grid-row--gutters">
        <div class="fr-col-12 fr-col-md-4">
          <div class="fr-select-group"><label class="fr-label" for="p-cible">Cible</label>
            <select id="p-cible" v-model="f.cible_type" class="fr-select"><option value="ligne">Ligne de la table</option><option value="fichier">Fichier</option></select></div>
        </div>
        <div class="fr-col-12 fr-col-md-8">
          <div class="fr-input-group"><label class="fr-label" for="p-ref">{{ f.cible_type === 'ligne' ? 'Ligne · colonne' : 'Nom du fichier' }}</label>
            <input id="p-ref" v-model="f.cible_ref" class="fr-input" maxlength="255"></div>
        </div>
      </div>
      <div class="collectif-diff">
        <div class="av"><label class="fr-label fr-text--xs" for="p-avant">Avant</label><textarea id="p-avant" v-model="f.avant" class="fr-input" rows="3"></textarea></div>
        <div class="ap"><label class="fr-label fr-text--xs" for="p-apres">Après <span class="collectif-obligatoire">*</span></label><textarea id="p-apres" v-model="f.apres" class="fr-input" rows="3" required></textarea></div>
      </div>
      <div class="fr-input-group fr-mt-2w"><label class="fr-label" for="p-just">Justification <span class="collectif-obligatoire">*</span></label>
        <textarea id="p-just" v-model="f.justification" class="fr-input" rows="2" required></textarea></div>
      <div class="fr-input-group"><label class="fr-label" for="p-src">Source (facultative)</label><input id="p-src" v-model="f.source" class="fr-input"></div>
      <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"><p>{{ erreur }}</p></div>
      <button class="fr-btn" type="submit">Envoyer la proposition</button>
    </form>

    <p v-if="propositions === null" class="fr-text--sm" style="color:var(--text-mention-grey)">Propositions indisponibles.</p>
    <p v-else-if="propositions.length === 0" class="fr-text--sm" style="color:var(--text-mention-grey)">Aucune proposition pour l'instant.</p>
    <article v-for="p in propositions" :key="p.id" class="collectif-prop">
      <header>
        <strong>{{ p.cible_ref || (p.cible_type === 'fichier' ? 'fichier' : 'ligne') }}</strong>
        <span class="fr-badge fr-badge--sm" :class="{ proposee: 'fr-badge--new', publiee: 'fr-badge--success', refusee: 'fr-badge--error' }[p.etat]">{{ p.etat }}</span>
      </header>
      <div class="collectif-diff collectif-diff--lecture">
        <div class="av"><small>Avant</small>{{ p.avant || '—' }}</div>
        <div class="ap"><small>Après</small>{{ p.apres }}</div>
      </div>
      <p class="fr-text--sm fr-mt-1w" style="margin:0">{{ p.justification }}</p>
      <p class="fr-text--xs" style="margin:0;color:var(--text-mention-grey)">
        <template v-if="p.source">Source : <a :href="p.source" class="fr-link fr-text--xs" target="_blank" rel="noopener">{{ p.source }}</a> · </template>
        déposée le {{ dateCourte(p.cree_le) }}<template v-if="p.decide_le"> · décidée le {{ dateCourte(p.decide_le) }}</template>
      </p>
      <p v-if="p.motif_refus" class="fr-text--sm" style="margin:0"><strong>Motif du refus :</strong> {{ p.motif_refus }}</p>
      <div v-if="garant && p.etat === 'proposee'" class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-1w">
        <button class="fr-btn fr-btn--sm" @click="$emit('publier', p.id)">Publier</button>
        <button class="fr-btn fr-btn--sm fr-btn--secondary" @click="refus = refus === p.id ? '' : p.id">Refuser…</button>
      </div>
      <div v-if="refus === p.id" class="fr-mt-1w">
        <input v-model="motif" class="fr-input" placeholder="Motif du refus (obligatoire)" aria-label="Motif du refus">
        <button class="fr-btn fr-btn--sm fr-mt-1w" :disabled="!motif.trim()" @click="$emit('refuser', p.id, motif); refus = ''; motif = ''">Confirmer le refus</button>
      </div>
    </article>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { dateCourte, messageErreur } from '~/utils/collectif'
const props = defineProps<{ propositions: any[] | null; garant?: boolean; proposer: (corps: any) => Promise<any> }>()
const emit = defineEmits<{ (e: 'deposee'): void; (e: 'publier', id: string): void; (e: 'refuser', id: string, motif: string): void }>()
const f = ref({ cible_type: 'ligne', cible_ref: '', avant: '', apres: '', justification: '', source: '' })
const erreur = ref('')
const refus = ref('')
const motif = ref('')
async function envoyer() {
  erreur.value = ''
  try {
    await props.proposer({ ...f.value, source: f.value.source || null })
    f.value = { cible_type: 'ligne', cible_ref: '', avant: '', apres: '', justification: '', source: '' }
    emit('deposee')
  } catch (e) { erreur.value = messageErreur(e) }
}
</script>
