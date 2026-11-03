'use strict';
const number = new Intl.NumberFormat('en-US');
const byId = id => document.getElementById(id);
const setText = (id, value) => { byId(id).textContent = value; };
const methods = [
  {key:'direct',label:'Direct API*',subtitle:'Closest baseline: generic + basic checks',color:'direct'},
  {key:'original',label:'With EGM',subtitle:'Original adapter + basic checks',color:'original'},
  {key:'grounded',label:'EGM + harness',subtitle:'Grounded evidence contract',color:'grounded'}
];
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function pct(n,d) { const v = n/d*100; return (Number.isInteger(v) ? v.toFixed(0) : v.toFixed(1)) + '%'; }
function bars(id,suite,field) {
  const parent=byId(id); parent.replaceChildren();
  const maximum=Math.max(...methods.map(m => suite[m.key]?.[field] ?? 0),1);
  for (const method of methods) {
    const data=suite[method.key], value=data?.[field];
    const missing=value === null || value === undefined;
    const row=el('div','bar-row'+(missing?' missing-row':''));
    row.append(el('span','',method.label));
    if (missing) {
      const track=el('div','missing-bar'); track.setAttribute('aria-hidden','true'); row.append(track);
      row.append(el('strong','',data?'Not audited':'Not measured'));
    } else {
      const track=el('div','bar-track'), bar=el('div','bar '+method.color+'-bar');
      bar.style.width=value/maximum*100+'%'; track.append(bar); track.setAttribute('aria-hidden','true');
      row.append(track,el('strong','',number.format(value)));
    }
    parent.append(row);
  }
}
function selectSuite(name) {
  const suite=window.HARNESS_DATA.suites[name]; if(!suite) return;
  document.querySelectorAll('[data-suite]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.suite===name)));
  setText('suite-description',suite.description);
  const cards=byId('scorecards'); cards.replaceChildren();
  for(const method of methods) {
    const data=suite[method.key], card=el('article','scorecard '+method.color+'-score');
    card.append(el('h3','',method.label),el('p','score-subtitle',method.subtitle));
    card.append(el('strong','score-value'+(!data?' missing':''),data?pct(data.detected,data.expected):'Not measured'));
    card.append(el('p','score-caption',data?data.detected+' / '+data.expected+' planted bugs detected':'No recorded baseline for these designs'));
    card.append(el('p','score-bottom',data?number.format(data.tokens)+' tokens · '+data.attempts+' HTTP attempts': 'No detection, token, or warning score is inferred.'));
    cards.append(card);
  }
  bars('warning-bars',suite,'unsupported'); bars('token-bars',suite,'tokens');
  setText('warning-caption',suite.direct?'The generic baseline has no complete finding-by-finding unsupported-warning count. Its missing bar is not zero.':'Only the two EGM modes were measured and audited on this pair.');
  const metrics=[
    ['Planted bugs detected',v=>v.detected+' / '+v.expected+' ('+pct(v.detected,v.expected)+')'],
    ['Completed design reviews',v=>v.completed+' / '+v.cases],
    ['Unsupported major / blocker findings',v=>v.unsupported===null?'Not audited':v.unsupported],
    ['All major / blocker findings',v=>v.major],
    ['Minor comments',v=>v.minor],
    ['Reviewer invocations',v=>v.invocations],
    ['Valid on the first response',v=>v.firstValid+' / '+v.invocations+' ('+pct(v.firstValid,v.invocations)+')'],
    ['Valid after allowed correction',v=>v.finalValid+' / '+v.invocations+' ('+pct(v.finalValid,v.invocations)+')'],
    ['Correction calls',v=>v.corrections],
    ['Total HTTP attempts',v=>v.attempts],
    ['Reported tokens',v=>number.format(v.tokens)],
    ['Corrected counterparts with major alerts¹',v=>v.controls+' / '+v.controlTotal]
  ];
  const tbody=byId('metrics-body'); tbody.replaceChildren();
  for(const [label,render] of metrics) {
    const row=el('tr'), heading=el('th','',label);heading.scope='row';row.append(heading);
    for(const method of methods) {
      const data=suite[method.key], value=data?render(data):'Not measured';
      row.append(el('td',typeof value==='string'&&value.startsWith('Not ')?'unmeasured':'',value));
    }
    tbody.append(row);
  }
  const original=suite.original,grounded=suite.grounded;
  const reduction=(original.unsupported-grounded.unsupported)/original.unsupported*100;
  setText('warning-reduction',reduction.toFixed(0)+'% fewer');
  setText('warning-formula','('+original.unsupported+' − '+grounded.unsupported+') ÷ '+original.unsupported+' × 100. Fewer assistant-audited unsupported serious warnings; not an overall accuracy score.');
  setText('token-increase','+'+((grounded.tokens/original.tokens-1)*100).toFixed(1)+'% tokens');
  setText('token-context',suite.direct?'Grounded EGM used '+(grounded.tokens/suite.direct.tokens).toFixed(2)+'× the tokens of the saved single-review baseline and '+(grounded.tokens/original.tokens).toFixed(2)+'× original EGM.':'Grounded EGM used '+number.format(grounded.tokens-original.tokens)+' more tokens than original EGM. There is no direct API baseline here.');
  setText('detection-uplift','0 percentage points');
  setText('detection-context',suite.direct?'All three saved implementations found the same six planted bugs. This does not establish equal performance on unseen bugs.':'Both EGM modes found both planted bugs. Detection uplift over a direct API call was not measured.');
}
document.querySelectorAll('[data-suite]').forEach(b=>b.addEventListener('click',()=>selectSuite(b.dataset.suite)));
const steps=[
 {stock:'1',label:'One item is available',a:'Ready to reserve',b:'Ready to reserve',description:'Two customers want the last item. Each request will check the stock before reserving it.'},
 {stock:'1',label:'Both requests see the same item',a:'Reads stock = 1',b:'Reads stock = 1',description:'Both requests read “1 available” before either updates the stock. Each decides its reservation can proceed.'},
 {stock:'−1',label:'The inventory requirement is broken',a:'Reservation accepted',b:'Reservation accepted',description:'Each update subtracts one without rechecking availability. Both reservations commit, leaving negative stock. An atomic check-and-update prevents this execution.'}
];
let step=0;
function renderStep() {
 const s=steps[step];setText('stock-number',s.stock);byId('stock-number').classList.toggle('negative',step===2);
 setText('stock-label',s.label);setText('customer-a',s.a);setText('customer-b',s.b);setText('step-description',s.description);
 setText('step-position','0'+(step+1)+' / 03');byId('previous-step').disabled=step===0;
 setText('next-step',step===2?'Replay ↺':'Next step →');
 document.querySelectorAll('.step-dots span').forEach((dot,i)=>dot.classList.toggle('active',i===step));
}
byId('previous-step').addEventListener('click',()=>{step=Math.max(0,step-1);renderStep();});
byId('next-step').addEventListener('click',()=>{step=(step+1)%steps.length;renderStep();});
byId('step-description').setAttribute('aria-live','polite');
function argument(label,text,kind='p') {const div=el('div','argument');div.append(el('span','argument-label',label),el(kind,'',text));return div;}
function selectReview(mode) {
 document.querySelectorAll('[data-review]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.review===mode)));
 const c=byId('review-content'),sample=window.HARNESS_DATA.example;c.replaceChildren();
 setText('finding-status',mode==='direct'?'NOT MEASURED':'BLOCKER');
 setText('finding-category',mode==='direct'?'EVIDENCE GAP':'RELIABILITY');
 setText('finding-title',mode==='direct'?'No direct API result was recorded for this case.':'Concurrent reservations can make stock negative.');
 if(mode==='direct') {
   c.append(argument('WHAT A RAW CALL WOULD DO','Send the design and one generic review prompt, then return the model response without application-level validation or correction.'));
   c.append(argument('WHAT WE CAN ACTUALLY SHOW','The inventory pair was tested only with original and grounded EGM. We cannot infer whether one raw call would detect this bug or invent a model response.'));
   c.append(argument('AVAILABLE COMPARISON','On the six earlier designs, the saved single-review baseline found 6/6 planted bugs. That baseline included basic validation and repair.'));
 } else if(mode==='grounded') {
   c.append(argument('PASSAGE / BOUND TO THIS DOCUMENT',sample.passageId,'code'));
   c.append(argument('REQUIREMENT','Available stock must never become negative.'));
   c.append(argument('FAILURE SCENARIO','Stock is 1. Two requests both read 1, then each subtracts 1 without rechecking. Both commit; stock becomes −1.'));
   c.append(argument('RECOMMENDATION','Combine the availability check and decrement in one atomic database update.'));
 } else {
   c.append(argument('EXACT QUOTE / DESIGN',sample.quote,'blockquote'));
   c.append(argument('ISSUE','The separate availability check and unguarded decrement allow concurrent requests to make stock negative.'));
   c.append(argument('RECOMMENDATION','Lock the stock row or use a conditional update, then verify that one row was updated.'));
 }
 setText('example-note',mode==='direct'?'Explanation of the setup and evidence gap; not a generated model answer.':'Condensed from the recorded inventory finding. The failure scenario still needs human inspection.');
}
document.querySelectorAll('[data-review]').forEach(b=>b.addEventListener('click',()=>selectReview(b.dataset.review)));
selectSuite('development');selectReview('grounded');

