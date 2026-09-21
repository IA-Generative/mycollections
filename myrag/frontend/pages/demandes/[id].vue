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
          <div v-if="d.satisfaction"><dt>Satisfaction</dt><dd>{{ LIBELLES_SATISFACTION[d.satisfaction] || d.satisfaction }}<span v-if="d.motif_insatisfaction"> — « {{ d.motif_insatisfaction }} »</span></dd></div>
          <div v-if="d.contact_auteur"><dt>Demandeur</dt><dd><a :href="`mailto:${d.contact_auteur}`" class="fr-link">{{ d.contact_auteur }}</a>
            <span class="fr-text--xs" style="color:var(--text-mention-grey)"> — visible du garant et de l'administration seulement</span></dd></div>
          <div v-if="d.motif_cloture || d.doublon_de"><dt>Clôture</dt><dd>{{ d.motif_cloture || '' }}<NuxtLink v-if="d.doublon_de" :to="`/demandes/${d.doublon_de}`" class="fr-link"> doublon d'une autre demande</NuxtLink></dd></div>
        </dl>
        <!-- La boucle de satisfaction : à l'auteur de dire si la collection répond à son besoin. -->
        <section v-if="d.etat === 'a_confirmer'" class="collectif-satisfaction fr-mt-3w" aria-labelledby="satisfaction-titre">
          <h2 id="satisfaction-titre" class="fr-h6 fr-mb-1w">
            {{ d.je_suis_demandeur ? 'La collection répond-elle à votre besoin ?' : 'En attente de la confirmation du demandeur' }}
          </h2>
          <p class="fr-text--sm fr-mb-2w">
            La collection <NuxtLink v-if="d.collection_name" :to="`/c/${d.collection_name}`" class="fr-link">{{ d.collection_name }}</NuxtLink>
            est publiée à tous.
            <template v-if="d.je_suis_demandeur">Essayez-la, puis dites-le ci-dessous.</template>
            Sans réponse {{ echeance(d.confirmation_avant) || 'bientôt' }}, la demande sera considérée comme réalisée.
          </p>
          <template v-if="d.je_suis_demandeur || superadmin">
            <div v-if="!nonSatisfait" class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
              <button class="fr-btn fr-btn--sm" :disabled="envoi" @click="repondre(true)">Oui, elle y répond</button>
              <button class="fr-btn fr-btn--sm fr-btn--secondary" :disabled="envoi" @click="nonSatisfait = true">Pas encore</button>
            </div>
            <div v-else class="fr-input-group">
              <label class="fr-label" for="motif-insatisfaction">Qu'est-ce qui manque encore ?
                <span class="fr-hint-text">Le garant le reprendra : la demande redevient un chantier.</span></label>
              <textarea id="motif-insatisfaction" v-model="motifInsatisfaction" class="fr-input" rows="3"></textarea>
              <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-1w">
                <button class="fr-btn fr-btn--sm" :disabled="envoi || !motifInsatisfaction.trim()" @click="repondre(false)">Envoyer</button>
                <button class="fr-btn fr-btn--sm fr-btn--tertiary" @click="nonSatisfait = false">Annuler</button>
              </div>
            </div>
          </template>
        </section>

        <div v-if="!['realisee', 'close', 'a_confirmer'].includes(d.etat)" class="fr-mt-3w">
          <h2 class="fr-h6">Je peux aider</h2>
          <CollectifJePeuxAider :mon-role="d.mon_role" :garant="d.garant" :je-suis-demandeur="d.je_suis_demandeur" @choisir="aider" />
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
import { LIBELLES_DEMANDE, LIBELLES_SATISFACTION, ceQuiManque, echeance, messageErreur, progression } from '~/utils/collectif'
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
const nonSatisfait = ref(false)
const motifInsatisfaction = ref('')
const envoi = ref(false)
async function repondre(satisfait: boolean) {
  erreur.value = ''
  envoi.value = true
  try {
    d.value = (await c.repondreSatisfaction(id, { satisfait, motif: satisfait ? null : motifInsatisfaction.value.trim() })).demande
    nonSatisfait.value = false
    motifInsatisfaction.value = ''
    await rechargerFil()
  } catch (e) { erreur.value = messageErreur(e) }
  envoi.value = false
}
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
