<script setup lang="ts">
import type { Collection } from '~/types/collection'
import type { ConnecteurDeclare, FicheAssistant, Regime } from '~/utils/assistants'
import { choixSource, connecteursAjoutables, etiquetteSource, REGIMES, resumeSources, sourceDepuisChoix } from '~/utils/assistants'
import { titreDe } from '~/utils/catalogue'

/** Les sources d'un assistant (B1) : quelles collections, quand les interroger, dans quel ordre. */
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
const id = useRoute().params.id as string
useHead({ title: `Sources — ${id} — Mes collections` })

const { get } = useApi()
const { enregistrer, connecteurs: listerConnecteurs } = useAssistants()
const collections = ref<Collection[]>([])
const connecteurs = ref<ConnecteurDeclare[]>([])
const message = ref('')
const erreur = ref('')
const envoi = ref(false)
onMounted(async () => {
  try {
    collections.value = (await get('/api/collections')).collections || []
  }
  catch {}
  try {
    connecteurs.value = await listerConnecteurs()
  }
  catch {}
})
function titreSource (sid: string) {
  const k = connecteurs.value.find(x => x.id === sid)
  if (k) {
    return k.titre
  }
  const c = collections.value.find(x => x.name === sid)
  return c ? titreDe(c) : sid
}
function connecteursDe (fiche: FicheAssistant) {
  return connecteursAjoutables(connecteurs.value, fiche.sources)
}
function ajouter (fiche: FicheAssistant, cible: HTMLSelectElement) {
  const s = sourceDepuisChoix(cible.value)
  if (s) {
    fiche.sources.push(s)
  }
  cible.value = ''
}
function ajoutables (fiche: FicheAssistant) {
  return collections.value
    .filter(c => c.mes_droits?.ecrire && !c.orphan && !c.archived_at && !fiche.sources.some(s => s.id === c.name))
}

async function sauver (fiche: FicheAssistant, recharger: () => Promise<void>) {
  envoi.value = true
  erreur.value = ''
  message.value = ''
  try {
    await enregistrer({ ...fiche, sources: fiche.sources.map((s, i) => ({ ...s, rang: i + 1 })) })
    message.value = 'Sources enregistrées dans le brouillon. Publiez pour en faire une version.'
    await recharger()
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
  finally {
    envoi.value = false
  }
}
function deplacer (fiche: FicheAssistant, i: number, sens: -1 | 1) {
  const j = i + sens
  if (j < 0 || j >= fiche.sources.length) {
    return
  }
  const s = fiche.sources
  ;[s[i], s[j]] = [s[j]!, s[i]!]
}
</script>

<template>
  <AssistantsCadre
    :id="id"
    rubrique="Sources"
  >
    <template #default="{ donnees, recharger }">
      <p class="fr-text--sm">
        {{ resumeSources(donnees.fiche.sources.length, donnees.sources_masquees) }}.
        <template v-if="donnees.sources_masquees">
          Celles que vous ne pouvez pas lire ne sont pas affichées.
        </template>
      </p>
      <div class="fr-table fr-table--no-caption sources-table">
        <table>
          <caption>Sources de l'assistant</caption>
          <thead>
            <tr>
              <th scope="col">
                Ordre
              </th>
              <th scope="col">
                Source
              </th>
              <th scope="col">
                Quand l'interroger
              </th>
              <th
                v-if="donnees.mes_droits.ecrire"
                scope="col"
              >
                <span class="fr-sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(s, i) in donnees.fiche.sources"
              :key="s.id"
            >
              <td>{{ i + 1 }}</td>
              <td>
                <template v-if="s.type === 'connecteur'">
                  {{ titreSource(s.id) }}
                  <p class="fr-badge fr-badge--sm fr-badge--info fr-badge--no-icon fr-ml-1w">
                    {{ etiquetteSource(s.type) }}
                  </p>
                </template>
                <NuxtLink
                  v-else
                  :to="`/c/${s.id}`"
                  class="fr-link"
                >
                  {{ titreSource(s.id) }}
                </NuxtLink>
                <br><code class="fr-text--xs">{{ s.id }}</code>
              </td>
              <td>
                <select
                  v-if="donnees.mes_droits.ecrire"
                  v-model="s.regime"
                  class="fr-select"
                  :aria-label="`Quand interroger ${titreSource(s.id)}`"
                >
                  <option
                    v-for="r in REGIMES"
                    :key="r.cle"
                    :value="r.cle as Regime"
                  >
                    {{ r.libelle }}
                  </option>
                </select>
                <template v-else>
                  {{ REGIMES.find(r => r.cle === s.regime)?.libelle }}
                </template>
              </td>
              <td
                v-if="donnees.mes_droits.ecrire"
                class="sources-actions"
              >
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-arrow-up-line fr-btn--icon-only"
                  :disabled="i === 0"
                  :title="`Monter ${titreSource(s.id)}`"
                  @click="deplacer(donnees.fiche, i, -1)"
                >
                  Monter
                </button>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-arrow-down-line fr-btn--icon-only"
                  :disabled="i === donnees.fiche.sources.length - 1"
                  :title="`Descendre ${titreSource(s.id)}`"
                  @click="deplacer(donnees.fiche, i, 1)"
                >
                  Descendre
                </button>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-delete-line fr-btn--icon-only"
                  :disabled="donnees.fiche.sources.length === 1"
                  :title="`Retirer ${titreSource(s.id)}`"
                  @click="donnees.fiche.sources.splice(i, 1)"
                >
                  Retirer
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <template v-if="donnees.mes_droits.ecrire">
        <div
          v-if="ajoutables(donnees.fiche).length || connecteursDe(donnees.fiche).length"
          class="fr-select-group sources-ajout"
        >
          <label
            class="fr-label"
            for="ajout"
          >Ajouter une source</label>
          <select
            id="ajout"
            class="fr-select"
            @change="ajouter(donnees.fiche, $event.target as HTMLSelectElement)"
          >
            <option
              value=""
              selected
              disabled
            >
              Choisir une collection que vous gérez ou un référentiel
            </option>
            <optgroup
              v-if="ajoutables(donnees.fiche).length"
              label="Collections que vous gérez"
            >
              <option
                v-for="c in ajoutables(donnees.fiche)"
                :key="c.name"
                :value="choixSource('collection', c.name)"
              >
                {{ titreDe(c) }}
              </option>
            </optgroup>
            <optgroup
              v-if="connecteursDe(donnees.fiche).length"
              label="Référentiels"
            >
              <option
                v-for="k in connecteursDe(donnees.fiche)"
                :key="k.id"
                :value="choixSource('connecteur', k.id)"
                :title="k.description"
              >
                {{ k.titre }}
              </option>
            </optgroup>
          </select>
          <p
            v-for="k in connecteursDe(donnees.fiche).filter(x => x.description)"
            :key="k.id"
            class="fr-hint-text fr-mt-1w"
          >
            {{ k.titre }} : {{ k.description }}
          </p>
        </div>
        <div
          v-if="message"
          class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w"
          role="status"
        >
          <p>{{ message }}</p>
        </div>
        <div
          v-if="erreur"
          class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
          role="alert"
        >
          <p>{{ erreur }}</p>
        </div>
        <button
          type="button"
          class="fr-btn"
          :disabled="envoi"
          @click="sauver(donnees.fiche, recharger)"
        >
          {{ envoi ? 'Enregistrement…' : 'Enregistrer les sources' }}
        </button>
      </template>
    </template>
  </AssistantsCadre>
</template>

<style scoped>
.sources-table table { width: 100%; }
.sources-actions { white-space: nowrap; }
.sources-ajout { max-width: 28rem; }
</style>
