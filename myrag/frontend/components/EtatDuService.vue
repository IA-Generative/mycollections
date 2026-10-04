<template>
  <!-- La fenêtre « État du service », ouverte depuis le menu personnel ou le bandeau.
       Ce que l'usager peut faire, en clair ; le détail technique pour les administrateurs. -->
  <dialog ref="fenetre" class="myrag-etat" aria-labelledby="myrag-etat-titre" @close="fenetreOuverte = false"
          @click="fermerSurFond">
    <div class="myrag-etat__corps">
      <div class="myrag-etat__haut">
        <h2 id="myrag-etat-titre" class="fr-h5 fr-mb-0">État de Mes collections</h2>
        <button type="button" class="fr-btn--close fr-btn" title="Fermer" @click="fenetreOuverte = false">Fermer</button>
      </div>
      <ul class="myrag-etat__liste">
        <li v-for="f in fonctions" :key="f.nom">
          <b>{{ f.nom }}</b>
          <span class="fr-badge fr-badge--sm" :class="f.classe">{{ f.etat }}</span>
          <small v-if="f.precision">{{ f.precision }}</small>
          <small v-if="isAdmin && f.technique" class="myrag-etat__technique">{{ f.technique }}</small>
        </li>
      </ul>
      <div class="myrag-etat__bas">
        <p class="fr-text--sm fr-mb-0">
          {{ derniereVerification ? `Dernière vérification à ${heureLisible(derniereVerification)}.` : 'Vérification en cours…' }}
        </p>
        <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary" :disabled="verificationEnCours" @click="verifier">
          {{ verificationEnCours ? 'Vérification…' : 'Vérifier maintenant' }}
        </button>
      </div>
      <p class="fr-text--xs fr-mb-0 myrag-etat__note">
        Une panne prévient l'équipe automatiquement. Pour tout autre problème, passez par « Mon avis ».
      </p>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { heureLisible, type Sonde } from '~/utils/etatService'

const { service, recherche, detail, derniereVerification, verificationEnCours, fenetreOuverte, verifier } = useEtatService()
const { isAdmin } = useAdminAuth()
const fenetre = ref<HTMLDialogElement | null>(null)

watch(fenetreOuverte, (ouverte) => {
  const d = fenetre.value
  if (!d) return
  if (ouverte && !d.open) { d.showModal(); verifier() }
  if (!ouverte && d.open) d.close()
})

function fermerSurFond(e: MouseEvent) {
  if (e.target === fenetre.value) fenetreOuverte.value = false
}

function ligne(nom: string, s: Sonde, dependance: Sonde | null, technique: string) {
  const enPanne = s.etat === 'ko' || dependance?.etat === 'ko'
  if (s.etat === 'inconnu' && !enPanne) return { nom, etat: 'Vérification…', classe: 'fr-badge--info', precision: '', technique }
  if (enPanne) {
    const depuis = s.premierEchec ?? dependance?.premierEchec
    const precision = s.etat === 'ko'
      ? `${depuis ? `Depuis ${heureLisible(depuis)}. ` : ''}L'équipe est prévenue.`
      : 'Reprendra avec Mes collections.'
    return { nom, etat: 'Indisponible', classe: 'fr-badge--warning', precision, technique }
  }
  const precision = s.retablieA && derniereVerification.value && derniereVerification.value - s.retablieA < 3600000
    ? `Rétablie à ${heureLisible(s.retablieA)}.`
    : ''
  return { nom, etat: 'Disponible', classe: 'fr-badge--success', precision, technique }
}

const fonctions = computed(() => [
  ligne('Consulter et gérer vos collections', service.value, null, detail.value.service),
  ligne('Poser des questions aux documents', recherche.value, service.value, detail.value.recherche),
  { ...ligne('Ajouter des documents', recherche.value, service.value, ''), precision: '' },
])
</script>

<style scoped>
.myrag-etat {
  border: 0;
  padding: 0;
  width: min(30rem, calc(100vw - 2rem));
  box-shadow: 0 10px 40px rgba(0, 0, 0, .25);
}
.myrag-etat::backdrop { background: rgba(22, 22, 22, .55); }
.myrag-etat__corps { padding: 1.25rem 1.5rem 1.5rem; display: grid; gap: 1rem; }
.myrag-etat__haut { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
.myrag-etat__liste { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--border-default-grey); }
.myrag-etat__liste li {
  display: grid; grid-template-columns: 1fr auto; gap: .15rem 1rem;
  padding: .7rem 0; border-bottom: 1px solid var(--border-default-grey);
}
.myrag-etat__liste b { font-weight: 500; }
.myrag-etat__liste .fr-badge { align-self: center; }
.myrag-etat__liste small { grid-column: 1 / -1; font-size: .8rem; color: var(--text-mention-grey); }
.myrag-etat__technique { font-family: monospace; }
.myrag-etat__bas { display: flex; justify-content: space-between; align-items: center; gap: .5rem 1rem; flex-wrap: wrap; }
.myrag-etat__note { color: var(--text-mention-grey); }
</style>
