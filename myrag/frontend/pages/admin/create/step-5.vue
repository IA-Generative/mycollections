<script setup lang="ts">
import { messageErreur } from '~/utils/collectif'
import { libelleSensibilite } from '~/utils/libelles'
import { CONFIRMATION_DROITS_RESANA, partageResanaPret } from '~/utils/resana'
import { lienEtape, resumeCreation } from '~/utils/wizard'

/**
 * Étape 5, la dernière : un récapitulatif (ce qui a été fait, ce qui reste à faire), le choix de
 * qui peut interroger la collection dans le chat MirAI — ses propres groupes à cocher, un pont vers
 * Communauté pour en créer un —, et un guide de démarrage à garder (page imprimable).
 */
const route = useRoute()
const collection = route.query.collection as string
// Une collection Résana s'ouvre à un groupe choisi, jamais à tous, et qui la partage confirme
// les droits Résana des membres (docs/resana.md, décision du 2026-10-24).
const source = (route.query.source as string) || ''
const resana = source === 'resana'
const { titre, retenir } = useTitreCollection(collection, { charger: false })
const { get, post } = useApi()

const choix = ref<'plus-tard' | 'groupe'>('plus-tard')
const groupes = ref<string[]>([])
const nomFiche = ref('')
const droitsConfirmes = ref(false)
const pret = computed(() => choix.value !== 'groupe' || (resana ? partageResanaPret(groupes.value, droitsConfirmes.value) : groupes.value.length > 0))
const envoi = ref(false)
const resultat = ref('')
const erreur = ref(false)
const partages = ref<string[]>([])

// ─── Le récapitulatif ────────────────────────────────────────────────────────
const fiche = ref<any>(null)
const documents = ref<number | null>(null)
const statutResana = ref<any>(null)
const questions = ref({ total: 0, validees: 0 })
const recapPret = ref(false)
const recap = computed(() => resumeCreation({
  titre: titre.value || collection,
  documents: documents.value,
  resana: statutResana.value ? { documents: statutResana.value.documents || 0, etat: statutResana.value.travail?.etat || null, total: statutResana.value.travail?.total || null } : null,
  questions: questions.value,
  sensibilite: libelleSensibilite(fiche.value?.sensitivity),
  groupes: partages.value,
}))

onMounted(async () => {
  if (!collection) {
    return
  }
  const c = encodeURIComponent(collection)
  const [f, docs, statut, qualite] = await Promise.all([
    get(`/api/collections/${c}`).catch(() => null),
    resana ? Promise.resolve(null) : get(`/api/collections/${c}/documents`, { par_page: '1' }).catch(() => null),
    resana ? get(`/api/sources/resana/status/${c}`).catch(() => null) : Promise.resolve(null),
    get(`/api/collections/${c}/qualite`).catch(() => null),
  ])
  fiche.value = f
  if (f) {
    retenir(f)
  }
  documents.value = typeof docs?.total === 'number' ? docs.total : null
  statutResana.value = statut
  questions.value = { total: qualite?.questions?.total || 0, validees: qualite?.questions?.par_relecture?.valide || 0 }
  recapPret.value = true
})

async function terminer () {
  erreur.value = false
  resultat.value = ''
  if (choix.value === 'plus-tard') {
    resultat.value = 'Votre collection est prête. Vérifiez ses réponses dans son bac à sable, puis partagez-la depuis sa fiche.'
    return
  }
  envoi.value = true
  try {
    const choisis = groupes.value
    const liste = choisis.map(g => `« ${g} »`).join(', ')
    const qui = choisis.length > 1 ? `des groupes ${liste}` : `du groupe ${liste}`
    const r: any = await post(`/api/collections/${collection}/publish`, {
      alias_enabled: true,
      alias_name: nomFiche.value.trim(),
      visibility: 'group',
      visibility_groups: choisis,
      ...(resana ? { droits_resana_confirmes: droitsConfirmes.value } : {}),
    })
    partages.value = [...choisis]
    resultat.value = r?.owui?.error
      ? `La collection est publiée, mais le chat MirAI ne l'a pas encore reçue : ${r.owui.error}`
      : resana
        ? `Votre collection est visible ${qui} dans le chat MirAI.`
        : `Votre collection est visible ${qui} dans le chat MirAI. Pour l'ouvrir à tous, vérifiez-la depuis sa fiche.`
  }
  catch (e) {
    erreur.value = true
    resultat.value = messageErreur(e)
  }
  finally {
    envoi.value = false
  }
}
</script>

<template>
  <WizardEtape
    :numero="5"
    :titre="`Partager — ${titre || collection}`"
    chapeau="Votre collection est prête. Voici ce qui a été fait, et qui pourra l'interroger dès maintenant."
  >
    <template #formulaire>
      <div
        v-if="!collection"
        class="fr-alert fr-alert--warning fr-mb-4w"
      >
        <p>
          Aucune collection indiquée. <NuxtLink to="/admin/create">
            Retour à l'étape 1
          </NuxtLink>
        </p>
      </div>

      <div
        v-else
        class="fr-col-12 fr-col-md-8"
      >
        <!-- Le récapitulatif : fait, à faire, et un guide à garder -->
        <div class="fr-callout fr-callout--green-emeraude fr-mb-4w recap">
          <h2 class="fr-callout__title fr-h6">
            <span
              class="fr-icon-success-line fr-icon--sm"
              aria-hidden="true"
            /> Tout s'est bien passé
          </h2>
          <template v-if="recapPret">
            <p class="fr-callout__text fr-text--sm fr-mb-1v">
              <strong>Ce qui a été fait</strong>
            </p>
            <ul class="fr-text--sm fr-mb-2w">
              <li
                v-for="(f, i) in recap.faits"
                :key="i"
              >
                {{ f }}
              </li>
            </ul>
            <p class="fr-callout__text fr-text--sm fr-mb-1v">
              <strong>Ce qui reste à faire</strong>
            </p>
            <ol class="fr-text--sm fr-mb-2w">
              <li
                v-for="(a, i) in recap.aFaire"
                :key="i"
              >
                {{ a }}
              </li>
            </ol>
          </template>
          <p
            v-else
            class="fr-callout__text fr-text--sm"
          >
            Préparation du récapitulatif…
          </p>
          <NuxtLink
            :to="`/c/${encodeURIComponent(collection)}/guide-de-demarrage`"
            class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-printer-line fr-btn--icon-left"
            target="_blank"
          >
            Garder le guide de démarrage<span class="fr-sr-only"> (nouvelle fenêtre)</span>
          </NuxtLink>
          <p class="fr-text--xs fr-mt-1w fr-mb-0 recap__discret">
            Une page à imprimer ou à enregistrer en PDF : vos liens, ce qui reste à faire. Vous la retrouverez aussi depuis la fiche.
          </p>
        </div>

        <template v-if="resana">
          <h2 class="fr-h5">
            Qui peut utiliser cette collection ?
          </h2>
          <p>
            <strong>Pour l'instant, vous seul.</strong> Vous pouvez aussi l'ouvrir à un groupe de collègues, qui la
            retrouveront dans le chat MirAI.
          </p>
          <div class="fr-callout fr-mb-4w">
            <h3 class="fr-callout__title fr-h6">
              Avant de l'ouvrir à un groupe
            </h3>
            <p class="fr-callout__text fr-text--sm">
              Ses documents viennent de vos espaces Résana. Dans Résana, chacun ne voit que les espaces où il est
              invité. Un membre d'un groupe qui n'est pas invité dans ces espaces lirait, par le chat MirAI, des documents
              que Résana ne lui montre pas, et les liens vers ces documents ne s'ouvriraient pas pour lui. Vérifiez donc
              que chaque membre des groupes choisis a accès aux dossiers indexés :
              c'est vous qui pilotez. Une collection Résana ne s'ouvre jamais à tout le monde.
            </p>
          </div>
        </template>
        <div
          v-else
          class="fr-callout fr-mb-4w"
        >
          <h2 class="fr-callout__title fr-h6">
            Ce qui se passe ensuite
          </h2>
          <p class="fr-callout__text fr-text--sm">
            Une collection neuve est <strong>en cours de vérification</strong> : elle se partage avec un groupe,
            pas encore avec tout le ministère. Pour l'ouvrir à tous, complétez sa grille de contrôle et faites-la
            avancer depuis sa fiche — c'est là que vous la retrouverez.
          </p>
        </div>

        <fieldset class="fr-fieldset fr-mb-4w">
          <legend class="fr-fieldset__legend fr-h5">
            Dans le chat MirAI
          </legend>
          <div class="fr-fieldset__element">
            <div class="fr-radio-group">
              <input
                id="part-plus-tard"
                v-model="choix"
                type="radio"
                value="plus-tard"
              >
              <label
                class="fr-label"
                for="part-plus-tard"
              >
                Plus tard — je la vérifie d'abord
                <span class="fr-hint-text">Elle ne s'interroge que dans son bac à sable, depuis sa fiche. Vous la partagerez quand vous voudrez.</span>
              </label>
            </div>
          </div>
          <div class="fr-fieldset__element">
            <div class="fr-radio-group">
              <input
                id="part-groupe"
                v-model="choix"
                type="radio"
                value="groupe"
              >
              <label
                class="fr-label"
                for="part-groupe"
              >
                Un ou plusieurs groupes, pour la tester à plusieurs
                <span class="fr-hint-text">Seuls les membres des groupes choisis la verront dans la liste des modèles du chat MirAI.</span>
              </label>
            </div>
            <div
              v-if="choix === 'groupe'"
              class="fr-ml-4w fr-mt-2w"
            >
              <ChoixGroupes
                v-model="groupes"
                :nom-propose="titre"
              />
            </div>
            <div
              v-if="resana && choix === 'groupe'"
              class="fr-checkbox-group fr-ml-4w fr-mt-2w"
            >
              <input
                id="part-droits-resana"
                v-model="droitsConfirmes"
                type="checkbox"
              >
              <label
                class="fr-label"
                for="part-droits-resana"
              >{{ CONFIRMATION_DROITS_RESANA }}</label>
            </div>
          </div>
          <div
            v-if="choix === 'groupe'"
            class="fr-fieldset__element fr-mt-2w"
          >
            <div class="fr-input-group">
              <label
                class="fr-label"
                for="nom-fiche"
              >Nom dans le chat MirAI
                <span class="fr-hint-text">Laissez vide : c'est le titre de la collection.</span>
              </label>
              <input
                id="nom-fiche"
                v-model="nomFiche"
                class="fr-input"
                :placeholder="titre"
              >
            </div>
          </div>
        </fieldset>

        <p
          class="fr-text--sm"
          style="color:var(--text-mention-grey)"
        >
          D'autres façons de l'interroger (comme outil dans toute conversation, depuis une page web, depuis
          MirAI Assistant pour navigateur) sont prévues ; elles n'existent pas encore et ne sont donc pas proposées ici.
        </p>

        <div
          v-if="resultat"
          class="fr-alert fr-mt-2w"
          :class="erreur ? 'fr-alert--error' : 'fr-alert--success'"
        >
          <p>{{ resultat }}</p>
          <ul
            v-if="!erreur"
            class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mt-1w fr-mb-0"
          >
            <li>
              <NuxtLink
                :to="`/c/${collection}`"
                class="fr-btn fr-btn--sm"
              >
                Ouvrir la fiche de la collection
              </NuxtLink>
            </li>
            <li>
              <NuxtLink
                :to="`/c/${encodeURIComponent(collection)}/guide-de-demarrage`"
                class="fr-btn fr-btn--sm fr-btn--secondary"
                target="_blank"
              >
                Garder le guide de démarrage<span class="fr-sr-only"> (nouvelle fenêtre)</span>
              </NuxtLink>
            </li>
          </ul>
        </div>
      </div>
    </template>
    <template #actions>
      <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-md">
        <li>
          <NuxtLink
            to="/"
            class="fr-btn fr-btn--tertiary-no-outline"
          >
            Annuler
          </NuxtLink>
        </li>
        <li>
          <NuxtLink
            :to="lienEtape(4, collection, source)"
            class="fr-btn fr-btn--secondary"
          >
            Étape précédente
          </NuxtLink>
        </li>
        <li>
          <button
            class="fr-btn"
            :disabled="!collection || envoi || !pret"
            @click="terminer"
          >
            {{ envoi ? 'Enregistrement…' : choix === 'groupe' ? (groupes.length > 1 ? 'Partager avec ces groupes' : 'Partager avec ce groupe') : 'Terminer' }}
          </button>
        </li>
      </ul>
    </template>
  </WizardEtape>
</template>

<style scoped>
.recap ul, .recap ol { padding-left: 1.25rem; }
.recap__discret { color: var(--text-mention-grey); }
</style>
