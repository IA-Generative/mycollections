<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous êtes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/demandes">Demandes de la communauté</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">{{ d ? d.titre : id }}</a></li>
      </ol>
    </nav>
    <div v-if="chargement" class="fr-callout"><p>Chargement…</p></div>
    <div v-else-if="!d" class="fr-alert fr-alert--warning"><p>Demande introuvable.</p></div>
    <div v-else class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-12 fr-col-md-7">
        <h1 class="fr-h3">{{ d.titre }}</h1>
        <div class="fr-mb-2w">
          <span class="fr-badge fr-badge--sm" :class="LIBELLES_DEMANDE[d.etat]?.badge">{{ LIBELLES_DEMANDE[d.etat]?.libelle || d.etat }}</span>
          <span v-if="d.sommeil" class="fr-badge fr-badge--sm fr-ml-1w">en sommeil</span>
          <span class="fr-badge fr-badge--sm fr-badge--info fr-ml-1w">{{ progression(d.nb_soutiens, d.seuil).texte }} soutiens</span>
          <span class="fr-badge fr-badge--sm fr-ml-1w" :class="d.garant ? 'fr-badge--success' : 'fr-badge--warning'">{{ d.garant ? '✓ garant' : 'garant à pourvoir' }}</span>
        </div>
        <dl class="collectif-grille">
          <div><dt>Usage</dt><dd>{{ d.usage }}</dd></div>
          <div><dt>Fréquence</dt><dd>{{ d.frequence }}</dd></div>
          <div><dt>Service</dt><dd>{{ d.service || '—' }}</dd></div>
          <div><dt>Aujourd'hui</dt><dd>{{ d.acces_actuel }}</dd></div>
          <div><dt>Seuil figé</dt><dd>{{ d.seuil }} soutiens et un garant<span v-if="ceQuiManque(d)"> — {{ ceQuiManque(d) }}</span></dd></div>
          <div><dt>Rôles pris</dt><dd><template v-if="Object.keys(d.roles || {}).length"><span v-for="(n, r) in d.roles" :key="r" class="fr-badge fr-badge--sm fr-mr-1w">{{ r }} : {{ n }}</span></template><span v-else class="collectif-grille__vide">personne encore</span>
            <span v-if="d.temps_declare_min" class="fr-text--xs"> · {{ Math.round(d.temps_declare_min / 60) }} h déclarées</span></dd></div>
          <div v-if="d.collection_name"><dt>Collection</dt><dd><NuxtLink :to="`/c/${d.collection_name}`" class="fr-link">{{ d.collection_name }}</NuxtLink></dd></div>
          <div v-if="d.motif_cloture || d.doublon_de"><dt>Clôture</dt><dd>{{ d.motif_cloture || '' }}<NuxtLink v-if="d.doublon_de" :to="`/demandes/${d.doublon_de}`" class="fr-link"> doublon d'une autre demande</NuxtLink></dd></div>
        </dl>
        <div v-if="!['realisee', 'close'].includes(d.etat)" class="fr-mt-3w">
          <h2 class="fr-h6">Je peux aider</h2>
          <CollectifJePeuxAider :mon-role="d.mon_role" :garant="d.garant" @choisir="aider" />
          <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-2w">
            <button class="fr-btn fr-btn--sm" :class="d.soutenue_par_moi ? 'fr-btn--tertiary' : ''" @click="d.soutenue_par_moi ? retirer() : aider('soutien', 0)">{{ d.soutenue_par_moi ? 'Retirer mon soutien' : 'Moi aussi' }}</button>
            <button v-if="superadmin && d.garant" class="fr-btn fr-btn--sm fr-btn--secondary" @click="retirerGarant">Retirer le garant</button>
            <button v-if="peutClore" class="fr-btn fr-btn--sm fr-btn--tertiary" @click="cloture = !cloture">Clore…</button>
          </div>
          <div v-if="cloture" class="fr-mt-2w">
            <input v-model="motifCloture" class="fr-input" placeholder="Motif de clôture" aria-label="Motif de clôture">
            <button class="fr-btn fr-btn--sm fr-mt-1w" :disabled="!motifCloture.trim()" @click="clore">Confirmer la clôture</button>
          </div>
        </div>
        <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w"><p>{{ erreur }}</p></div>
      </div>
      <div class="fr-col-12 fr-col-md-5">
        <CollectifAvancement :evenements="evenements" :suivant="suivant" :abonne="d.abonne" abonnable @abonner="abonner" @suite="suite" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { LIBELLES_DEMANDE, ceQuiManque, messageErreur, progression } from '~/utils/collectif'
const route = useRoute()
const id = route.params.id as string
const c = useCollectif()
const { isAdmin: superadmin } = useAdminAuth()
const { del } = useApi()
const d = ref<any>(null)
const evenements = ref<any[] | null>([])
const suivant = ref<string | null>(null)
const chargement = ref(true)
const erreur = ref('')
const cloture = ref(false)
const motifCloture = ref('')
const peutClore = computed(() => superadmin.value || d.value?.mon_role === 'garant')
async function charger() {
  try {
    d.value = (await c.lireDemande(id)).demande
    const j = await c.journalDemande(id)
    evenements.value = j.evenements; suivant.value = j.suivant
  } catch (e) { d.value = null; evenements.value = null }
  chargement.value = false
}
async function suite(avant: string) { const j = await c.journalDemande(id, { avant }); evenements.value = [...(evenements.value || []), ...j.evenements]; suivant.value = j.suivant }
async function aider(role: string, minutes: number) { erreur.value = ''; try { d.value = (await c.soutenir(id, role, minutes || null)).demande; await rechargerFil() } catch (e) { erreur.value = messageErreur(e) } }
async function retirer() { try { d.value = (await c.retirerSoutien(id)).demande; await rechargerFil() } catch (e) { erreur.value = messageErreur(e) } }
async function retirerGarant() { try { d.value = (await del(`/api/demandes/${id}/garant`)).demande; await rechargerFil() } catch (e) { erreur.value = messageErreur(e) } }
async function abonner(oui: boolean) { try { await c.abonnerDemande(id, oui); d.value.abonne = oui } catch (e) { erreur.value = messageErreur(e) } }
async function clore() { try { d.value = (await c.cloreDemande(id, { motif: motifCloture.value })).demande; cloture.value = false; await rechargerFil() } catch (e) { erreur.value = messageErreur(e) } }
async function rechargerFil() { const j = await c.journalDemande(id); evenements.value = j.evenements; suivant.value = j.suivant }
onMounted(charger)
</script>
