// Test de l'adaptateur avec le vrai moteur Python/WebAssembly, sans serveur API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {loadPyodide} = require(process.env.PYODIDE_MODULE || 'pyodide');
const root = path.resolve(__dirname, '..');

(async () => {
  const py = await loadPyodide();
  const values = new Map();
  let blocked = false, queue = Promise.resolve();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem(key, value) { if (blocked) throw Error('quota'); values.set(key, value); },
    removeItem: key => values.delete(key),
  };
  const locks = {request(key, callback) {
    const result = queue.then(callback);
    queue = result.catch(() => {});
    return result;
  }};
  function tab() {
    const context = {window: {}, URL, Uint8Array, console, localStorage: storage,
      navigator: {locks}, loadPyodide: async () => py,
      document: {currentScript: {src: 'https://example.org/ffessm_qcm/web/pages.js'},
        createElement: () => ({}), head: {append: script => script.onload()}},
      fetch: async url => {
        assert.equal(url.pathname.startsWith('/ffessm_qcm/'), true);
        const data = fs.readFileSync(path.join(root, url.pathname.slice('/ffessm_qcm/'.length)));
        return {ok: true, arrayBuffer: async () => data};
      }};
    vm.runInNewContext(fs.readFileSync(path.join(root, 'web/pages.js'), 'utf8'), context);
    return context.window.pagesApi;
  }
  const api = tab();
  assert.equal((await api('session')).has_history, false);
  const q = await api('next');
  assert.equal(q.question_id, 1);
  await api('answer', {letter: 'A', question_id: q.question_id, presentation_id: q.presentation_id});
  assert.equal((await api('history')).length, 1);
  assert.equal((await api('export')).attempts.length, 1);
  assert((await api('summary')).reference.sections.length > 0);
  const secondTab = tab();
  assert.equal((await secondTab('session')).has_history, true);
  assert.equal((await secondTab('start-review')).session_mode, 'revision');
  assert.equal((await api('resume-latest')).session_mode, 'normal');
  await Promise.all([api('next'), secondTab('next')]);
  const key = [...values.keys()][0];
  const before = values.get(key);
  blocked = true;
  await assert.rejects(api('reset'), /Sauvegarde impossible/);
  assert.equal(values.get(key), before);
  blocked = false;
  assert.equal((await api('history')).length, 1);
  await api('restart');
  assert(Object.keys(JSON.parse(values.get(key))).some(name => /^progress-/.test(name)));
  assert.equal((await api('history')).length, 0);
  await api('reset');
  values.set(key, 'corrompu');
  await assert.rejects(api('session'), /illisible/);
  assert.equal(values.get(key), 'corrompu');
  console.log('Pages OK : vrai moteur WebAssembly, sous-chemin, réponses, synthèse, reprise, révision, onglets, archives et erreurs de stockage.');
})().catch(error => {console.error(error); process.exitCode = 1;});
