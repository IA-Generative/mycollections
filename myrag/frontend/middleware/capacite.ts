/**
 * Une page sous drapeau : `definePageMeta({ middleware: 'capacite', capacite: 'assistants' })`.
 * Drapeau à faux, la page n'existe pas — 404 en français (error.vue), comme une adresse inconnue,
 * et comme la route de l'API derrière elle.
 */
import type { Drapeau } from '~/utils/capacites'

declare module '#app' {
  interface PageMeta {
    capacite?: Drapeau
  }
}

export default defineNuxtRouteMiddleware(async (to) => {
  const nom = to.meta.capacite
  if (!nom) {
    return
  }
  const { capacites, charger } = useCapacites()
  await charger()
  if (capacites.value[nom] !== true) {
    return abortNavigation(createError({ statusCode: 404, statusMessage: 'Page introuvable' }))
  }
})
