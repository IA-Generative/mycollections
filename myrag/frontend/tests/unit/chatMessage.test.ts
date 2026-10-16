import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { computed } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'
import { transformWithEsbuild } from 'vite'

/**
 * Les puces de `ChatMessage.vue` : une par fichier cité (clé `original_filename || filename`).
 * On charge le VRAI composant (son `<script setup>` compilé) et on lit `deduped`, sans le
 * monter : la suite tourne sans DOM.
 *
 * Le serveur aplatit les sources d'OpenRAG 2.3 (métadonnées sous `chunk`) avant de les rendre :
 * le front reçoit toujours des sources à plat.
 */
async function puces(sources: any[]): Promise<any[]> {
  const fichier = fileURLToPath(new URL('../../components/playground/ChatMessage.vue', import.meta.url))
  const { descriptor } = parse(readFileSync(fichier, 'utf8'), { filename: fichier })
  const script = compileScript(descriptor, { id: 'chat-message', inlineTemplate: false })
  const { code } = await transformWithEsbuild(script.content, 'ChatMessage.ts', { loader: 'ts', format: 'cjs' })
  const modules: Record<string, any> = {
    vue: { defineComponent: (o: any) => o },
    '~/utils/sanitize': { renderMarkdownSafe: (s: string) => s },
  }
  const module = { exports: {} as any }
  // `computed` est importé automatiquement par Nuxt : on le fournit.
  new Function('require', 'module', 'exports', 'computed', code)((n: string) => modules[n] ?? {}, module, module.exports, computed)
  const composant = module.exports.default
  const liaisons = composant.setup({ message: { role: 'assistant', content: 'Réponse.', sources } }, { expose: () => {}, emit: () => {} })
  return liaisons.deduped.value
}

const docA = { _id: '4567', filename: 'CESEDA_L423_1.md', original_filename: 'CESEDA-L423-1.md', page: 3, chunk_url: '/api/openrag/extract/4567' }
const docABis = { ...docA, _id: '4568', page: 4, chunk_url: '/api/openrag/extract/4568' }
const docB = { _id: '7001', filename: 'faq.docx', original_filename: 'Foire aux questions.docx', chunk_url: '/api/openrag/extract/7001' }
const docC = { _id: '9001', filename: 'note.md', chunk_url: '/api/openrag/extract/9001' }

describe('ChatMessage.vue — une puce par fichier', () => {
  it('sources à plat : autant de puces que de fichiers distincts', async () => {
    const p = await puces([docA, docABis, docB, docC])
    expect(p.map(s => s._id)).toEqual(['4567', '7001', '9001'])
  })

  it('le nom d\'origine prime sur le nom de stockage', async () => {
    const memeStockage = { ...docB, _id: '7002', filename: docA.filename }
    expect((await puces([docA, memeStockage])).length).toBe(2)
  })

  it('une source web garde sa puce', async () => {
    const web = { source_type: 'web', url: 'https://www.service-public.fr/x', title: 'Carte de séjour' }
    expect((await puces([docA, web])).length).toBe(2)
  })

  it('sans aplatissement côté serveur, des sources 2.3 (sous `chunk`) fusionneraient en une seule puce', async () => {
    const niche = (s: any) => ({ source_type: 'document', chunk: s, chunk_url: s.chunk_url })
    expect((await puces([niche(docA), niche(docB), niche(docC)])).length).toBe(1)
  })
})
