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
                  Mes collections <span class="fr-badge fr-badge--sm fr-badge--green-emeraude">Beta</span>
                </NuxtLink>
                <p class="fr-header__service-tagline">Recherche augmentee dans vos collections documentaires</p>
              </div>
            </div>
            <div class="fr-header__tools">
              <div class="fr-header__tools-links">
                <ul class="fr-btns-group">
                  <!-- Service status indicators -->
                  <li>
                    <span class="myrag-status" :title="myragStatus.title">
                      <span class="myrag-status__dot" :class="myragStatus.class"></span>
                      MyRAG
                    </span>
                  </li>
                  <li>
                    <span class="myrag-status" :title="openragStatus.title">
                      <span class="myrag-status__dot" :class="openragStatus.class"></span>
                      OpenRAG
                    </span>
                  </li>
                  <li v-if="user">
                    <span class="myrag-status" :title="getUserName()">
                      <span class="fr-icon-user-line" aria-hidden="true" style="font-size:0.9rem;"></span>
                      {{ getUserName() }}
                    </span>
                  </li>
                  <li>
                    <NuxtLink to="/admin" class="fr-btn fr-icon-settings-5-line fr-btn--sm">
                      Admin
                    </NuxtLink>
                  </li>
                  <li v-if="user">
                    <button class="fr-btn fr-btn--sm fr-icon-logout-box-r-line fr-btn--tertiary-no-outline" @click="logout">
                      Se deconnecter
                    </button>
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
                  Mes collections
                </NuxtLink>
              </li>
              <li class="fr-nav__item">
                <NuxtLink to="/admin" class="fr-nav__link" :aria-current="route.path.startsWith('/admin') ? 'page' : undefined">
                  Administration
                </NuxtLink>
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </header>

    <!-- Connection error banner -->
    <div v-if="openragStatus.status === 'down'" class="fr-alert fr-alert--error fr-alert--sm" role="alert">
      <p>OpenRAG n'est pas accessible ({{ config.public.myragApiUrl }}). Verifiez que le service est demarre.</p>
    </div>

    <!-- Auth error banner -->
    <div v-if="authError" class="fr-alert fr-alert--warning fr-alert--sm" role="alert">
      <p>Authentification : {{ authError }}</p>
    </div>

    <!-- Auth loading gate -->
    <div v-if="authLoading && config.public.authEnabled" class="fr-container fr-mt-8w" style="text-align:center;">
      <p>Connexion a Keycloak en cours...</p>
      <p class="fr-text--sm fr-mt-2w">Si cette page persiste, verifiez que Keycloak est accessible sur {{ config.public.keycloakUrl }}</p>
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
              Mes collections (beta) — recherche et analyse documentaire assistee par IA.
            </p>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
const config = useRuntimeConfig()
const route = useRoute()
const { user, loading: authLoading, authError, init: initAuth, logout, getUserName } = useAuth()

const myragStatus = ref({ status: 'checking', class: 'myrag-status__dot--checking', title: 'Verification...' })
const openragStatus = ref({ status: 'checking', class: 'myrag-status__dot--checking', title: 'Verification...' })

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

  checkServices()
  setInterval(checkServices, 30000)
})
</script>

<style>
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
