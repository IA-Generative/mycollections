<template>
  <div class="fr-container fr-my-4w" style="text-align:center; padding:4rem 0;">
    <p>Déconnexion en cours…</p>
  </div>
</template>

<script setup lang="ts">
// La route que le menu commun de la bêta appelle d'un simple lien
// (`sortie: '/deconnexion'` dans la table APPS de mirai-apps-menu).
//
// `layout: false` est INDISPENSABLE : le layout par défaut appelle `initAuth()` au
// montage et, la session une fois absente, repart en `signinRedirect()` — on se
// RECONNECTERAIT au lieu de se déconnecter, en boucle.
definePageMeta({ layout: false })

const { logout } = useAuth()

onMounted(() => {
  logout().catch(() => {
    window.location.replace('/')
  })
})
</script>
