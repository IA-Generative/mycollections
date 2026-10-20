<script setup lang="ts">
import type { Consigne, FicheAssistant, ResultatAssistant } from '~/utils/assistants'
import {
  BORNES_CONSIGNE,
  consignePourEnvoi,
  consigneVide,
  deplacer,
  exemplesDepuisTexte,
  libelleQuand,
  ordonnerEtapes,
  QUAND_TOUJOURS,
  resumeConsigne,
  validerConsigne,
} from '~/utils/assistants'

/**
 * Les consignes d'un assistant (B2) : pour un type de question, où chercher et comment répondre.
 * On les ajoute, modifie, retire et réordonne ; « Enregistrer » envoie la fiche entière
 * (`PUT /api/assistants/{id}`, comme les sources). « Tester » pose une question à l'assistant et
 * montre le plan suivi, la réponse et ses passages.
 */
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
const id = useRoute().params.id as string
useHead({ title: `Consignes — ${id} — Mes collections` })

const { enregistrer, executer } = useAssistants()
const { titre: titreSource } = useTitresSources()

const message = ref('')
const erreur = ref('')
const envoi = ref(false)
/** Des changements faits ici qui ne sont pas encore enregistrés. */
const modifie = ref(false)

// ─── Le formulaire d'une consigne ────────────────────────────────────────────────────────────

interface Edition {
  /** Rang de la consigne modifiée ; null pour une nouvelle. */
  index: number | null
  consigne: Consigne
  pourToute: boolean
  exemplesTexte: string
  tente: boolean
}
const edition = ref<Edition | null>(null)
const champQuand = ref<HTMLElement | null>(null)
let retourFocus: HTMLElement | null = null

function ouvrir (fiche: FicheAssistant, index: number | null) {
  retourFocus = document.activeElement as HTMLElement | null
  const base = index === null ? consigneVide(fiche.consignes) : fiche.consignes[index]!
  const c: Consigne = { ...base, exemples: [...base.exemples], chercher: base.chercher.map(e => ({ ...e })) }
  edition.value = {
    index,
    consigne: c,
    pourToute: c.quand.trim() === QUAND_TOUJOURS,
    exemplesTexte: c.exemples.join('\n'),
    tente: false,
  }
  if (c.quand.trim() === QUAND_TOUJOURS) {
    c.quand = ''
  }
  message.value = ''
  nextTick(() => (champQuand.value || document.getElementById('quand-toujours'))?.focus())
}

function fermer () {
  edition.value = null
  nextTick(() => retourFocus?.focus())
}

/** La consigne telle que le formulaire la décrit. */
function consigneSaisie (e: Edition): Consigne {
  return { ...e.consigne, quand: e.pourToute ? QUAND_TOUJOURS : e.consigne.quand, exemples: exemplesDepuisTexte(e.exemplesTexte) }
}
function autres (fiche: FicheAssistant, e: Edition): Consigne[] {
  return fiche.consignes.filter((_, i) => i !== e.index)
}
function erreursDe (fiche: FicheAssistant, e: Edition): Record<string, string> {
  return validerConsigne(consigneSaisie(e), fiche.sources.map(s => s.id), autres(fiche, e))
}
function toujoursPris (fiche: FicheAssistant, e: Edition): boolean {
  return autres(fiche, e).some(c => c.quand.trim() === QUAND_TOUJOURS)
}

function valider (fiche: FicheAssistant) {
  const e = edition.value
  if (!e) {
    return
  }
  e.tente = true
  if (Object.keys(erreursDe(fiche, e)).length) {
    return
  }
  const c = consignePourEnvoi(consigneSaisie(e))
  if (e.index === null) {
    fiche.consignes.push(c)
  }
  else {
    fiche.consignes.splice(e.index, 1, c)
  }
  modifie.value = true
  message.value = 'Consigne prête. Enregistrez pour la garder.'
  fermer()
}

function ajouterEtape (fiche: FicheAssistant, e: Edition) {
  const deja = new Set(e.consigne.chercher.map(x => x.source))
  const libre = fiche.sources.find(s => !deja.has(s.id)) || fiche.sources[0]
  e.consigne.chercher.push({ source: libre?.id || '' })
}
function deplacerEtape (e: Edition, i: number, sens: -1 | 1) {
  e.consigne.chercher = ordonnerEtapes(e.consigne.chercher, i, i + sens)
}
function retirerEtape (e: Edition, i: number) {
  // ordonnerEtapes sans déplacement : la nouvelle première étape perd son « avec ».
  e.consigne.chercher = ordonnerEtapes(e.consigne.chercher.filter((_, j) => j !== i), 0, 0)
}

// ─── La liste ────────────────────────────────────────────────────────────────────────────────

function monter (fiche: FicheAssistant, i: number, sens: -1 | 1) {
  fiche.consignes = deplacer(fiche.consignes, i, sens)
  modifie.value = true
}
function retirer (fiche: FicheAssistant, i: number) {
  fiche.consignes.splice(i, 1)
  modifie.value = true
  message.value = 'Consigne retirée. Enregistrez pour confirmer.'
}

async function sauver (fiche: FicheAssistant, recharger: () => Promise<void>) {
  envoi.value = true
  erreur.value = ''
  message.value = ''
  try {
    await enregistrer({ ...fiche, consignes: fiche.consignes.map(consignePourEnvoi) })
    modifie.value = false
    message.value = 'Consignes enregistrées dans le brouillon. Publiez pour en faire une version.'
    await recharger()
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
  finally {
    envoi.value = false
  }
}

// ─── Tester ──────────────────────────────────────────────────────────────────────────────────

const question = ref('')
const essai = ref(false)
const erreurEssai = ref('')
const resultat = ref<ResultatAssistant | null>(null)
const doublure = ref(false)
const zoneEssai = ref<HTMLElement | null>(null)

async function tester (q?: string) {
  if (q !== undefined) {
    question.value = q
    zoneEssai.value?.scrollIntoView({ block: 'start' })
  }
  const texte = question.value.trim()
  if (!texte || essai.value) {
    return
  }
  essai.value = true
  erreurEssai.value = ''
  resultat.value = null
  doublure.value = false
  try {
    const r = await executer(id, texte.slice(0, 1000))
    resultat.value = r.resultat
    doublure.value = r.doublure
  }
  catch (e) {
    erreurEssai.value = messageErreurMoteur(e)
  }
  finally {
    essai.value = false
  }
}
</script>

<template>
  <AssistantsCadre
    :id="id"
    rubrique="Consignes"
  >
    <template #default="{ donnees, recharger }">
      <p class="fr-text--sm">
        Une consigne dit à l'assistant, pour un type de question, où chercher et comment répondre.
        Sans consigne, il choisit ses sources d'après la question et ce que vous avez réglé dans
        « Sources ».
      </p>

      <p
        v-if="!donnees.fiche.consignes.length"
        class="fr-text--sm consignes-vide"
      >
        Aucune consigne pour l'instant.
      </p>
      <ol
        v-else
        class="fr-raw-list consignes-liste"
      >
        <li
          v-for="(c, i) in (donnees.fiche as FicheAssistant).consignes"
          :key="c.id"
          class="consignes-carte"
        >
          <h2 class="fr-h6 fr-mb-1v">
            {{ libelleQuand(c.quand) }}
          </h2>
          <p class="fr-text--sm fr-mb-1w consignes-discret">
            {{ resumeConsigne(c, titreSource) }}
          </p>
          <ul class="fr-btns-group fr-btns-group--inline-sm fr-btns-group--sm fr-btns-group--icon-left">
            <li>
              <button
                type="button"
                class="fr-btn fr-btn--secondary fr-icon-play-line"
                :disabled="essai"
                :title="c.exemples.length ? `Tester avec « ${c.exemples[0]} »` : 'Tester une question'"
                @click="c.exemples.length ? tester(c.exemples[0]) : zoneEssai?.scrollIntoView({ block: 'start' })"
              >
                Tester
              </button>
            </li>
            <template v-if="donnees.mes_droits.ecrire">
              <li>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary fr-icon-edit-line"
                  :disabled="!!edition"
                  @click="ouvrir(donnees.fiche, i)"
                >
                  Modifier
                </button>
              </li>
              <li>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-icon-arrow-up-line"
                  :disabled="i === 0 || !!edition"
                  @click="monter(donnees.fiche, i, -1)"
                >
                  Monter
                </button>
              </li>
              <li>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-icon-arrow-down-line"
                  :disabled="i === donnees.fiche.consignes.length - 1 || !!edition"
                  @click="monter(donnees.fiche, i, 1)"
                >
                  Descendre
                </button>
              </li>
              <li>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-icon-delete-line"
                  :disabled="!!edition"
                  @click="retirer(donnees.fiche, i)"
                >
                  Retirer
                </button>
              </li>
            </template>
          </ul>
        </li>
      </ol>

      <!-- Le formulaire d'une consigne, en mots simples. Échap l'annule. -->
      <form
        v-if="edition && donnees.mes_droits.ecrire"
        class="consignes-formulaire fr-mb-3w"
        :aria-label="edition.index === null ? 'Nouvelle consigne' : 'Modifier la consigne'"
        novalidate
        @submit.prevent="valider(donnees.fiche)"
        @keydown.esc.prevent="fermer"
      >
        <h2 class="fr-h5">
          {{ edition.index === null ? 'Nouvelle consigne' : 'Modifier la consigne' }}
        </h2>

        <fieldset
          class="fr-fieldset"
          :class="{ 'fr-fieldset--error': edition.tente && erreursDe(donnees.fiche, edition).quand }"
          aria-labelledby="legende-quand"
        >
          <legend
            id="legende-quand"
            class="fr-fieldset__legend fr-text--regular"
          >
            Quand
            <span class="fr-hint-text">À quelles questions la consigne s'applique.</span>
          </legend>
          <div class="fr-fieldset__element">
            <div class="fr-radio-group">
              <input
                id="quand-phrase"
                v-model="edition.pourToute"
                type="radio"
                name="quand"
                :value="false"
              >
              <label
                class="fr-label"
                for="quand-phrase"
              >Quand la question porte sur…</label>
            </div>
          </div>
          <div class="fr-fieldset__element">
            <div class="fr-radio-group">
              <input
                id="quand-toujours"
                v-model="edition.pourToute"
                type="radio"
                name="quand"
                :value="true"
                :disabled="toujoursPris(donnees.fiche, edition)"
              >
              <label
                class="fr-label"
                for="quand-toujours"
              >Pour toute question
                <span
                  v-if="toujoursPris(donnees.fiche, edition)"
                  class="fr-hint-text"
                >Une autre consigne vaut déjà pour toute question.</span>
              </label>
            </div>
          </div>
          <div
            v-if="!edition.pourToute"
            class="fr-fieldset__element"
          >
            <div class="fr-input-group">
              <label
                class="fr-label"
                for="quand"
              >Décrivez ces questions en une phrase</label>
              <textarea
                id="quand"
                ref="champQuand"
                v-model="edition.consigne.quand"
                class="fr-input"
                rows="2"
                :maxlength="BORNES_CONSIGNE.quand"
                placeholder="Ex. : la personne vient d'un pays lié à la France par un accord"
              />
            </div>
          </div>
          <p
            v-if="edition.tente && erreursDe(donnees.fiche, edition).quand"
            class="fr-error-text fr-fieldset__element"
          >
            {{ erreursDe(donnees.fiche, edition).quand }}
          </p>
        </fieldset>

        <div
          class="fr-input-group"
          :class="{ 'fr-input-group--error': edition.tente && erreursDe(donnees.fiche, edition).exemples }"
        >
          <label
            class="fr-label"
            for="exemples"
          >Exemples de questions
            <span class="fr-hint-text">Une par ligne, {{ BORNES_CONSIGNE.exemples }} au plus : elles aident l'assistant à reconnaître les questions concernées.</span>
          </label>
          <textarea
            id="exemples"
            v-model="edition.exemplesTexte"
            class="fr-input"
            rows="3"
          />
          <p
            v-if="edition.tente && erreursDe(donnees.fiche, edition).exemples"
            class="fr-error-text"
          >
            {{ erreursDe(donnees.fiche, edition).exemples }}
          </p>
        </div>

        <fieldset
          class="fr-fieldset"
          :class="{ 'fr-fieldset--error': edition.tente && erreursDe(donnees.fiche, edition).chercher }"
          aria-labelledby="legende-chercher"
        >
          <legend
            id="legende-chercher"
            class="fr-fieldset__legend fr-text--regular"
          >
            Chercher
            <span class="fr-hint-text">Les sources à interroger, dans l'ordre. Sans étape, l'assistant choisit lui-même.</span>
          </legend>
          <div
            v-for="(etape, i) in edition.consigne.chercher"
            :key="i"
            class="fr-fieldset__element consignes-etape"
          >
            <div class="fr-select-group fr-mb-1w">
              <label
                class="fr-label"
                :for="`etape-${i}`"
              >Étape {{ i + 1 }} : chercher dans</label>
              <select
                :id="`etape-${i}`"
                v-model="etape.source"
                class="fr-select"
              >
                <option
                  v-for="s in donnees.fiche.sources"
                  :key="s.id"
                  :value="s.id"
                >
                  {{ titreSource(s.id) }}
                </option>
              </select>
            </div>
            <div
              v-if="i > 0"
              class="fr-input-group fr-mb-1w"
            >
              <label
                class="fr-label"
                :for="`avec-${i}`"
              >À partir de ce qu'a trouvé l'étape précédente (facultatif)
                <span class="fr-hint-text">Nommez ce qui est transmis, en minuscules sans espace : ex. article_trouve.</span>
              </label>
              <input
                :id="`avec-${i}`"
                v-model="etape.avec"
                class="fr-input"
                maxlength="41"
              >
            </div>
            <ul class="fr-btns-group fr-btns-group--inline-sm fr-btns-group--sm fr-btns-group--icon-left">
              <li>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-icon-arrow-up-line"
                  :disabled="i === 0"
                  @click="deplacerEtape(edition, i, -1)"
                >
                  Avant
                </button>
              </li>
              <li>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-icon-arrow-down-line"
                  :disabled="i === edition.consigne.chercher.length - 1"
                  @click="deplacerEtape(edition, i, 1)"
                >
                  Après
                </button>
              </li>
              <li>
                <button
                  type="button"
                  class="fr-btn fr-btn--tertiary-no-outline fr-icon-delete-line"
                  @click="retirerEtape(edition, i)"
                >
                  Retirer l'étape
                </button>
              </li>
            </ul>
          </div>
          <div class="fr-fieldset__element">
            <button
              type="button"
              class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-add-line fr-btn--icon-left"
              @click="ajouterEtape(donnees.fiche, edition)"
            >
              Ajouter une étape
            </button>
          </div>
          <p
            v-if="edition.tente && erreursDe(donnees.fiche, edition).chercher"
            class="fr-error-text fr-fieldset__element"
          >
            {{ erreursDe(donnees.fiche, edition).chercher }}
          </p>
        </fieldset>

        <div
          class="fr-input-group"
          :class="{ 'fr-input-group--error': edition.tente && erreursDe(donnees.fiche, edition).repondre }"
        >
          <label
            class="fr-label"
            for="repondre"
          >Répondre (facultatif)
            <span class="fr-hint-text">Comment rédiger la réponse : ton, longueur, ce qu'il faut citer.</span>
          </label>
          <textarea
            id="repondre"
            v-model="edition.consigne.repondre"
            class="fr-input"
            rows="3"
            :maxlength="BORNES_CONSIGNE.repondre"
            placeholder="Ex. : citez l'article de l'accord, puis les pièces à fournir."
          />
          <p
            v-if="edition.tente && erreursDe(donnees.fiche, edition).repondre"
            class="fr-error-text"
          >
            {{ erreursDe(donnees.fiche, edition).repondre }}
          </p>
        </div>

        <ul class="fr-btns-group fr-btns-group--inline-sm fr-btns-group--icon-left">
          <li>
            <button
              type="submit"
              class="fr-btn fr-icon-check-line"
            >
              Valider la consigne
            </button>
          </li>
          <li>
            <button
              type="button"
              class="fr-btn fr-btn--secondary fr-icon-close-line"
              @click="fermer"
            >
              Annuler
            </button>
          </li>
        </ul>
      </form>

      <template v-if="donnees.mes_droits.ecrire">
        <button
          v-if="donnees.fiche.consignes.length < BORNES_CONSIGNE.consignes"
          type="button"
          :disabled="!!edition"
          class="fr-btn fr-btn--secondary fr-icon-add-line fr-btn--icon-left fr-mb-2w"
          @click="ouvrir(donnees.fiche, null)"
        >
          Ajouter une consigne
        </button>
        <div
          v-if="message"
          class="fr-alert fr-alert--info fr-alert--sm fr-mb-2w"
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
        <div>
          <button
            type="button"
            class="fr-btn"
            :disabled="envoi || !!edition || !modifie"
            @click="sauver(donnees.fiche, recharger)"
          >
            {{ envoi ? 'Enregistrement…' : 'Enregistrer les consignes' }}
          </button>
        </div>
      </template>

      <section
        ref="zoneEssai"
        class="fr-mt-5w"
        aria-labelledby="titre-essai"
      >
        <h2
          id="titre-essai"
          class="fr-h5"
        >
          Tester une question
        </h2>
        <p
          v-if="modifie"
          class="fr-text--sm consignes-discret"
        >
          Des changements ne sont pas enregistrés : le test ne les prend pas en compte.
        </p>
        <form
          class="consignes-essai"
          @submit.prevent="tester()"
        >
          <div class="fr-input-group fr-mb-0">
            <label
              class="fr-label"
              for="question-essai"
            >Question</label>
            <input
              id="question-essai"
              v-model="question"
              class="fr-input"
              maxlength="1000"
              placeholder="Posez une question comme le ferait un collègue"
            >
          </div>
          <button
            type="submit"
            class="fr-btn fr-icon-play-line fr-btn--icon-left"
            :disabled="essai || !question.trim()"
          >
            {{ essai ? 'Recherche…' : 'Tester' }}
          </button>
        </form>
        <div
          aria-live="polite"
          class="fr-mt-2w"
        >
          <div
            v-if="erreurEssai"
            class="fr-alert fr-alert--error fr-alert--sm"
            role="alert"
          >
            <p>{{ erreurEssai }}</p>
          </div>
          <AssistantsEncadreDoublure v-if="resultat && doublure" />
          <AssistantsResultat
            v-if="resultat"
            :resultat="resultat"
            :fiche="donnees.fiche"
            :titre="titreSource"
          />
        </div>
      </section>
    </template>
  </AssistantsCadre>
</template>

<style scoped>
.consignes-discret { color: var(--text-mention-grey); }
.consignes-vide { color: var(--text-mention-grey); }
.consignes-liste { list-style: none; margin: 0 0 1.5rem; padding: 0; }
.consignes-carte { padding: 1rem 1rem .25rem; margin-bottom: 1rem; border: 1px solid var(--border-default-grey); }
.consignes-formulaire { padding: 1.5rem; border: 1px solid var(--border-default-grey); background: var(--background-alt-grey); }
.consignes-etape { padding: .75rem; margin-bottom: .75rem; border-left: 3px solid var(--border-default-blue-france); background: var(--background-default-grey); }
.consignes-essai { display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end; }
.consignes-essai .fr-input-group { flex: 1 1 18rem; }
</style>
