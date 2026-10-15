<template>
  <section>
    <h3 class="fr-h6 fr-mb-1w">Personas</h3>
    <p class="fr-text--sm fr-mb-2w">{{ AIDE_CONTEXTE }}</p>

    <ul v-if="personas.length" class="gen-personas">
      <li v-for="p in personas" :key="p.id" class="gen-personas__item">
        <template v-if="edition?.id === p.id">
          <FormulairePersona v-model:nom="edition.nom" v-model:description="edition.description_role" :erreurs="erreurs"
                             :id-base="`persona-${p.id}`" />
          <div class="gen-actions">
            <button class="fr-btn fr-btn--sm" :disabled="occupe" @click="enregistrer">Enregistrer</button>
            <button class="fr-btn fr-btn--sm fr-btn--secondary" @click="edition = null">Annuler</button>
          </div>
        </template>
        <template v-else>
          <p class="fr-text--bold fr-mb-0">{{ p.nom }}</p>
          <p class="fr-text--sm fr-mb-1w">{{ p.description_role }}</p>
          <div class="gen-actions">
            <button class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-edit-line fr-btn--icon-left" @click="modifier(p)">Modifier</button>
            <button class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-delete-line fr-btn--icon-left" :disabled="occupe"
                    @click="supprimer(p)">Supprimer</button>
          </div>
        </template>
      </li>
    </ul>
    <p v-else class="fr-text--sm" style="color:var(--text-mention-grey)">Aucun persona pour l'instant.</p>

    <div class="fr-mt-2w">
      <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-sparkling-2-line fr-btn--icon-left"
              :disabled="occupe || enProposition" @click="proposer">
        {{ enProposition ? 'Lecture des documents…' : 'Proposer des personas d\'après les documents' }}
      </button>
      <p v-if="propositions.length" class="fr-text--xs fr-mt-1w fr-mb-1w">
        Proposés d'après les documents — rien n'est enregistré tant que vous ne les ajoutez pas.
      </p>
      <ul v-if="propositions.length" class="gen-personas">
        <li v-for="(pr, i) in propositions" :key="pr.nom" class="gen-personas__item gen-personas__item--propose">
          <p class="fr-text--bold fr-mb-0">{{ pr.nom }}</p>
          <p class="fr-text--sm fr-mb-1w">{{ pr.description_role }}</p>
          <div class="gen-actions">
            <button class="fr-btn fr-btn--sm" :disabled="occupe" @click="adopter(i)">Ajouter</button>
            <button class="fr-btn fr-btn--sm fr-btn--tertiary" @click="Object.assign(nouveau, pr); propositions.splice(i, 1); ouvert = true">Modifier avant d'ajouter</button>
            <button class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline" @click="propositions.splice(i, 1)">Écarter</button>
          </div>
        </li>
      </ul>
    </div>

    <details class="fr-mt-2w" :open="ouvert || !personas.length" @toggle="ouvert = ($event.target as HTMLDetailsElement).open">
      <summary class="fr-text--bold">Ajouter un persona</summary>
      <div class="fr-mt-1w">
        <p class="fr-text--sm fr-mb-1w">Partir d'un exemple :
          <button v-for="e in EXEMPLES_PERSONAS" :key="e.nom" type="button" class="fr-tag fr-tag--sm fr-mr-1w fr-mb-1w"
                  @click="Object.assign(nouveau, e)">{{ e.nom }}</button>
        </p>
        <FormulairePersona v-model:nom="nouveau.nom" v-model:description="nouveau.description_role" :erreurs="erreursNouveau"
                           id-base="persona-nouveau" />
        <button class="fr-btn fr-btn--sm" :disabled="occupe" @click="ajouter">Ajouter</button>
      </div>
    </details>
    <div v-if="erreur" class="fr-alert fr-alert--error fr-alert--sm fr-mt-2w" role="alert"><p>{{ erreur }}</p></div>
  </section>
</template>

<script setup lang="ts">
import { defineComponent, h } from 'vue'
import { AIDE_CONTEXTE, EXEMPLES_PERSONAS, validerPersona, type ErreursPersona } from '~/utils/generation'
import { messageErreur } from '~/utils/collectif'

const props = defineProps<{ collection: string, personas: any[] }>()
const emit = defineEmits<{ change: [] }>()
const g = useGeneration()
const occupe = ref(false)
const erreur = ref('')
const nouveau = reactive({ nom: '', description_role: '' })
const erreursNouveau = ref<ErreursPersona>({})
const edition = ref<{ id: string, nom: string, description_role: string } | null>(null)
const erreurs = ref<ErreursPersona>({})
const propositions = ref<{ nom: string, description_role: string }[]>([])
const enProposition = ref(false)
const ouvert = ref(false)

async function proposer() {
  enProposition.value = true
  erreur.value = ''
  try {
    const r = await g.proposerPersonas(props.collection, 4)
    const deja = new Set([...props.personas, ...propositions.value].map((p: any) => p.nom.toLowerCase()))
    propositions.value = [...propositions.value, ...(r.propositions || []).filter((p: any) => !deja.has(p.nom.toLowerCase()))]
    if (!propositions.value.length) erreur.value = 'Aucun nouveau persona proposé : réessayez, ou ajoutez-en un vous-même.'
  } catch (e) { erreur.value = messageErreur(e) } finally { enProposition.value = false }
}
function adopter(i: number) {
  const pr = propositions.value[i]
  agir(async () => {
    await g.creerPersona(props.collection, pr)
    propositions.value.splice(i, 1)
  })
}

/** Les deux champs d'un persona, avec leurs messages d'erreur DSFR. */
const FormulairePersona = defineComponent({
  props: { nom: String, description: String, erreurs: Object, idBase: String },
  emits: ['update:nom', 'update:description'],
  setup(p, { emit: e }) {
    const champ = (cle: 'nom' | 'description', libelle: string, aide: string, multi: boolean) => {
      const err = (p.erreurs as any)?.[cle === 'nom' ? 'nom' : 'description_role']
      const id = `${p.idBase}-${cle}`
      return h('div', { class: ['fr-input-group', err && 'fr-input-group--error'] }, [
        h('label', { class: 'fr-label', for: id }, [libelle, h('span', { class: 'fr-hint-text' }, aide)]),
        h(multi ? 'textarea' : 'input', {
          id, class: ['fr-input', err && 'fr-input--error'], rows: multi ? 3 : undefined,
          value: cle === 'nom' ? p.nom : p.description, 'aria-describedby': err ? `${id}-err` : undefined,
          onInput: (ev: Event) => e(`update:${cle}` as any, (ev.target as HTMLInputElement).value),
        }),
        err ? h('p', { id: `${id}-err`, class: 'fr-error-text' }, err) : null,
      ])
    }
    return () => h('div', [
      champ('nom', 'Nom', 'Court : « Agent au guichet étrangers ».', false),
      champ('description', 'Qui pose la question, et dans quelle situation', 'Son métier, à qui il répond, ce qu\'il cherche.', true),
    ])
  },
})

const noms = (sauf?: string) => props.personas.filter(p => p.id !== sauf).map(p => p.nom)

async function agir(f: () => Promise<any>) {
  occupe.value = true
  erreur.value = ''
  try { await f(); emit('change') } catch (e) { erreur.value = messageErreur(e) } finally { occupe.value = false }
}

function ajouter() {
  erreursNouveau.value = validerPersona(nouveau, noms())
  if (Object.keys(erreursNouveau.value).length) return
  agir(async () => {
    await g.creerPersona(props.collection, { nom: nouveau.nom.trim(), description_role: nouveau.description_role.trim() })
    nouveau.nom = ''
    nouveau.description_role = ''
  })
}
function modifier(p: any) {
  erreurs.value = {}
  edition.value = { id: p.id, nom: p.nom, description_role: p.description_role }
}
function enregistrer() {
  const e = edition.value!
  erreurs.value = validerPersona(e, noms(e.id))
  if (Object.keys(erreurs.value).length) return
  agir(async () => {
    await g.modifierPersona(props.collection, e.id, { nom: e.nom.trim(), description_role: e.description_role.trim() })
    edition.value = null
  })
}
function supprimer(p: any) {
  if (!confirm(`Supprimer le persona « ${p.nom} » ? Les paires déjà générées restent.`)) return
  agir(() => g.supprimerPersona(props.collection, p.id))
}
</script>

<style scoped>
.gen-personas { list-style: none; padding: 0; margin: 0; }
.gen-personas__item { border-left: 3px solid var(--border-default-blue-france); padding: .25rem 0 .25rem 1rem; margin-bottom: 1rem; }
.gen-personas__item--propose { border-left-color: var(--border-default-yellow-tournesol, #c8aa39); }
.gen-actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
</style>
