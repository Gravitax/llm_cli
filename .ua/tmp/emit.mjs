#!/usr/bin/env node
// Emits batch-<i>.json from (a) deterministic extraction results + import data
// and (b) a hand-authored semantic sidecar. Keeps `imports` edges 1:1 with
// batchImportData so the file-analyzer self-check cannot drift.
import { readFileSync, writeFileSync } from 'node:fs'

const UA = '/opt/eca/llm_cli/.ua'
const idx = process.argv[2]
const read = (p) => JSON.parse(readFileSync(p, 'utf8'))

const extract = read(`${UA}/tmp/ua-file-extract-results-${idx}.json`)
const input = read(`${UA}/tmp/ua-file-analyzer-input-${idx}.json`)
const sem = read(`${UA}/tmp/sem-${idx}.json`)
const importData = input.batchImportData || {}

const PREFIX = {
  file: 'file', config: 'config', document: 'document', service: 'service',
  pipeline: 'pipeline', resource: 'resource', table: 'table', schema: 'schema',
  endpoint: 'endpoint',
}

const nodes = []
const edges = []
const nodeIds = new Set()

const addNode = (n) => {
  if (nodeIds.has(n.id)) return
  nodeIds.add(n.id)
  nodes.push(n)
}
const addEdge = (source, target, type, weight) =>
  edges.push({ source, target, type, direction: 'forward', weight })

const byPath = new Map(extract.results.map((r) => [r.path, r]))

for (const [path, meta] of Object.entries(sem.files)) {
  const type = meta.type || 'file'
  const prefix = PREFIX[type]
  if (!prefix) throw new Error(`bad node type "${type}" for ${path}`)
  const fileId = `${prefix}:${path}`
  const node = {
    id: fileId,
    type,
    name: path.split('/').pop(),
    filePath: path,
    summary: meta.summary,
    tags: meta.tags,
    complexity: meta.complexity,
  }
  if (meta.languageNotes) node.languageNotes = meta.languageNotes
  addNode(node)

  // imports: 1:1 with the pre-resolved project-internal import list
  for (const target of importData[path] || []) {
    const tType = sem.pathTypes?.[target] || 'file'
    addEdge(fileId, `${PREFIX[tType] || 'file'}:${target}`, 'imports', 0.7)
  }
}

// function / class sub-nodes
const ex = extract.results
for (const [key, meta] of Object.entries(sem.symbols || {})) {
  const sep = key.lastIndexOf('::')
  const path = key.slice(0, sep)
  const name = key.slice(sep + 2)
  const kind = meta.kind || 'function'
  const r = byPath.get(path)
  const src = kind === 'class' ? r?.classes : r?.functions
  const hit = src?.find((s) => s.name === name)
  const id = `${kind}:${path}:${name}`
  const node = {
    id, type: kind, name, filePath: path,
    summary: meta.summary, tags: meta.tags,
    complexity: meta.complexity || 'simple',
  }
  if (hit) node.lineRange = [hit.startLine, hit.endLine]
  addNode(node)

  const parentType = sem.files[path]?.type || 'file'
  const parentId = `${PREFIX[parentType]}:${path}`
  addEdge(parentId, id, 'contains', 1.0)
  const isExported = (r?.exports || []).some((e) => e.name === name)
  if (isExported) addEdge(parentId, id, 'exports', 0.8)
}

for (const e of sem.extraEdges || []) {
  addEdge(e.source, e.target, e.type, e.weight ?? 0.5)
}

// self-check: imports emitted must equal sum(batchImportData[file].length)
const expected = Object.keys(sem.files).reduce(
  (a, p) => a + (importData[p] || []).length, 0)
const got = edges.filter((e) => e.type === 'imports').length
if (expected !== got) throw new Error(`imports mismatch: expected ${expected}, got ${got}`)

writeFileSync(`${UA}/intermediate/batch-${idx}.json`,
  JSON.stringify({ nodes, edges }, null, 1))

const missing = extract.results.map((r) => r.path).filter((p) => !sem.files[p])
console.log(`batch-${idx}: ${nodes.length} nodes, ${edges.length} edges ` +
  `(${got} imports)${missing.length ? ` | MISSING FILES: ${missing.join(', ')}` : ''}`)
