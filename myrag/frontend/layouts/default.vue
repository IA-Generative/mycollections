<script setup lang="ts">
import { libelleEtat } from '~/utils/collectif'
import { ENTREES_PIED_DE_PAGE } from '~/utils/navigation'

const config = useRuntimeConfig()
const route = useRoute()
const { loading: authLoading, authError, init: initAuth } = useAuth()
const { isAdmin, charger: chargerDroits } = useAdminAuth()
// Aucun bouton n'apparaît si le service ne sait pas le faire : l'onglet des demandes
// n'existe que si capacites.json le déclare.
const { capacites, charger: chargerCapacites } = useCapacites()

// Le menu « Mes collections » : celles dont je suis le créateur ou le garant.
const menuOuvert = ref(false)
const btnVolet = ref<HTMLButtonElement | null>(null)
/** Échap ferme le volet et rend le focus à son bouton. */
function fermerVolet (e: KeyboardEvent) {
  if (!menuOuvert.value) {
    return
  }
  e.stopPropagation() // le volet se ferme seul : le menu mobile qui le porte reste ouvert
  menuOuvert.value = false
  nextTick(() => btnVolet.value?.focus())
}
const menuMobile = ref(false)
const menuPrincipal = ref<HTMLElement | null>(null)
const btnFermerMenu = ref<HTMLButtonElement | null>(null)
function ouvrirMenuMobile () {
  menuMobile.value = true
  nextTick(() => btnFermerMenu.value?.focus())
}
const miennes = ref<any[]>([])
async function chargerMiennes () {
  try {
    miennes.value = (await useApi().get('/api/accueil/mes-collections')).collections || []
  }
  catch {}
}
watch(() => route.fullPath, () => {
  menuOuvert.value = false
  menuMobile.value = false
  chargerMiennes()
})

const { serviceIndisponible, rechercheIndisponible, retabli, fenetreOuverte, demarrer: surveillerEtat } = useEtatService()
// Masqué par l'usager : jusqu'au prochain changement d'état, pas au-delà.
const bandeauMasque = ref(false)
watch([serviceIndisponible, rechercheIndisponible], () => {
  bandeauMasque.value = false
})

/** Le garde `admin-only` laisse passer tant que le compte n'est pas chargé (il ne peut pas
 *  l'attendre : c'est ce gabarit qui le charge). Une fois chargé, on refait le contrôle :
 *  un simple testeur qui tape /admin repart à l'accueil au lieu de voir une page vide. */
function garderLAdministration () {
  const mw = route.meta.middleware
  const protegee = Array.isArray(mw) ? mw.includes('admin-only') : mw === 'admin-only'
  if (protegee && !isAdmin.value) {
    navigateTo('/')
  }
}

onMounted(async () => {
  // Init auth (redirect to Keycloak if not logged in)
  if (config.public.authEnabled) {
    await initAuth()
    await chargerDroits()
    garderLAdministration()
  }

  chargerCapacites()
  chargerMiennes()
  surveillerEtat()
})
</script>

<template>
  <div>
    <!-- DSFR Header -->
    <header
      role="banner"
      class="fr-header"
    >
      <div class="fr-header__body">
        <div class="fr-container">
          <div class="fr-header__body-row">
            <div class="fr-header__brand fr-enlarge-link">
              <div class="fr-header__brand-top">
                <div class="fr-header__logo">
                  <p class="fr-logo">
                    République<br>Française
                  </p>
                </div>
                <div class="fr-header__operator">
                  <img
                    class="fr-responsive-img myrag-operator-logo"
                    src="/favicon.svg"
                    alt="Mes collections"
                  >
                </div>
                <!-- Sur petit écran, le DSFR range la navigation derrière « Menu » (son JavaScript
                     n'est pas chargé : Vue ouvre et ferme la fenêtre). -->
                <div class="fr-header__navbar">
                  <button
                    type="button"
                    class="fr-btn--menu fr-btn"
                    title="Menu"
                    aria-controls="menu-principal"
                    aria-haspopup="menu"
                    :aria-expanded="menuMobile"
                    @click="ouvrirMenuMobile"
                  >
                    Menu
                  </button>
                </div>
              </div>
              <div class="fr-header__service">
                <NuxtLink
                  to="/"
                  class="fr-header__service-title"
                >
                  Mes collections
                </NuxtLink>
                <p class="fr-header__service-tagline">
                  Interrogez les documents de votre ministère
                </p>
              </div>
            </div>
            <!-- Rien à droite de l'en-tête : la barre commune de la bêta y flotte, et porte
                 le compte, « Se déconnecter » et « État du service » (menu personnel). -->
          </div>
        </div>
      </div>
      <div
        id="menu-principal"
        ref="menuPrincipal"
        class="fr-header__menu fr-modal"
        :class="{ 'fr-modal--opened': menuMobile }"
        aria-label="Menu"
        @keydown.esc="menuMobile = false"
        @keydown="menuMobile && piegerLeFocus($event, menuPrincipal)"
      >
        <div class="fr-container">
          <button
            ref="btnFermerMenu"
            type="button"
            class="fr-btn--close fr-btn"
            aria-controls="menu-principal"
            title="Fermer"
            @click="menuMobile = false"
          >
            Fermer
          </button>
          <div class="fr-header__menu-links" />
          <NavigationPrincipale :admin="isAdmin">
            <!-- Les collections que JE gère : un volet du menu, sur toutes les pages. -->
            <template #volet="{ entree, courante }">
              <li
                class="fr-nav__item myrag-menu-miennes"
                @keydown.esc="fermerVolet($event)"
              >
                <button
                  ref="btnVolet"
                  type="button"
                  class="fr-nav__link myrag-menu-miennes__bouton"
                  :aria-expanded="menuOuvert"
                  aria-controls="menu-miennes"
                  :aria-current="courante ? 'page' : undefined"
                  @click="menuOuvert = !menuOuvert"
                >
                  {{ entree.libelle }}
                  <span class="myrag-menu-miennes__compte">{{ miennes.length }}</span>
                  <span
                    class="fr-icon-arrow-down-s-line fr-icon--sm"
                    aria-hidden="true"
                  />
                </button>
                <div
                  v-if="menuOuvert"
                  id="menu-miennes"
                  class="myrag-menu-miennes__volet"
                >
                  <p class="myrag-menu-miennes__entete">
                    Celles que je gère
                  </p>
                  <NuxtLink
                    v-for="c in miennes.slice(0, 6)"
                    :key="c.name"
                    :to="`/c/${c.name}`"
                    class="myrag-menu-miennes__ligne"
                    @click="menuOuvert = false"
                  >
                    <b>{{ c.titre }}</b>
                    <small>
                      <template v-if="c.categorie_libelle">{{ c.categorie_libelle }} · </template>{{ c.questions }} question{{ c.questions > 1 ? 's' : '' }} en 30 jours<template v-if="c.signalements_ouverts"> · {{ c.signalements_ouverts }} signalement{{ c.signalements_ouverts > 1 ? 's' : '' }} à traiter</template>
                    </small>
                    <span
                      class="fr-badge fr-badge--sm fr-badge--no-icon"
                      :class="c.etat_collab === 'publiee_tous' ? 'fr-badge--success' : 'fr-badge--warning'"
                    >{{ libelleEtat(c.etat_collab) }}</span>
                  </NuxtLink>
                  <p
                    v-if="!miennes.length"
                    class="myrag-menu-miennes__vide"
                  >
                    Vous ne gérez pas encore de collection.
                  </p>
                  <div class="myrag-menu-miennes__pied">
                    <NuxtLink
                      to="/admin/create"
                      @click="menuOuvert = false"
                    >
                      + Créer
                    </NuxtLink>
                    <NuxtLink
                      to="/mes-collections"
                      @click="menuOuvert = false"
                    >
                      Tout voir et gérer
                    </NuxtLink>
                    <NuxtLink
                      v-if="capacites.assistants"
                      to="/assistants"
                      @click="menuOuvert = false"
                    >
                      Mes assistants
                    </NuxtLink>
                  </div>
                </div>
              </li>
            </template>
          </NavigationPrincipale>
        </div>
      </div>
    </header>

    <!-- État du service : rien quand tout va bien. En panne, un bandeau qui dit ce qui
         ne marche pas, ce qui marche encore, et qu'il est inutile de le signaler. -->
    <div
      v-if="serviceIndisponible && !bandeauMasque"
      class="fr-notice fr-notice--alert"
      role="status"
    >
      <div class="fr-container">
        <div class="fr-notice__body">
          <p>
            <span class="fr-notice__title">Mes collections ne répond plus pour le moment.</span>
            <span class="fr-notice__desc">Vos collections et vos documents ne sont pas perdus. L'équipe est prévenue : inutile de le signaler.</span>
            <a
              href="#"
              class="fr-notice__link"
              @click.prevent="fenetreOuverte = true"
            >Voir l'état du service</a>
          </p>
          <button
            type="button"
            class="fr-btn--close fr-btn"
            title="Masquer ce message"
            @click="bandeauMasque = true"
          >
            Masquer le message
          </button>
        </div>
      </div>
    </div>
    <div
      v-else-if="rechercheIndisponible && !bandeauMasque"
      class="fr-notice fr-notice--warning"
      role="status"
    >
      <div class="fr-container">
        <div class="fr-notice__body">
          <p>
            <span class="fr-notice__title">La recherche dans les documents est momentanément indisponible.</span>
            <span class="fr-notice__desc">Vos collections, leurs fiches et leurs réglages restent consultables. L'équipe est prévenue : inutile de le signaler.</span>
            <a
              href="#"
              class="fr-notice__link"
              @click.prevent="fenetreOuverte = true"
            >Voir l'état du service</a>
          </p>
          <button
            type="button"
            class="fr-btn--close fr-btn"
            title="Masquer ce message"
            @click="bandeauMasque = true"
          >
            Masquer le message
          </button>
        </div>
      </div>
    </div>
    <div
      v-if="retabli"
      class="fr-container fr-mt-2w"
    >
      <div
        class="fr-alert fr-alert--success fr-alert--sm"
        role="status"
      >
        <p>Le service fonctionne de nouveau.</p>
      </div>
    </div>
    <EtatDuService />

    <!-- Auth error banner -->
    <div
      v-if="authError"
      class="fr-alert fr-alert--warning fr-alert--sm"
      role="alert"
    >
      <p>Authentification : {{ authError }}</p>
    </div>

    <!-- Auth loading gate -->
    <div
      v-if="authLoading && config.public.authEnabled"
      class="fr-container fr-mt-8w"
      style="text-align:center;"
    >
      <p>Connexion en cours…</p>
      <p
        class="fr-text--sm fr-mt-2w"
        :title="config.public.keycloakUrl"
      >
        Si cette page persiste, le service de connexion ne répond pas : réessayez dans quelques minutes.
      </p>
    </div>

    <!-- Main content (only when auth is ready) -->
    <main
      v-else
      id="main-content"
      class="fr-container fr-mt-4w fr-mb-8w"
    >
      <slot />
    </main>

    <!-- DSFR Footer -->
    <footer
      class="fr-footer"
      role="contentinfo"
    >
      <div class="fr-container">
        <div class="fr-footer__body">
          <div class="fr-footer__brand fr-enlarge-link">
            <NuxtLink
              to="/"
              title="Accueil — Mes collections"
            >
              <p class="fr-logo">
                République<br>Française
              </p>
            </NuxtLink>
          </div>
          <div class="fr-footer__content">
            <p class="fr-footer__content-desc">
              Mes collections — recherche et analyse documentaire assistée par IA. Version bêta.
            </p>
            <ul class="fr-footer__content-list">
              <li
                v-for="e in ENTREES_PIED_DE_PAGE"
                :key="e.vers"
                class="fr-footer__content-item"
              >
                <NuxtLink
                  :to="e.vers"
                  class="fr-footer__content-link"
                >
                  {{ e.libelle }}
                </NuxtLink>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<style>
/* Sur tablette et téléphone, la barre commune de la bêta (position fixe, en haut à droite)
   tombait sur le bouton « Menu » du DSFR, qui occupe le même coin : le toucher ouvrait le
   compte, jamais le menu. On lui laisse une bande au-dessus de l'en-tête. */
@media (max-width: 991.98px) {
  .fr-header { padding-top: 2.75rem; }
  .fr-header__menu.fr-modal--opened { padding-top: 2.75rem; }
}
/* Le menu « Mes collections » : troisième entrée de la navigation, volet sous le bouton. */
.myrag-menu-miennes { position: relative; }
.myrag-menu-miennes__bouton { display: inline-flex; align-items: center; gap: .35rem; color: var(--text-action-high-blue-france); }
.myrag-menu-miennes__compte {
  min-width: 1.5em; text-align: center; font-size: .75rem; font-weight: 700; border-radius: 1em; padding: 0 .4em;
  background: var(--background-action-high-blue-france); color: var(--text-inverted-blue-france); font-variant-numeric: tabular-nums;
}
.myrag-menu-miennes__volet {
  position: absolute; right: 0; top: 100%; z-index: 750; width: min(24rem, calc(100vw - 2rem));
  background: var(--background-overlap-grey); border: 1px solid var(--border-default-grey); box-shadow: 0 6px 18px rgba(0, 0, 18, .16);
}
.myrag-menu-miennes__entete { margin: 0; padding: .75rem 1rem .4rem; font-size: .72rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--text-mention-grey); }
.myrag-menu-miennes__ligne {
  display: grid; grid-template-columns: 1fr auto; gap: .1rem .75rem; padding: .6rem 1rem; font-size: .92rem;
  border-top: 1px solid var(--border-default-grey); background-image: none; color: var(--text-default-grey);
}
.myrag-menu-miennes__ligne:hover { background: var(--background-alt-grey); }
.myrag-menu-miennes__ligne b { font-weight: 500; }
.myrag-menu-miennes__ligne small { grid-column: 1; font-size: .78rem; color: var(--text-mention-grey); }
.myrag-menu-miennes__ligne .fr-badge { grid-column: 2; grid-row: 1 / span 2; align-self: center; }
.myrag-menu-miennes__vide { margin: 0; padding: .25rem 1rem .9rem; font-size: .9rem; color: var(--text-mention-grey); }
.myrag-menu-miennes__pied { display: flex; flex-wrap: wrap; gap: .25rem 1rem; padding: .6rem 1rem .75rem; border-top: 1px solid var(--border-default-grey); background: var(--background-alt-grey); }
.myrag-menu-miennes__pied a { font-size: .85rem; font-weight: 500; color: var(--text-action-high-blue-france); }
.myrag-menu-miennes__volet { left: 0; right: auto; }
@media (max-width: 62em) { .myrag-menu-miennes__volet { position: static; width: 100%; } }

/* Logo opérateur dans l'en-tête — emplacement DSFR standard (look myvault) */
.myrag-operator-logo {
  width: auto;
  height: 3.5rem;
  border-radius: 6px;
}
</style>
