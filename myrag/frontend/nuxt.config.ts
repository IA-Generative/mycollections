export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  ssr: false,

  app: {
    head: {
      // Casse de phrase, sans mention bêta : la pastille « MirAI Next Beta » du menu
      // commun porte déjà ce repère (docs/nommage.md du dépôt mirai-apps-menu).
      title: 'Mes collections',
      htmlAttrs: { lang: 'fr', 'data-fr-scheme': 'light' },
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
      ],
      // Le menu commun de la bêta — servi en MÊME ORIGINE par l'Ingress `/_beta`, depuis
      // `IA-Generative/mirai-apps-menu`. `bodyClose` et non `head` : le menu construit son
      // encart dans `document.body`, qui doit exister quand il s'exécute.
      script: [
        { src: '/_beta/menu.js', tagPosition: 'bodyClose' },
      ],
    },
  },

  css: [
    '@gouvfr/dsfr/dist/dsfr.min.css',
    '@gouvfr/dsfr/dist/utility/icons/icons.min.css',
    '~/assets/main.css',
  ],

  runtimeConfig: {
    public: {
      // NB: use ?? (nullish coalescing) not || here — an empty string is a
      // valid value that means "same-origin, relative URLs" behind the prod
      // ingress. With || the empty string would fall through to localhost.
      myragApiUrl: process.env.MYCOLLECTIONS_API_URL ?? process.env.MYRAG_API_URL ?? 'http://localhost:8200',
      appTitle: process.env.APP_TITLE || 'Mes collections (bêta)',
      keycloakUrl: process.env.KEYCLOAK_URL || 'http://host.docker.internal:8082',
      keycloakRealm: process.env.KEYCLOAK_REALM || 'openwebui',
      keycloakClientId: process.env.KEYCLOAK_CLIENT_ID || 'myrag-front',
      authEnabled: process.env.AUTH_ENABLED !== 'false',
      // Mes agents (contrat d'agents MirAI, docs/agents.md) : l'origine du service, cuite au
      // build comme le reste. Vide ⇒ la fonction « Interroger avec un agent » n'existe pas, et
      // la portée `mesagents-agents` n'est pas demandée au SSO (un Keycloak refuse une portée
      // non affectée au client : `invalid_scope` dès la connexion).
      mesagentsBaseUrl: process.env.NUXT_PUBLIC_MESAGENTS_BASE_URL || '',
    },
  },
})
