<template>
  <div>
    <!-- DSFR Header -->
    <header role="banner" class="fr-header">
      <div class="fr-header__body">
        <div class="fr-container">
          <div class="fr-header__body-row">
            <div class="fr-header__brand fr-enlarge-link">
              <div class="fr-header__brand-top">
                <div class="fr-header__logo">
                  <p class="fr-logo">République<br>Française</p>
                </div>
                <div class="fr-header__operator">
                  <img class="fr-responsive-img myrag-operator-logo" src="/favicon.svg" alt="Mes collections" />
                </div>
              </div>
              <div class="fr-header__service">
                <NuxtLink to="/" class="fr-header__service-title">
                  Mes collections
                </NuxtLink>
                <p class="fr-header__service-tagline">Interrogez les documents de votre ministère</p>
              </div>
            </div>
            <div class="fr-header__tools">
              <div class="fr-header__tools-links">
                <ul class="fr-btns-group">
                  <!-- Témoins d'état des deux services : un repère d'exploitation, pas une
                       information pour l'usager — réservés aux administrateurs. -->
                  <li v-if="isAdmin">
                    <span class="myrag-status" :title="myragStatus.title">
                      <span class="myrag-status__dot" :class="myragStatus.class"></span>
                      MyRAG
                    </span>
                  </li>
                  <li v-if="isAdmin">
                    <span class="myrag-status" :title="openragStatus.title">
                      <span class="myrag-status__dot" :class="openragStatus.class"></span>
                      OpenRAG
                    </span>
                  </li>
                  <!-- Le nom et « Se déconnecter » sont portés par le menu commun de la
                       bêta (bulle en haut à droite, sortie GET /deconnexion) : une seule
                       commande de compte à l'écran. -->
                  <li v-if="isAdmin">
                    <NuxtLink to="/admin" class="fr-btn fr-icon-settings-5-line fr-btn--sm">
                      Admin
                    </NuxtLink>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="fr-header__menu">
        <div class="fr-container">
          <nav class="fr-nav" role="navigation" aria-label="Navigation principale">
            <ul class="fr-nav__list">
              <li class="fr-nav__item">
                <NuxtLink to="/" class="fr-nav__link" :aria-current="route.path === '/' ? 'page' : undefined">
                  Accueil
                </NuxtLink>
              </li>
              <li class="fr-nav__item">
                <NuxtLink to="/admin/catalog" class="fr-nav__link" :aria-current="route.path === '/admin/catalog' ? 'page' : undefined">
                  Catalogue
                </NuxtLink>
              </li>
              <li v-if="capacites.demandes" class="fr-nav__item">
                <NuxtLink to="/demandes" class="fr-nav__link" :aria-current="route.path.startsWith('/demandes') ? 'page' : undefined">
                  Demandes de la communauté
                </NuxtLink>
              </li>
              <li class="fr-nav__item">
                <NuxtLink to="/guide" class="fr-nav__link" :aria-current="route.path.startsWith('/guide') ? 'page' : undefined">
                  Soyez acteurs vous-mêmes
                </NuxtLink>
              </li>
              <li v-if="isAdmin" class="fr-nav__item">
                <NuxtLink to="/admin" class="fr-nav__link" :aria-current="route.path.startsWith('/admin') ? 'page' : undefined">
                  Administration
                </NuxtLink>
              </li>
              <!-- Les collections que JE gère : dans un menu, sur toutes les pages — l'accueil,
                   lui, invite à découvrir. -->
              <li class="fr-nav__item myrag-menu-miennes" @keydown.esc="menuOuvert = false">
                <button type="button" class="fr-nav__link myrag-menu-miennes__bouton" :aria-expanded="menuOuvert" aria-controls="menu-miennes"
                        @click="menuOuvert = !menuOuvert">
                  Mes collections
                  <span class="myrag-menu-miennes__compte">{{ miennes.length }}</span>
                  <span class="fr-icon-arrow-down-s-line fr-icon--sm" aria-hidden="true"></span>
                </button>
                <div v-if="menuOuvert" id="menu-miennes" class="myrag-menu-miennes__volet">
                  <p class="myrag-menu-miennes__entete">Celles que je gère</p>
                  <NuxtLink v-for="c in miennes.slice(0, 6)" :key="c.name" :to="`/c/${c.name}`" class="myrag-menu-miennes__ligne" @click="menuOuvert = false">
                    <b>{{ c.titre }}</b>
                    <small>
                      <template v-if="c.categorie_libelle">{{ c.categorie_libelle }} · </template>{{ c.questions }} question{{ c.questions > 1 ? 's' : '' }} en 30 jours<template v-if="c.signalements_ouverts"> · {{ c.signalements_ouverts }} signalement{{ c.signalements_ouverts > 1 ? 's' : '' }} à traiter</template>
                    </small>
                    <span class="fr-badge fr-badge--sm fr-badge--no-icon" :class="c.etat_collab === 'publiee_tous' ? 'fr-badge--success' : 'fr-badge--warning'">{{ libelleEtat(c.etat_collab) }}</span>
                  </NuxtLink>
                  <p v-if="!miennes.length" class="myrag-menu-miennes__vide">Vous ne gérez pas encore de collection.</p>
                  <div class="myrag-menu-miennes__pied">
                    <NuxtLink to="/admin/create" @click="menuOuvert = false">+ Créer une collection</NuxtLink>
                    <NuxtLink v-if="miennes.length" to="/mes-collections" @click="menuOuvert = false">Tout voir et gérer</NuxtLink>
                  </div>
                </div>
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </header>

    <!-- Connection error banner -->
    <div v-if="openragStatus.status === 'down'" class="fr-alert fr-alert--error fr-alert--sm" role="alert">
      <p :title="isAdmin ? `OpenRAG injoignable (${config.public.myragApiUrl})` : undefined">La recherche est momentanément indisponible. Réessayez dans quelques minutes.</p>
    </div>

    <!-- Auth error banner -->
    <div v-if="authError" class="fr-alert fr-alert--warning fr-alert--sm" role="alert">
      <p>Authentification : {{ authError }}</p>
    </div>

    <!-- Auth loading gate -->
    <div v-if="authLoading && config.public.authEnabled" class="fr-container fr-mt-8w" style="text-align:center;">
      <p>Connexion en cours…</p>
      <p class="fr-text--sm fr-mt-2w" :title="config.public.keycloakUrl">Si cette page persiste, le service de connexion ne répond pas : réessayez dans quelques minutes.</p>
    </div>

    <!-- Main content (only when auth is ready) -->
    <main v-else id="main-content" class="fr-container fr-mt-4w fr-mb-8w">
      <slot />
    </main>

    <!-- DSFR Footer -->
    <footer class="fr-footer" role="contentinfo">
      <div class="fr-container">
        <div class="fr-footer__body">
          <div class="fr-footer__brand fr-enlarge-link">
            <NuxtLink to="/" title="Accueil — Mes collections">
              <p class="fr-logo">République<br>Française</p>
            </NuxtLink>
          </div>
          <div class="fr-footer__content">
            <p class="fr-footer__content-desc">
              Mes collections — recherche et analyse documentaire assistée par IA. Version bêta.
            </p>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { libelleEtat } from '~/utils/collectif'

const config = useRuntimeConfig()
const route = useRoute()
const { loading: authLoading, authError, init: initAuth } = useAuth()
const { isAdmin } = useAdminAuth()
// Aucun bouton n'apparaît si le service ne sait pas le faire : l'onglet des demandes
// n'existe que si capacites.json le déclare.
const { capacites, charger: chargerCapacites } = useCapacites()

// Le menu « Mes collections » : celles dont je suis le créateur ou le garant.
const menuOuvert = ref(false)
const miennes = ref<any[]>([])
async function chargerMiennes() {
  try { miennes.value = (await useApi().get('/api/accueil/mes-collections')).collections || [] } catch (e) {}
}
watch(() => route.fullPath, () => { menuOuvert.value = false; chargerMiennes() })

const myragStatus = ref({ status: 'checking', class: 'myrag-status__dot--checking', title: 'Vérification…' })
const openragStatus = ref({ status: 'checking', class: 'myrag-status__dot--checking', title: 'Vérification…' })

async function checkServices() {
  // Check MyRAG
  try {
    const resp = await fetch(`${config.public.myragApiUrl}/health`, { signal: AbortSignal.timeout(3000) })
    if (resp.ok) {
      const data = await resp.json()
      myragStatus.value = {
        status: 'up',
        class: 'myrag-status__dot--up',
        title: `MyRAG ${data.version || ''} — OK`,
      }
    } else {
      myragStatus.value = { status: 'down', class: 'myrag-status__dot--down', title: `MyRAG — HTTP ${resp.status}` }
    }
  } catch {
    myragStatus.value = { status: 'down', class: 'myrag-status__dot--down', title: 'MyRAG — Non accessible' }
  }

  // Check OpenRAG via the MyRAG proxy (browsers can't hit OpenRAG directly
  // because of CORS — the VM only allows same-origin).
  try {
    const resp = await fetch(`${config.public.myragApiUrl}/api/openrag/health`, { signal: AbortSignal.timeout(5000) })
    if (resp.ok) {
      const data = await resp.json()
      if (data.status === 'up') {
        openragStatus.value = { status: 'up', class: 'myrag-status__dot--up', title: `OpenRAG — OK (${data.openrag_url})` }
      } else {
        openragStatus.value = { status: 'down', class: 'myrag-status__dot--down', title: `OpenRAG — ${data.openrag_url} injoignable` }
      }
    } else {
      openragStatus.value = { status: 'down', class: 'myrag-status__dot--down', title: `OpenRAG — HTTP ${resp.status}` }
    }
  } catch {
    openragStatus.value = { status: 'down', class: 'myrag-status__dot--down', title: 'OpenRAG — Non accessible' }
  }
}

onMounted(async () => {
  // Init auth (redirect to Keycloak if not logged in)
  if (config.public.authEnabled) {
    await initAuth()
  }

  chargerCapacites()
  chargerMiennes()
  checkServices()
  setInterval(checkServices, 30000)
})
</script>

<style>
/* Le menu « Mes collections » : poussé à droite de la navigation, volet sous le bouton. */
.myrag-menu-miennes { margin-left: auto; position: relative; }
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
@media (max-width: 62em) { .myrag-menu-miennes { margin-left: 0; } .myrag-menu-miennes__volet { left: 0; right: auto; } }

/* Logo opérateur dans l'en-tête — emplacement DSFR standard (look myvault) */
.myrag-operator-logo {
  width: auto;
  height: 3.5rem;
  border-radius: 6px;
}

.myrag-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: #666;
  padding: 4px 8px;
}

.myrag-status__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.myrag-status__dot--up {
  background: #18753c;
  box-shadow: 0 0 4px #18753c;
}

.myrag-status__dot--down {
  background: #ce0500;
  box-shadow: 0 0 4px #ce0500;
  animation: pulse-red 1.5s infinite;
}

.myrag-status__dot--checking {
  background: #b34000;
  animation: pulse-orange 1s infinite;
}

.myrag-status__dot--unknown {
  background: #666;
}

@keyframes pulse-red {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@keyframes pulse-orange {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
