'use strict';
const data=window.BUILD_DATA;
const $=id=>document.getElementById(id);
const assignments={A:'egm',B:'direct',C:'grounded'};
const names={direct:'Direct API',egm:'With EGM',grounded:'EGM + harness'};
let selected=data?.arms?.egm?'A':data?.arms?.direct?'B':'A',revealed=false,favorite=null,runToken='',checkTimer=null;
const pageState={};
const checksByVersion={};
$('build-progress').textContent=Object.keys(data.arms).length+' / 3 BUILDS READY · THE PLAYGROUND';
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function testBridge(token){
  const id=s=>document.getElementById(s),rows=()=>Array.from(document.querySelectorAll('[data-task-id]'));
  const pause=()=>new Promise(r=>setTimeout(r,40));
  const requireEl=s=>{const e=id(s);if(!e)throw Error('Missing required #'+s);return e;};
  const counts=()=>['count-total','count-active','count-done'].map(s=>Number(requireEl(s).textContent.trim()));
  const click=async s=>{requireEl(s).click();await pause();};
  const fill=async(s,text)=>{const e=requireEl(s);e.value=text;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));await pause();};
  const assert=(v,message)=>{if(!v)throw Error(message);};
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const results=[];
  const test=async(label,fn)=>{try{await fn();results.push({label,pass:true});}catch(e){results.push({label,pass:false,detail:e.message});}};
  async function run(){
    await test('Three initial tasks and accurate counts',async()=>{assert(rows().length===3,'Expected three visible task rows');assert(same(counts(),[3,3,0]),'Expected total 3, active 3, done 0');});
    await test('Add task updates the list and counters',async()=>{await fill('task-title','  Plan the demo  ');await click('add-task');assert(rows().some(r=>r.textContent.includes('Plan the demo')),'Added task missing');assert(same(counts(),[4,4,0]),'Counts incorrect after add');});
    await test('Blank titles are rejected',async()=>{const before=counts();await fill('task-title','   ');await click('add-task');assert(same(counts(),before),'Blank title added a task');});
    await test('Complete task updates both counters',async()=>{const target=rows().find(r=>r.textContent.includes('Plan the demo'));assert(target,'New task missing');const box=target.querySelector('input[type=checkbox]');assert(box,'No real checkbox');box.click();await pause();assert(same(counts(),[4,3,1]),'Completion counters incorrect');});
    await test('Done filter shows only completed tasks',async()=>{await click('filter-done');assert(rows().length===1&&rows()[0].textContent.includes('Plan the demo'),'Done filter shows wrong rows');assert(same(counts(),[4,3,1]),'Filter changed global counts');});
    await test('Active filter excludes completed tasks',async()=>{await click('filter-active');assert(rows().length===3&&!rows().some(r=>r.textContent.includes('Plan the demo')),'Active filter shows wrong rows');});
    await test('Search combines with filter, ignoring case',async()=>{await fill('task-search','WALKING');assert(rows().length===1&&rows()[0].textContent.includes('walking break'),'Expected walking task');await click('filter-done');assert(rows().length===0,'Completed filter ignored search');});
    await test('Deletion after filtering targets the correct task',async()=>{await click('filter-active');const r=rows()[0];assert(r&&r.textContent.includes('walking break'),'Search target missing');const b=Array.from(r.querySelectorAll('button')).find(e=>(e.getAttribute('aria-label')||e.textContent).trim().startsWith('Delete'));assert(b,'Accessible Delete button missing');b.click();await pause();await fill('task-search','');await click('filter-all');assert(rows().length===3&&!rows().some(r=>r.textContent.includes('walking break')),'Wrong task deleted');assert(same(counts(),[3,2,1]),'Deletion counts incorrect');});
    await test('Task titles render as literal text',async()=>{await fill('task-title','<b>Focus</b>');await click('add-task');const r=rows().find(e=>e.textContent.includes('<b>Focus</b>'));assert(r,'Title interpreted as markup or changed');assert(!Array.from(r.querySelectorAll('b')).some(e=>e.textContent==='Focus'),'User markup was interpreted');});
    await test('No horizontal page overflow at this width',async()=>{assert(document.documentElement.scrollWidth<=innerWidth+2,'Page content overflows viewport');});
    parent.postMessage({kind:'build-check-results',token,results,width:innerWidth},'*');
  }
  async function stress(){await test('Long unbroken title stays within the viewport',async()=>{await fill('task-title','A'.repeat(140));await click('add-task');assert(rows().some(r=>r.textContent.includes('A'.repeat(140))),'Long title was not added');assert(document.documentElement.scrollWidth<=innerWidth+2,'Content width '+document.documentElement.scrollWidth+' px exceeds viewport '+innerWidth+' px');});parent.postMessage({kind:'build-stress-results',token,results,width:innerWidth},'*');}
  window.addEventListener('message',e=>{if(e.source!==parent||e.data?.token!==token)return;if(e.data.kind==='run-build-checks')run();if(e.data.kind==='run-build-stress')stress();});
  parent.postMessage({kind:'build-ready',token},'*');
}
function frameDocument(html,token){
  const policy="<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'\">";
  const bridge='<script>('+testBridge.toString()+')('+JSON.stringify(token)+');<\/script>';
  // Same safety envelope and test bridge for all outputs; original downloads stay unchanged.
  return html.replace(/<head[^>]*>/i,match=>match+policy).replace(/<\/body>/i,bridge+'</body>');
}
function showChecks(letter){
  const container=$('checks');container.replaceChildren();const record=checksByVersion[letter];if(!record)return;
  container.append(node('strong',record.results.filter(r=>r.pass).length+' / '+record.results.length+' checks passed · tested at '+record.width+' px','check-summary'));
  for(const result of record.results){const row=node('div',undefined,'check-row'+(result.pass?'':' fail'));row.append(node('b',result.pass?'✓':'×'),node('span',result.label+(result.detail?' — '+result.detail:'')));container.append(row);}
}
function mount(check=false,stress=false){
  clearTimeout(checkTimer);$('check').disabled=false;$('stress').disabled=false;pageState.stressToken=null;$('stress-result').textContent='';
  const arm=data?.arms?.[assignments[selected]];
  runToken=crypto.randomUUID();
  $('preview').title='Version '+selected+' task planner';
  $('frame-label').textContent='Version '+selected+' / '+(revealed?names[assignments[selected]]:'interactive preview');
  $('favorite').textContent='Choose Version '+selected+(favorite===selected?' ♥':' ♡');
  document.querySelectorAll('[data-version]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.version===selected));b.disabled=!data?.arms?.[assignments[b.dataset.version]]?.html;});
  showChecks(selected);
  $('preview').srcdoc=arm?.html?frameDocument(arm.html,runToken):'<html><body style="font:16px Arial;padding:40px"><h2>Generation in progress</h2><p>This build will appear when its model run completes.</p></body></html>';
  if(check){$('check').disabled=true;$('stress').disabled=true;$('checks').replaceChildren(node('p','Running the same interaction sequence…','check-summary'));pageState.checkToken=runToken;checkTimer=setTimeout(()=>{$('check').disabled=false;$('stress').disabled=false;$('checks').replaceChildren(node('p','Checks did not complete. The page may have failed to initialize.','check-summary'));pageState.checkToken=null;},15000);}else pageState.checkToken=null;
  if(stress){$('stress').disabled=true;$('check').disabled=true;pageState.stressToken=runToken;$('stress-result').textContent='Adding the long title and checking layout…';checkTimer=setTimeout(()=>{$('stress').disabled=false;$('check').disabled=false;$('stress-result').textContent='Stress test did not complete.';pageState.stressToken=null;},15000);}
}
function renderResults(){
  const container=$('result-cards');container.replaceChildren();$('review-details').replaceChildren();
  for(const [letter,key] of Object.entries(assignments)){
    const arm=data.arms[key],card=node('article',undefined,'result-card');
    if(!arm){card.append(node('h3','Version '+letter),node('p','Generation in progress.'));container.append(card);continue;}
    card.append(node('div','VERSION '+letter,'card-label'),node('h3',names[key]),node('p',arm.description));
    const dl=node('dl',undefined,'metrics');
    const stats=[['Reported tokens',arm.tokens?.toLocaleString()??'Not reported'],['HTTP attempts',arm.attempts],['Total time',Math.round(arm.seconds)+' s'],['Request time',Math.round(arm.processingSeconds)+' s'],['Revision passes',key==='direct'?0:1],['Review corrections',arm.corrections??0]];
    if(arm.verification){stats.push(['Checks at 837 / 390 px',arm.verification.desktop.split(' checks')[0]+' · '+arm.verification.mobile.split(' checks')[0]],['Long-title stress test',arm.verification.stress.startsWith('PASS')?'Pass':'Fail']);}
    for(const [label,value] of stats){const row=node('div');row.append(node('dt',label),node('dd',String(value)));dl.append(row);}card.append(dl);
    const source=node('a','Download original HTML ↓');source.href='artifacts/'+key+'.html.txt';source.download='daymark-'+key+'.html';card.append(source);container.append(card);
    const review=node('div',undefined,'review-block');review.append(node('h4','Version '+letter+' · '+names[key]));review.append(node('p','Resolved model(s): '+arm.models.join(', ')+'. Routes: '+arm.routes.join(', ')+'.'));
    if(arm.findings?.length){const list=node('ul');for(const f of arm.findings){const li=node('li');li.append(node('strong',f.severity.toUpperCase()+': '),node('span',f.issue+' Suggested change: '+f.recommendation));list.append(li);}review.append(list);}else review.append(node('p',key==='direct'?'No reviewer calls were made for the direct output.':'No findings were returned.'));
    if(key!=='direct'){const changes=node('a','Inspect exact code changes from the initial page ↗');changes.href='artifacts/'+key+'-changes.diff.txt';changes.target='_blank';changes.rel='noopener';review.append(changes);}
    if(arm.note)review.append(node('p',arm.note));$('review-details').append(review);
  }
}
document.querySelectorAll('[data-version]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.version;mount();}));
$('reset').addEventListener('click',()=>mount());
$('mobile').addEventListener('click',()=>{const on=$('viewport').classList.toggle('mobile');$('mobile').setAttribute('aria-pressed',String(on));});
$('favorite').addEventListener('click',()=>{favorite=selected;$('vote-status').textContent='Your choice: Version '+favorite+(revealed?' — '+names[assignments[favorite]]:'. Reveal the methods when you’re ready.')+'.';$('favorite').textContent='Choose Version '+selected+' ♥';});
$('reveal').addEventListener('click',()=>{revealed=!revealed;$('results').hidden=!revealed;$('reveal').textContent=revealed?'Hide the methods':'Reveal the methods ↗';$('frame-label').textContent='Version '+selected+' / '+(revealed?names[assignments[selected]]:'interactive preview');if(favorite)$('vote-status').textContent='Your choice: Version '+favorite+(revealed?' — '+names[assignments[favorite]]:'')+'.';if(revealed){renderResults();$('results').scrollIntoView({behavior:'smooth',block:'start'});}});
$('check').addEventListener('click',()=>mount(true));
$('stress').addEventListener('click',()=>{$('viewport').classList.add('mobile');$('mobile').setAttribute('aria-pressed','true');mount(false,true);});
window.addEventListener('message',e=>{if(e.source!==$('preview').contentWindow||e.data?.token!==runToken)return;if(e.data.kind==='build-ready'&&pageState.checkToken===runToken){$('preview').contentWindow.postMessage({kind:'run-build-checks',token:runToken},'*');}if(e.data.kind==='build-ready'&&pageState.stressToken===runToken){$('preview').contentWindow.postMessage({kind:'run-build-stress',token:runToken},'*');}if(e.data.kind==='build-check-results'&&pageState.checkToken===runToken){clearTimeout(checkTimer);checksByVersion[selected]={results:e.data.results,width:e.data.width};pageState.checkToken=null;$('check').disabled=false;$('stress').disabled=false;showChecks(selected);}if(e.data.kind==='build-stress-results'&&pageState.stressToken===runToken){clearTimeout(checkTimer);pageState.stressToken=null;$('check').disabled=false;$('stress').disabled=false;const r=e.data.results[0];$('stress-result').textContent=(r.pass?'PASS — ':'FAIL — ')+r.label+'. Tested at '+e.data.width+' px.'+(r.detail?' '+r.detail:'');$('stress-result').className='stress-result '+(r.pass?'pass':'fail');}});
mount();
