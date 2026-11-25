/* Même moteur Python que les lanceurs locaux, exécuté dans le navigateur. */
(() => {
  'use strict';
  const base = new URL('../', document.currentScript.src);
  const storageKey = 'ffessm-qcm:pages:v1:' + base.pathname;
  const runtimeURL = 'https://cdn.jsdelivr.net/pyodide/v314.0.8/full/';
  const root = '/qcm';
  let runtime;

  async function init() {
    if (!navigator.locks) throw Error('Ce navigateur ne prend pas en charge la sauvegarde du QCM. Utilise un navigateur récent.');
    // Vérifier le stockage avant de proposer une session qui ne serait pas conservée.
    const probe = storageKey + ':probe';
    try { localStorage.setItem(probe, 'ok'); localStorage.removeItem(probe); }
    catch { throw Error('Le stockage du navigateur est indisponible. Autorise les données du site puis recharge la page.'); }
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = runtimeURL + 'pyodide.js';
      script.onload = resolve;
      script.onerror = () => reject(Error('Chargement du moteur impossible. Vérifie ta connexion puis recharge la page.'));
      document.head.append(script);
    });
    const py = await loadPyodide({indexURL: runtimeURL});
    await Promise.all(['app/engine.py', 'app/layout.py', 'questions/bank.json', 'questions/synthesis.json'].map(async name => {
      const response = await fetch(new URL(name, base));
      if (!response.ok) throw Error('Fichier du QCM indisponible : ' + name);
      py.FS.mkdirTree(root + '/' + name.slice(0, name.lastIndexOf('/')));
      py.FS.writeFile(root + '/' + name, new Uint8Array(await response.arrayBuffer()));
    }));
    py.FS.mkdirTree(root + '/preferences');
    py.runPython(`
import json, sys
sys.path.insert(0, '/qcm/app')
from engine import Quiz

def pages_call(action, body):
    quiz = Quiz('/qcm')
    if action == 'answer':
        return quiz.answer(body.get('letter', ''), body.get('question_id'),
                           presentation_id=body.get('presentation_id'))
    if action == 'export':
        return quiz.state
    methods = {'next': quiz.next, 'session': quiz.session,
               'resume-latest': quiz.resume_latest, 'start-review': quiz.start_review,
               'restart': quiz.restart, 'reset': quiz.reset, 'status': quiz.status,
               'summary': quiz.summary, 'history': quiz.history}
    if action not in methods:
        raise ValueError('Action inconnue.')
    return methods[action]()
`);
    return py;
  }

  // L'initialisation reste paresseuse pour que l'interface affiche les erreurs.
  window.pagesApi = async (action, body = {}) => {
    runtime ??= init();
    const py = await runtime;
    return navigator.locks.request(storageKey, async () => {
      // Relire à chaque action : plusieurs onglets partagent une même progression.
      const saved = localStorage.getItem(storageKey);
      let files = {};
      if (saved !== null) {
        try {
          files = JSON.parse(saved);
          if (!files || typeof files !== 'object' || Array.isArray(files)
              || !Object.hasOwn(files, 'progress.json')
              || Object.entries(files).some(([name, value]) => !/^[\w.-]+\.json$/.test(name) || typeof value !== 'string')) throw Error();
        } catch { throw Error('La progression enregistrée est illisible. Les données ont été conservées ; ne vide pas le stockage du site.'); }
      }
      const directory = root + '/preferences/';
      for (const name of py.FS.readdir(directory)) {
        if (name !== '.' && name !== '..') py.FS.unlink(directory + name);
      }
      for (const [name, value] of Object.entries(files)) py.FS.writeFile(directory + name, value);
      py.globals.set('pages_action', action);
      py.globals.set('pages_body', JSON.stringify(body));
      const result = py.runPython('json.dumps(pages_call(pages_action, json.loads(pages_body)), ensure_ascii=False)');
      const updated = {};
      for (const name of py.FS.readdir(directory)) {
        if (name.endsWith('.json')) updated[name] = py.FS.readFile(directory + name, {encoding: 'utf8'});
      }
      try { localStorage.setItem(storageKey, JSON.stringify(updated)); }
      catch { throw Error('Sauvegarde impossible : le stockage du navigateur est plein ou bloqué. Cette action n’a pas été enregistrée.'); }
      return JSON.parse(result);
    });
  };
})();
