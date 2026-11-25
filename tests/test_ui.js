// Tests du comportement de l'interface sans navigateur ni connexion réseau.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(require('node:path').join(__dirname, '..', 'interface.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
function element(tag='div') { return {tagName:tag.toUpperCase(),hidden:false,textContent:'',className:'',children:[],dataset:{},style:{},value:'',attrs:{},disabled:false,checked:false,
  set innerHTML(value){throw Error('Le texte doit être rendu sans innerHTML : '+value);},
  setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];},replaceChildren(){this.children=[];},append(...v){this.children.push(...v);},focus(){},scrollIntoView(){},
  click(){if(this.disabled)return;if(this.tagName==='LABEL'){const checkbox=this.children.find(child=>child.tagName==='INPUT');if(checkbox&&!checkbox.disabled){checkbox.checked=!checkbox.checked;checkbox.onchange?.();}return;}if(this.tagName==='INPUT'&&this.type==='checkbox'){this.checked=!this.checked;return this.onchange?.();}return this.onclick?.();},
  closest(selector){return selector.split(',').some(tag=>tag.trim().toUpperCase()===this.tagName)?this:null;},addEventListener(){},showModal(){this.open=true;},close(){this.open=false;}}; }
for(const m of html.matchAll(/id="([^"]+)"/g))elements.set(m[1],element());
const get=id=>{assert(elements.has(id),'Element absent: '+id);return elements.get(id);};
get('details').append(...['summary-panel','history-panel','scope-panel','sources-panel'].map(get));
const timers=new Map();let tid=0,calls=[],requests=[],currentQ=6,summaryReference=null,oneAnswer=false,useVisibleNumbers=true,mode='normal',reviewAvailable=true;const keyHandlers=[];
const status={scope:30,initial_acquired:5,initial_complete:false,points:5.5,attempts:6,counts:{failed:0,partial:1},growth_correct:0,last_answer_at:'2026-11-23T12:34:00Z'};
const question=id=>({question_id:id,...(useVisibleNumbers?{question_number:id+100}:{}),presentation_id:id,question:'Question '+id,kind:'new',one_answer:oneAnswer,session_mode:mode,choices:{A:'un',B:'deux',C:'trois',D:'quatre'},status:{...status,session_mode:mode}});
const source={reference:'Source vérifiée',url:'https://example.org'};
async function fetchMock(path,options){const name=path.split('/').pop(),body=JSON.parse(options.body);calls.push(name);requests.push({name,body});let v;
  if(name==='session')v={has_history:true,...(reviewAvailable==='missing'?{}:{review_available:reviewAvailable}),session_mode:mode,resume_question_id:6,resume_question_number:106,last_presented_question_number:106,priority_question_id:6,priority_question_number:106,priority_reason:'Q106 en reprise : réponse partielle.',status:{...status,session_mode:mode}};
  else if(name==='resume-latest'){mode='normal';v=question(currentQ);}
  else if(name==='start-review'){mode='revision';v=question(6);}
  else if(name==='next')v=question(mode==='revision'?6:++currentQ);
  else if(name==='answer'){const selected=body.letter.split(','),expected=oneAnswer?['B']:['B','D'];const score=selected.some(letter=>!expected.includes(letter))?0:selected.length===expected.length?1:.5;v={score,correct:score===1,correct_letters:expected,correct_letter:expected.join(', '),explanation:'Explication',source,status:{...status,session_mode:mode},answered_at:'2026-11-23T12:34:00Z'};}
  else if(name==='history')v=[{question_id:6,...(useVisibleNumbers?{question_number:106}:{}),letter:'B',score:.5,correct:false,at:'2026-11-23T12:34:00Z'},{question_id:5,letter:'A',score:1,correct:true,at:null}];
  else if(name==='summary')v={rules:[{rule:'Règle',source}],status,...(summaryReference?{reference:summaryReference}:{})};
  else if(name==='reset'){mode='normal';v={message:'Réinitialisé',next:question(currentQ=1)};}
  else throw Error('Action inattendue: '+name);
  return {ok:true,json:async()=>v};
}
const context={document:{getElementById:get,createElement:element,addEventListener(name,handler){if(name==='keydown')keyHandlers.push(handler);}},location:{protocol:'http:'},fetch:fetchMock,
  setTimeout(fn,delay){const id=++tid;timers.set(id,{fn,delay,interval:false});return id;},clearTimeout(id){timers.delete(id);},
  setInterval(fn,delay){const id=++tid;timers.set(id,{fn,delay,interval:true});return id;},clearInterval(id){timers.delete(id);},
  URL:{createObjectURL(){return 'blob:test';},revokeObjectURL(){}},Blob:global.Blob,confirm:()=>true,Date,console};
vm.createContext(context);vm.runInContext(script,context);
async function flush(){for(let i=0;i<30;i++)await Promise.resolve();}
function pressKey(key,target=element()){const event={key,target,ctrlKey:false,altKey:false,metaKey:false,repeat:false,preventDefault(){this.prevented=true;}};for(const handler of keyHandlers)handler(event);return event;}
(async()=>{
  await flush();assert.equal(get('quiz').hidden,true);assert.equal(get('session').hidden,false);
  assert.equal(get('start-review').disabled,false);assert(get('points-date').textContent.includes('23/11/2026'));assert(get('points-date').textContent.includes('13:34'),'La date du dernier résultat doit être affichée en heure de Paris');
  assert.equal(get('resume').textContent,'Continuer à la question 106');
  get('resume').click();await flush();assert.equal(get('question').textContent,'Question 6');
  assert.equal(get('number').textContent,'Question n° 106');
  const options=get('answers').children;
  assert(options.every(option=>option.tagName==='BUTTON'&&option.children.length===2&&option.children[0].className==='key'));
  assert.equal(get('kind').textContent,'Plusieurs réponses');
  assert(!html.includes("type='checkbox'")&&!html.includes('role="checkbox"'),'Les réponses doivent conserver leurs boutons sans cases');
  assert(get('answer-instructions').textContent.includes('Plusieurs réponses sont attendues'));
  assert(!html.includes('Choisis une seule réponse.'));
  assert.equal(get('validate').disabled,true);
  const answersBefore=calls.filter(name=>name==='answer').length;get('validate').click();await flush();assert.equal(calls.filter(name=>name==='answer').length,answersBefore,'Une sélection vide ne doit pas être envoyée');
  options[1].click();options[3].click();assert.equal(options[1].getAttribute('aria-pressed'),'true');assert.equal(options[3].getAttribute('aria-pressed'),'true');
  options[1].click();assert.equal(options[1].getAttribute('aria-pressed'),'false');assert.equal(options[3].getAttribute('aria-pressed'),'true');
  options[3].click();assert.equal(get('validate').disabled,true,'Tout décocher doit désactiver la validation');
  pressKey('a');assert.equal(options[0].getAttribute('aria-pressed'),'true');pressKey('A');assert.equal(options[0].getAttribute('aria-pressed'),'false');
  pressKey('b',options[1]);pressKey('D',options[3]);
  assert.equal(options[1].getAttribute('aria-pressed'),'true');assert.equal(options[3].getAttribute('aria-pressed'),'true');
  pressKey('Enter',options[3]);await flush();
  const multiPayload=requests.filter(row=>row.name==='answer').at(-1).body;
  assert.equal(multiPayload.letter,'B,D');assert.equal(multiPayload.question_id,6);assert.equal(multiPayload.presentation_id,6);
  assert(options.every(option=>option.disabled),'Les boutons doivent être figés après correction');
  assert.equal(get('feedback').className,'correct');
  assert.equal(get('answer-date').hidden,false);assert(get('answer-date').textContent.includes('13:34'));
  let timer=[...timers.values()].find(t=>!t.interval&&t.delay===10000);assert(timer,'Passage automatique à 10 secondes absent');
  timer.fn();await flush();assert.equal(get('question').textContent,'Question 7');
  assert(get('answers').children.every(option=>option.getAttribute('aria-pressed')==='false'),'La question suivante doit démarrer sans sélection');
  get('history').click();await flush();assert.equal(get('details').hidden,false);
  assert(get('history-panel').children.some(row=>row.textContent.startsWith('Question 106')),'Les résultats doivent afficher le numéro visible');
  assert(get('history-panel').children.some(row=>row.textContent.includes('23/11/2026')&&row.textContent.includes('13:34')),'L’historique doit afficher date et heure de Paris');
  assert(get('history-panel').children.some(row=>row.textContent.includes('date inconnue')),'Les dates historiques absentes ne doivent pas être inventées');
  const before=calls.filter(x=>x==='history').length;get('history').click();await flush();assert.equal(get('details').hidden,true);assert.equal(calls.filter(x=>x==='history').length,before);
  get('history').click();await flush();assert.equal(get('details').hidden,false);
  get('answers').children[1].click();get('validate').click();await flush();assert.equal(get('feedback').className,'partial');assert(get('explanation').textContent.includes('Réponses attendues : B, D.'),'Une réponse partielle doit afficher tous les choix attendus');assert(!elements.has('manual'),'Auto-attribution de points présente');
  get('report').click();assert.equal(get('report-dialog').open,true);assert(![...timers.values()].some(t=>!t.interval&&t.delay===10000),'Le signalement doit suspendre le changement de question');
  get('report-remarks').value='Le milieu est incomplet.';get('report-prepare').click();
  const report=JSON.parse(get('report-json').textContent);assert.equal(report.question_id,7);assert.equal(report.question_number,107);assert.equal(report.question_title,'Question 7');assert.equal(report.remarks,'Le milieu est incomplet.');assert(get('report-question').textContent.startsWith('Question 107'));assert(get('report-mail').href.startsWith('mailto:woyczek@gmail.com?'));assert.equal(JSON.parse(decodeURIComponent(get('report-mail').href.split('&body=')[1])).question_id,7);assert.equal(decodeURIComponent(get('report-mail').href.split('subject=')[1].split('&body=')[0]),'QCM FFESSM — erreur question 107');assert.equal(get('report-download').download,'ffessm-erreur-Q107.json');
  useVisibleNumbers=false;oneAnswer=true;get('reset').click();await flush();assert.equal(get('kind').textContent,'1 réponse');assert.equal(get('question').textContent,'Question 1');assert.equal(get('number').textContent,'Question n° 1');assert.equal(get('details').hidden,true);
  pressKey('C');pressKey('a');assert.equal(get('answers').children[0].getAttribute('aria-pressed'),'true');assert.equal(get('answers').children[2].getAttribute('aria-pressed'),'true');pressKey('Enter');await flush();
  assert.equal(requests.filter(row=>row.name==='answer').at(-1).body.letter,'A,C','Les lettres envoyées doivent être cumulées et triées');
  assert.equal(get('feedback').className,'wrong');assert(get('explanation').textContent.includes('Réponse attendue : B.'),'Une réponse avec intrus doit afficher la correction complète');
  const walk=node=>[node,...node.children.flatMap(walk)];
  get('summary').click();await flush();assert.equal(get('summary-panel').hidden,false);assert(walk(get('summary-panel')).some(n=>n.textContent==='Synthèse'));
  const summaryCalls=calls.filter(x=>x==='summary').length;
  get('summary').click();await flush();assert.equal(get('summary-panel').hidden,true);assert.equal(get('summary').getAttribute('aria-expanded'),'false');assert.equal(calls.filter(x=>x==='summary').length,summaryCalls,'Fermer la synthèse ne doit pas recharger de données');
  summaryReference={version:'test',checked_at:'2026-11-23',title:'<img src=x onerror=alert(1)>',introduction:'Sources officielles seulement.',
    sections:[{id:'test',title:'Prérogatives',columns:['Niveau','Règle'],rows:[['N1','<script>alert(1)</script>']],notes:['Une note'],sources:['official','unsafe']}],
    sources:{official:{reference:'Source vérifiée',url:'https://example.org/reference',version:'2026'},unsafe:{reference:'URL interdite',url:'javascript:alert(1)'}},
    audit:[{item:'Comparaison',supplied:'Proposition',verified:'Règle vérifiée',status:'qualified',source_ids:['official']}],attachments:[{name:'proposition.pdf'}]};
  const duplicateBefore=calls.filter(name=>name==='answer').length;get('validate').click();await flush();assert.equal(calls.filter(name=>name==='answer').length,duplicateBefore,'Une correction affichée ne doit pas permettre une deuxième soumission');
  oneAnswer=false;get('next').click();await flush();get('answers').children[1].click();get('answers').children[3].click();get('validate').click();await flush();assert([...timers.values()].some(t=>!t.interval&&t.delay===10000));
  get('summary').click();await flush();
  assert(![...timers.values()].some(t=>!t.interval&&t.delay===10000),'Lire la synthèse doit suspendre le passage automatique');
  const summaryNodes=walk(get('summary-panel'));
  assert(summaryNodes.some(n=>n.textContent==='Synthèse vérifiée — ensemble du programme'));
  assert(summaryNodes.some(n=>n.textContent.includes('Vérifiée le 2026-11-23')));
  assert(summaryNodes.some(n=>n.tagName==='TABLE'));assert(summaryNodes.some(n=>n.tagName==='TH'&&n.attrs.scope==='col'));
  assert(summaryNodes.some(n=>n.attrs.role==='region'&&n.attrs['aria-label']==='Prérogatives'));
  assert(summaryNodes.some(n=>n.textContent==='<script>alert(1)</script>'));
  assert(!summaryNodes.some(n=>n.tagName==='SCRIPT'||n.tagName==='IMG'));
  assert(!summaryNodes.some(n=>n.textContent.includes('Vérification du document transmis')),'Le bloc audit ne doit plus être affiché');
  assert(!summaryNodes.some(n=>n.className==='summary-audit'));
  assert(!summaryNodes.some(n=>n.textContent==='Règle — '),'Le périmètre courant doit avoir son propre panneau');
  const printable=get('summary-panel').children[0];assert.equal(printable.className,'print-document');
  assert(printable.children.some(n=>n.tagName==='A'&&n.textContent==='PDF à imprimer'&&n.href==='/documents/Prerogatives_FFESSM_impression.pdf'),'Le PDF local à imprimer doit figurer en haut de la synthèse');
  assert(!html.includes('chatgpt.com/library'),'La synthèse doit utiliser le document local du lanceur');
  const tableWrapperCss=html.match(/\.summary-table\{([^}]+)\}/)[1],tableCss=html.match(/\.summary-table table\{([^}]+)\}/)[1];
  assert(!/(max-height|min-width|overflow\s*:)/.test(tableWrapperCss+tableCss),'Les tableaux ne doivent imposer ni barre de défilement ni largeur minimale');
  assert(tableCss.includes('table-layout:fixed'),'Les colonnes doivent se répartir dans la largeur disponible');
  assert(html.includes('overflow-wrap:anywhere'),'Les cellules doivent pouvoir retourner à la ligne');
  get('sources').click();await flush();assert.equal(get('sources-panel').hidden,false);assert.equal(get('summary-panel').hidden,false,'Sources et synthèse doivent être indépendantes');
  const sourceNodes=walk(get('sources-panel'));
  assert(sourceNodes.some(n=>n.tagName==='A'&&n.href==='https://example.org/reference'));
  assert(!sourceNodes.some(n=>n.tagName==='A'&&String(n.href).startsWith('javascript:')));
  get('scope-details').click();await flush();assert.equal(get('scope-panel').hidden,false);assert.equal(get('summary-panel').hidden,false);assert.equal(get('sources-panel').hidden,false);
  assert(walk(get('scope-panel')).some(n=>n.textContent==='Règle — '));
  assert(walk(get('scope-panel')).some(n=>n.textContent==='Rappel du périmètre courant — 30 %'));
  get('history').click();await flush();assert.equal(get('history-panel').hidden,false);get('history').click();await flush();assert.equal(get('history-panel').hidden,true);assert.equal(get('summary-panel').hidden,false);
  for(const [button,panel] of [['scope-details','scope-panel'],['sources','sources-panel'],['summary','summary-panel']]){
    const before=calls.length;get(button).click();await flush();assert.equal(get(panel).hidden,true);assert.equal(get(button).getAttribute('aria-expanded'),'false');assert.equal(calls.length,before,'Masquer une consultation ne doit pas appeler le serveur');
    get(button).click();await flush();assert.equal(get(panel).hidden,false);assert.equal(get(button).getAttribute('aria-expanded'),'true');
    get(button).click();await flush();assert.equal(get(panel).hidden,true);
  }
  assert.equal(get('details').hidden,true,'Le conteneur doit se masquer lorsque les quatre panneaux sont fermés');
  const nav=html.match(/<nav class="toolbar"[\s\S]*?<\/nav>/)[0];
  assert(nav.indexOf('id="export"')<nav.indexOf('id="reset"'),'Exporter doit précéder Réinitialiser');
  assert(nav.includes('class="toolbar-actions"'));
  assert(/class="[^"]*action-export[^\"]*" id="export"/.test(nav));assert(/class="[^"]*action-reset[^\"]*" id="reset"/.test(nav));
  assert(html.includes('.toolbar-actions{margin-left:auto}'));
  assert(html.includes('.action-export{background:#1266ac'));assert(html.includes('.action-reset{background:#b72c35'));
  for(const action of ['export','reset','validate']){const tag=html.match(new RegExp('<button[^>]*id="'+action+'"[^>]*>'))[0];assert(!tag.includes('aria-expanded'),'Les actions ne doivent pas être des toggles');}
  get('report').click();get('report-remarks').value='Vérification sans numéro visible fourni.';get('report-prepare').click();
  const legacyReport=JSON.parse(get('report-json').textContent);assert.equal(legacyReport.question_id,2);assert(!Object.hasOwn(legacyReport,'question_number'),'Le champ de numéro visible doit rester facultatif');
  assert.equal(decodeURIComponent(get('report-mail').href.split('subject=')[1].split('&body=')[0]),'QCM FFESSM — erreur question 2');
  const paletteCases=[
    {id:'jeunes',labels:['N1','GP-N4','Or','PE60'],expected:['young','young','young','young'],header:'young'},
    {id:'exploration',labels:['PE12 / PE20','PA20','N1','N2','N3','GP-N4','N5 / DPE','GP / N4 et baptême'],expected:['diver','diver','diver','diver','diver','instructor','instructor','instructor'],header:'neutral'},
    {id:'enseignement',labels:['E1 / Initiateur','E2 : GP-N4 + Initiateur','Stagiaire MF1 reconnu E2','E3 / MF1','E4 / MF2','Exploration autonome d’un enseignant'],expected:['instructor','instructor','instructor','instructor','instructor','instructor'],header:'instructor'},
    {id:'acces',labels:['N1','PA20 / PE40 / N2','PA40','PE60','N3','GP-N4','Initiateur : stage initial','MF1 : voie classique','MF2 : examen','N5'],expected:['diver','diver','diver','diver','diver','instructor','instructor','instructor','instructor','instructor'],header:'neutral'},
    {id:'validation',labels:['N1 à N3 et qualifications PE/PA','GP-N4','Initiateur','E2','MF1','MF2'],expected:['diver','instructor','instructor','instructor','instructor','instructor'],header:'neutral'},
    {id:'discordances',labels:['Âge du PE60','Préalable technique à l’examen initiateur pour un jeune'],expected:['diver','instructor'],header:'neutral'}
  ];
  context.paletteFixture={status,reference:{version:'palette-test',checked_at:'2026-11-23',title:'Palette',introduction:'',sources:{},sections:paletteCases.map(item=>({id:item.id,title:item.id,columns:['Qualification','Règle'],rows:item.labels.map(label=>[label,'Texte']),notes:[],sources:[]}))},rules:[]};
  vm.runInContext("renderSummary(paletteFixture,document.getElementById('summary-panel'))",context);
  for(const item of paletteCases){
    const section=get('summary-panel').children.find(node=>node.tagName==='SECTION'&&node.children[0]?.textContent===item.id);
    assert(section,'Section de synthèse absente : '+item.id);
    const nodes=walk(section),rows=nodes.filter(node=>node.tagName==='TR'&&node.className.startsWith('summary-row-'));
    assert.deepEqual(rows.map(node=>node.className),item.expected.map(category=>'summary-row-'+category),'Palette incorrecte pour '+item.id);
    assert(nodes.some(node=>node.tagName==='TR'&&node.className==='summary-head-'+item.header),'En-tête incorrect pour '+item.id);
    assert(section.className.includes('summary-section-'+item.header));
    assert(rows.every(node=>Object.keys(node.style).length===0),'Les lignes doivent utiliser des classes, pas des styles injectés');
  }
  assert(html.includes('.summary-table .summary-row-diver>*{background:#eaf4e9}'));
  assert(html.includes('.summary-table .summary-row-instructor>*{background:#edf3fb}'));
  assert(html.includes('.summary-table .summary-row-young>*{background:#fff5ce}'));
  assert(html.includes('.summary-table .summary-head-young th{background:#f0d26b;color:#3b3007}'),'Les en-têtes jaunes doivent garder un texte foncé');
  for(const [category,background]of [['correct','#edf8ef'],['wrong','#fff0f0'],['partial','#fff4e0']])assert(html.match(new RegExp('\\.'+category+'\\{([^}]+)\\}'))[1].includes('background:'+background),'Les couleurs de correction QCM doivent rester inchangées');
  const normalQuestion=currentQ,resetsBeforeReview=calls.filter(action=>action==='reset'||action==='restart').length;
  get('session-menu').click();await flush();get('start-review').click();await flush();
  assert.equal(get('question').textContent,'Question 6');assert(get('phase').textContent.startsWith('Révision'));assert.equal(get('end-review').hidden,false);
  get('next').click();await flush();assert.equal(get('question').textContent,'Question 6','Une session de révision ne doit pas introduire une question nouvelle');
  get('end-review').click();await flush();assert.equal(get('question').textContent,'Question '+normalQuestion);assert.equal(get('end-review').hidden,true);assert(!get('phase').textContent.startsWith('Révision'));
  assert.equal(calls.filter(action=>action==='reset'||action==='restart').length,resetsBeforeReview,'Terminer la révision ne doit pas réinitialiser la progression');
  reviewAvailable=false;get('session-menu').click();await flush();assert.equal(get('start-review').disabled,true);const reviewCalls=calls.filter(action=>action==='start-review').length;get('start-review').click();await flush();assert.equal(calls.filter(action=>action==='start-review').length,reviewCalls);
  reviewAvailable='missing';get('session-menu').click();await flush();assert.equal(get('start-review').disabled,false,'Compatibilité avec une ancienne API disposant de réponses mais sans review_available');
  assert.equal(vm.runInContext("resultDate(null)",context),'date inconnue');assert.equal(vm.runInContext("resultDate('invalid')",context),'date inconnue');assert(vm.runInContext("resultDate('2026-07-01T10:15:00Z')",context).includes('12:15'),'Le fuseau Paris doit respecter l’heure d’été');
  context.missingDateStatus={...status,last_answer_at:null};vm.runInContext("status(missingDateStatus,'normal')",context);assert.equal(get('points-date').textContent,'Dernier résultat : date inconnue');
  console.log('Interface OK : dates Paris et inconnues, session révision et reprise sans reset, palette, PDF, multisélection, numérotation et toggles préservés.');
})().catch(e=>{console.error(e);process.exitCode=1;});
