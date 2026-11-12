// Run with: node --test tests/frontend.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../static/index.html'), 'utf8');

function loadFunctions(context, names) {
  vm.createContext(context);
  for (const name of names) {
    const start = html.search(new RegExp(`^    (?:async )?function ${name}\\(`, 'm'));
    assert.notEqual(start, -1, `Missing function ${name}`);
    const end = html.indexOf('\n    }', start) + '\n    }'.length;
    vm.runInContext(html.slice(start, end), context);
  }
}

function fakeDocument() {
  const elements = new Map();
  return {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, {
        value: '', checked: false, innerHTML: '', dataset: {},
        classList: { add() {}, remove() {}, toggle() {} },
        querySelectorAll() { return []; },
        appendChild() {},
      });
      return elements.get(id);
    },
    createElement(tag) {
      return {
        className: '', innerHTML: '', dataset: {},
        classList: { add() {}, remove() {}, toggle() {} },
        appendChild() {}, addEventListener() {}, setAttribute() {},
      };
    },
  };
}

function deferredResponse() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

test('release status follows the current PDF identity, never the previous green badge', () => {
  const context = {document:fakeDocument()};
  vm.createContext(context);
  const start = html.indexOf('    function renderResults(data) {');
  const end = html.indexOf("      const tacStatus =", start);
  vm.runInContext(html.slice(start,end) + '\n    }',context);
  const badge=context.document.getElementById('badgeRelease');
  badge.textContent='AUTHORIZED';
  context.renderResults({job_meta:{job_id:'B',current_sha256:'new'},triple_result:{release:{status:'PENDING_AUTHORIZATION'}}});
  assert.equal(badge.textContent,'PENDIENTE');
  context.renderResults({job_meta:{job_id:'B',current_sha256:'new',authorized_sha256:'old'},triple_result:{release:{status:'AUTHORIZED'}}});
  assert.equal(badge.textContent,'PENDIENTE');
  context.renderResults({job_meta:{job_id:'B',current_sha256:'new',authorized_sha256:'new'},triple_result:{release:{status:'AUTHORIZED',label:'Verified'}}});
  assert.equal(badge.textContent,'AUTHORIZED');
});

for (const name of ['applyCmykImageConversion','applyHairlineFix','applyFontOutlineFix','applyPrinterMarks']) {
  test(`${name} ignores a late response and releases its button`, async () => {
    const pending=deferredResponse(), original=inspectorReport('A'), next=inspectorReport('B');
    const context={currentJobId:'A',currentReport:original,document:fakeDocument(),console,
      alert:assert.fail,renderResults:assert.fail,fetch:()=>pending.promise};
    loadFunctions(context,[name]);
    const btn={innerHTML:'Correct',disabled:false,closest(){ return null; }};
    const work=context[name](btn);
    context.currentJobId='B';context.currentReport=next;
    pending.resolve({ok:true,json:async()=>({status:'success',report:original})});
    await work;
    assert.equal(context.currentJobId,'B');
    assert.equal(context.currentReport,next);
    assert.equal(btn.disabled,false);
    assert.equal(btn.innerHTML,'Correct');
  });
}

test('deleted selected profiles fall back to an existing radio', async () => {
  const document=fakeDocument();
  document.querySelector=()=>({value:'DELETED'});
  const context={document,console,cachedTargetProfiles:[],fetch:async()=>({json:async()=>({profiles:[{id:'OFFSET_300',name:'Offset'}]})})};
  loadFunctions(context,['escapeHtml','loadTargetProfiles']);
  await context.loadTargetProfiles();
  assert.match(document.getElementById('targetProfilesContainer').innerHTML,/value="OFFSET_300" checked/);
});

test('inventory uses measured profile criteria and the requested color family', () => {
  const start=html.indexOf('            const targetDpi =');
  const end=html.indexOf('            imagesTbody.appendChild(tr);',start);
  const context={csBadge:'',tr:{},escapeHtml:value=>String(value)};
  vm.createContext(context);
  vm.runInContext('function row(data,img) { '+html.slice(start,end)+' return tr.innerHTML; }',context);
  const image={effective_dpi:400,is_cmyk:true,placed_mm:'20 x 20',colorspace:'CMYK'};
  const low=context.row({job_summary:{target_dpi:600,required_color_family:'CMYK'}},image);
  assert.match(low,/insuficiente/);
  const screen=context.row({job_summary:{target_dpi:96,required_color_family:'RGB'}},{...image,effective_dpi:96,is_cmyk:false,is_rgb:true});
  assert.doesNotMatch(screen,/Requiere.*CMYK/);
  assert.match(screen,/Óptima/);
  assert.match(context.row({job_summary:{target_dpi:96,required_color_family:'RGB'}},image),/sRGB/);
});

function inspectorReport(jobId, limit=320, profile='OFFSET_300') {
  return {job_meta:{job_id:jobId,profile_id:profile},
    job_summary:{max_tac_limit:limit},triple_result:{technical:{status:'FAIL'}},findings:[]};
}

test('loading a batch job changes its ID and criteria together and uses its TAC limit', async () => {
  const document=fakeDocument(), pending=deferredResponse(), old=inspectorReport('old',240);
  const next=inspectorReport('next',320);
  const calls=[];
  const context={document,currentJobId:'old',currentReport:old,console,alert:assert.fail,
    closeBatchHotfolderModal(){},renderResults(){},showTacCorrectionResult(){},
    fetch:async url=>{
      calls.push(url);
      if(url.includes('/api/report/')) return pending.promise;
      return {ok:true,json:async()=>({status:'success',report:next})};
    }};
  loadFunctions(context,['loadBatchJobIntoInspector','getTacLimit','applyTacLimiter']);
  const loading=context.loadBatchJobIntoInspector('next');
  assert.equal(context.currentJobId,'old');
  assert.equal(context.currentReport,old);
  pending.resolve({ok:true,json:async()=>next});
  await loading;
  assert.equal(context.currentJobId,'next');
  assert.equal(context.currentReport,next);
  await context.applyTacLimiter({innerHTML:'Limitar'});
  assert.equal(calls[1],'/api/limit-tac/next?max_tac=320');
});

test('opening a screen job from the batch does not inherit bleed and crop marks', async () => {
  const document=fakeDocument();
  const report=inspectorReport('screen',240,'PANTALLA_RGB');
  const context={document,currentJobId:'old',currentReport:inspectorReport('old'),console,
    cachedTargetProfiles:[{id:'PANTALLA_RGB',color_family:'RGB',min_bleed_mm:0}],
    closeBatchHotfolderModal(){},renderResults(){},alert:assert.fail,
    fetch:async()=>({ok:true,json:async()=>report})};
  loadFunctions(context,['loadBatchJobIntoInspector','openBatchFixModal']);
  await context.loadBatchJobIntoInspector('screen');
  context.openBatchFixModal();
  assert.equal(document.getElementById('batchChkMirrorBleed').checked,false);
  assert.equal(document.getElementById('batchChkMarks').checked,false);
});

test('late batch responses never replace the most recently selected job', async () => {
  const b=deferredResponse(),c=deferredResponse(),rendered=[];
  const context={currentJobId:'old',currentReport:inspectorReport('old'),console,
    fetch:url=>url.endsWith('/b')?b.promise:c.promise,
    closeBatchHotfolderModal(){},renderResults:r=>rendered.push(r.job_meta.job_id),alert:assert.fail};
  loadFunctions(context,['loadBatchJobIntoInspector']);
  const loadingB=context.loadBatchJobIntoInspector('b');
  const loadingC=context.loadBatchJobIntoInspector('c');
  c.resolve({ok:true,json:async()=>inspectorReport('c')});
  await loadingC;
  b.resolve({ok:true,json:async()=>inspectorReport('b')});
  await loadingB;
  assert.deepEqual(rendered,['c']);
  assert.equal(context.currentJobId,'c');
  assert.equal(context.currentReport.job_meta.job_id,'c');
});

test('failed or mismatched batch reports preserve the previous active job', async () => {
  for(const response of [{ok:false},{ok:true,json:async()=>inspectorReport('other')},
                         {ok:true,json:async()=>({triple_result:{}})}]) {
    const old=inspectorReport('old');let alerts=0;
    const context={currentJobId:'old',currentReport:old,console:{error(){}},
      fetch:async()=>response,closeBatchHotfolderModal:assert.fail,renderResults:assert.fail,
      alert(){alerts++;}};
    loadFunctions(context,['loadBatchJobIntoInspector']);
    await context.loadBatchJobIntoInspector('next');
    assert.equal(context.currentJobId,'old');assert.equal(context.currentReport,old);
    assert.equal(alerts,1);
  }
});

test('the workshop refreshes the main report and retains verified remaining errors', async () => {
  const document=fakeDocument(), corrected=inspectorReport('job',240),rendered=[];
  corrected.findings=[{rule_id:'MAX_INK_COVERAGE',severity:'ERROR'}];
  document.getElementById('tab-comparison').classList.contains=()=>true;
  document.getElementById('batchResultArea').scrollIntoView=()=>{};
  const context={document,currentJobId:'job',currentReport:inspectorReport('job'),console,
    URLSearchParams,setTimeout:fn=>fn(),renderResults:r=>rendered.push(r),
    fetch:async()=>({ok:true,text:async()=>JSON.stringify({success:true,report:corrected,
      verdict:'RECHAZADO',errors_count:1,warnings_count:0,pending_errors:corrected.findings})})};
  loadFunctions(context,['executeBatchFix','escapeHtml']);
  await context.executeBatchFix({innerHTML:'Aplicar'});
  assert.equal(rendered.length,1);
  assert.equal(context.currentReport.job_summary.max_tac_limit,240);
  assert.equal(context.currentReport.findings[0].rule_id,'MAX_INK_COVERAGE');
  assert.ok(document.getElementById('batchResultContent').innerHTML.includes('RECHAZADO'));
  assert.equal(document.getElementById('downloadPdfBtnLabel').textContent,'Descargar PDF corregido');
});

test('workshop results for a previously active job do not overwrite another report', async () => {
  const document=fakeDocument(),pending=deferredResponse();
  const context={document,currentJobId:'old',currentReport:inspectorReport('old'),console,
    URLSearchParams,fetch:()=>pending.promise,renderResults:assert.fail};
  loadFunctions(context,['executeBatchFix']);
  const button={innerHTML:'Aplicar'};
  const applying=context.executeBatchFix(button);
  context.currentJobId='new';context.currentReport=inspectorReport('new',240);
  pending.resolve({ok:true,text:async()=>JSON.stringify({success:true,report:inspectorReport('old')})});
  await applying;
  assert.equal(context.currentReport.job_meta.job_id,'new');
  assert.equal(button.disabled,false);
});

test('barcode corrections refresh the main report and its current PDF hash', async () => {
  const document=fakeDocument(), report=inspectorReport('job'),rendered=[];
  report.job_meta.current_sha256='b'.repeat(64);
  const context={document,currentJobId:'job',currentReport:inspectorReport('job'),console,
    renderResults:r=>rendered.push(r),loadBarcodeInspection:async()=>{},alert:assert.fail,
    fetch:async()=>({ok:true,json:async()=>({status:'success',report})})};
  loadFunctions(context,['executeFixBarcodes']);
  await context.executeFixBarcodes();
  assert.equal(context.currentReport,report);
  assert.equal(rendered[0].job_meta.current_sha256,'b'.repeat(64));
});

test('all inline JavaScript parses', () => {
  for (const script of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    if (!/\bsrc\s*=/.test(script[1])) new vm.Script(script[2]);
  }
});

for (const profile of [
  {id:'OFFSET_300',color_family:'CMYK',min_bleed_mm:3,bleed:true,marks:true},
  {id:'PANTALLA_RGB',color_family:'RGB',min_bleed_mm:0,bleed:false,marks:false},
  {id:'CUSTOM_RGB',color_family:'RGB',min_bleed_mm:0,bleed:false,marks:false},
  {id:'CUSTOM_ZERO',color_family:'CMYK',min_bleed_mm:0,bleed:false,marks:true},
]) {
  test(`the workshop selects bleed and crop marks for ${profile.id}`, () => {
    const document=fakeDocument();
    const context={document,currentJobId:'first',currentReport:{job_meta:{profile_id:profile.id}},
      cachedTargetProfiles:[profile],alert:assert.fail};
    loadFunctions(context,['openBatchFixModal']);
    context.openBatchFixModal();
    assert.equal(document.getElementById('batchChkMirrorBleed').checked,profile.bleed);
    assert.equal(document.getElementById('batchChkMarks').checked,profile.marks);
    document.getElementById('batchChkMarks').checked=false;
    context.openBatchFixModal();
    assert.equal(document.getElementById('batchChkMarks').checked,false,'Keep the operator choice for this job');
    context.currentJobId='second';context.openBatchFixModal();
    assert.equal(document.getElementById('batchChkMarks').checked,profile.marks);
  });
}

test('the complete manual loads on first opening and keeps the reading position', () => {
  const document = fakeDocument();
  const reader = document.getElementById('manualReader');
  reader.dataset = { src: '/manual?embed=1' };
  reader.getAttribute = () => reader.src;
  const context = { document };
  loadFunctions(context, ['openManualModal', 'closeManualModal']);
  context.openManualModal();
  assert.equal(reader.src, '/manual?embed=1');
  reader.src = '/manual?embed=1#6-modulos-de-produccion';
  context.closeManualModal();
  context.openManualModal();
  assert.equal(reader.src, '/manual?embed=1#6-modulos-de-produccion');
});

test('imported profile markup is inert and selection uses the literal ID', () => {
  const document = fakeDocument();
  const attack = `<img src=x onerror="alert('xss')">`;
  const id = `CUSTOM_');alert(1);//" onmouseover="alert(2)`;
  let clicked;
  let handler;
  const context = { document, currentSelectedProfileId: null, selectProfileInManager: value => { clicked = value; } };
  loadFunctions(context, ['escapeHtml', 'renderProfileManagerList']);
  const container = document.getElementById('pmProfilesList');
  container.querySelectorAll = () => [{ dataset: { profileId: id }, addEventListener: (name, fn) => { handler = fn; } }];
  context.renderProfileManagerList([{ id, name: attack, destination: attack, target_dpi: attack, min_bleed_mm: attack, max_tac: attack, is_custom: true }]);
  assert.ok(!container.innerHTML.includes('<img'));
  assert.ok(!container.innerHTML.includes('onclick='));
  assert.ok(!container.innerHTML.includes('" onmouseover="'));
  assert.ok(container.innerHTML.includes('&lt;img'));
  handler();
  assert.equal(clicked, id);
});

test('zero margins remain zero when loading and saving the form', async () => {
  const document = fakeDocument();
  let payload;
  const context = {
    document, currentSelectedProfileId: null,
    fetch: async (url, options) => {
      payload = JSON.parse(options.body);
      return { ok: true, json: async () => ({ profile: { id: 'CUSTOM_test' } }) };
    },
    refreshProfileManagerList: async () => {}, loadTargetProfiles: async () => {},
    alert() {},
  };
  loadFunctions(context, ['loadProfileIntoForm', 'saveCustomProfileFromForm']);
  context.loadProfileIntoForm({ id: 'CUSTOM_test', name: 'Pantalla', min_bleed_mm: 0, safety_margin_mm: 0, is_custom: true });
  assert.equal(document.getElementById('pmBleedInput').value, 0);
  assert.equal(document.getElementById('pmSafetyInput').value, 0);
  // Browser input values are strings.
  document.getElementById('pmBleedInput').value = '0';
  document.getElementById('pmSafetyInput').value = '0';
  await context.saveCustomProfileFromForm();
  assert.equal(payload.min_bleed_mm, 0);
  assert.equal(payload.safety_margin_mm, 0);
});

for (const name of ['applyCmykImageConversion', 'convertImagesToCmyk', 'applyTacLimiter', 'applyFontOutlineFix']) {
  test(`${name} displays the verified report even when errors remain`, async () => {
    const document = fakeDocument();
    const report = { findings: [{ title: 'RGB pendiente' }], triple_result: { technical: { status: 'FAIL' } } };
    let rendered;
    const context = {
      document, FormData, currentJobId: 'test', currentReport: null,
      fetch: async () => ({ ok: true, json: async () => ({ status: 'success', report, images_converted: 0, errors: [] }) }),
      renderResults: data => { rendered = data; }, updateSeparationPreview() {},
      alert: message => assert.fail(message), console,
    };
    loadFunctions(context, name === 'applyTacLimiter' ? ['getTacLimit', 'showTacCorrectionResult', name] : [name]);
    await context[name]({ innerHTML: 'Convertir', closest: () => null });
    assert.equal(rendered, report);
    assert.equal(context.currentReport.triple_result.technical.status, 'FAIL');
    assert.equal(context.currentReport.findings.length, 1);
  });
}

test('TAC findings offer correction using the profile limit and plain scope', () => {
  const context = {};
  loadFunctions(context, ['getTacLimit', 'renderTacCorrectionAction']);
  for (const limit of [240,300,320]) {
    const markup = context.renderTacCorrectionAction({job_summary:{max_tac_limit:limit}});
    assert.ok(markup.includes(`Limitar TAC a ${limit} %`));
    assert.ok(markup.includes('onclick="applyTacLimiter(this)"'));
    assert.ok(markup.includes('imágenes CMYK'));
  }
  for (const value of [null, NaN, 0, 999, '<img>']) {
    assert.equal(context.getTacLimit({job_summary:{max_tac_limit:value}}),300);
  }
});

test('TAC correction posts 320 percent and reports a remaining excess honestly', async () => {
  const document=fakeDocument();
  const report={job_summary:{max_tac_limit:320,tac_measurement:{measured:true,peak_percent:346.7}},
    findings:[{rule_id:'MAX_INK_COVERAGE'}]};
  let requested;
  const context={document,currentJobId:'digital',currentReport:report,renderResults(){},
    fetch:async url=>{requested=url;return {ok:true,json:async()=>({status:'success',report,images_clamped:0,target_max_tac:320})}},
    alert:assert.fail,console};
  loadFunctions(context,['getTacLimit','showTacCorrectionResult','applyTacLimiter']);
  const button={innerHTML:'Limitar TAC a 320 %'};
  await context.applyTacLimiter(button);
  assert.equal(requested,'/api/limit-tac/digital?max_tac=320');
  assert.equal(button.disabled,false);
  const status=document.getElementById('tacCorrectionStatus');
  assert.ok(status.textContent.includes('346.7 %'));
  assert.ok(status.textContent.includes('el error permanece pendiente'));
  assert.ok(!status.className.includes('emerald'));
});

test('TAC feedback confirms a measured result and never approves an unmeasured one', () => {
  const document=fakeDocument();
  const context={document};
  loadFunctions(context,['showTacCorrectionResult']);
  const report={findings:[],job_summary:{tac_measurement:{measured:true,peak_percent:319.6}}};
  context.showTacCorrectionResult({images_clamped:1,target_max_tac:320},report,320);
  const status=document.getElementById('tacCorrectionStatus');
  assert.ok(status.className.includes('emerald'));
  assert.ok(status.textContent.includes('319.6 %'));
  report.job_summary.tac_measurement={measured:false};
  context.showTacCorrectionResult({images_clamped:1,target_max_tac:320},report,320);
  assert.ok(!status.className.includes('emerald'));
  assert.ok(status.textContent.includes('No se ha podido verificar'));
});

test('mass correction preserves individual failed and rejected outcomes', async () => {
  const context = {
    batchQueueItems: [
      { job_id: 'failed', status: 'REJECTED', errors_count: 3 },
      { job_id: 'rejected', status: 'REJECTED', errors_count: 2 },
      { job_id: 'passed', status: 'REJECTED', errors_count: 1 },
    ],
    fetch: async () => ({ ok: true, json: async () => ({ status: 'success', results: [
      { job_id: 'failed', status: 'error', errors_count: 1, message: 'Conversion failed' },
      { job_id: 'rejected', status: 'success', technical_status: 'FAIL', errors_count: 2, warnings_count: 1, summary: 'NO CUMPLE' },
      { job_id: 'passed', status: 'success', technical_status: 'PASS', errors_count: 0, warnings_count: 0, summary: 'CUMPLE' },
    ] }) }),
    renderBatchQueueTable() {}, alert() {}, console,
  };
  loadFunctions(context, ['executeBatchFixAll']);
  await context.executeBatchFixAll({ innerHTML: 'Corregir' });
  assert.equal(context.batchQueueItems[0].status, 'ERROR');
  assert.equal(context.batchQueueItems[1].status, 'REJECTED');
  assert.equal(context.batchQueueItems[1].errors_count, 2);
  assert.equal(context.batchQueueItems[2].status, 'FIXED');
});

test('omitted mass correction results remain errors', async () => {
  const context = {
    batchQueueItems: [{ job_id: 'missing', errors_count: 3 }],
    fetch: async () => ({ ok: true, json: async () => ({ status: 'success', results: [] }) }),
    renderBatchQueueTable() {}, alert() {}, console,
  };
  loadFunctions(context, ['executeBatchFixAll']);
  await context.executeBatchFixAll({ innerHTML: 'Corregir' });
  assert.equal(context.batchQueueItems[0].status, 'ERROR');
  assert.equal(context.batchQueueItems[0].errors_count, 3);
});

const maliciousText = `<img src=x onerror="alert(1)">'&`;

function assertInert(markup) {
  assert.ok(!markup.includes('<img src=x'), 'Untrusted text must not become an element');
  assert.ok(markup.includes('&lt;img'), 'Display the literal text, do not silently remove it');
}

test('the main profile selector escapes names, descriptions and attribute values', async () => {
  const document = fakeDocument();
  document.querySelector = () => null;
  const id = `CUSTOM_" autofocus onfocus="alert(1)`;
  const context = { document, console, cachedTargetProfiles: [],
    fetch: async () => ({ json: async () => ({ profiles: [{ id, name: maliciousText,
      destination: maliciousText, is_custom: true }] }) }) };
  loadFunctions(context, ['escapeHtml', 'loadTargetProfiles']);
  await context.loadTargetProfiles();
  const markup = document.getElementById('targetProfilesContainer').innerHTML;
  assertInert(markup);
  assert.ok(!markup.includes('value="' + id + '"'));
  assert.ok(markup.includes('CUSTOM_&quot; autofocus'));
});

test('instant PDF inspection escapes the ICC in both messages', async () => {
  const document = fakeDocument();
  const context = { document, console, selectedFile: null, FormData: class { append() {} },
    fileName: {}, filePrompt: document.getElementById('prompt'), fileInfo: document.getElementById('info'),
    startCheckBtn: {}, fetch: async () => ({ ok: true, json: async () => ({
      output_intent: { has_output_intent: true, icc_valid: true, friendly_description: maliciousText }, pages: 1 }) }) };
  loadFunctions(context, ['escapeHtml', 'handleFileSelect']);
  await context.handleFileSelect({ name: 'safe.pdf', size: 100 });
  assertInert(document.getElementById('fileDetectedIcc').innerHTML);
  assertInert(document.getElementById('preserveIccHint').innerHTML);
});

test('an OutputIntent label without a valid embedded profile never gets a green ICC badge', async () => {
  const document = fakeDocument();
  const context = { document, console, selectedFile: null, FormData: class { append() {} },
    fileName: {}, filePrompt: document.getElementById('prompt'), fileInfo: document.getElementById('info'),
    startCheckBtn: {}, fetch: async () => ({ ok: true, json: async () => ({
      output_intent: { has_output_intent: true, icc_valid: false, identifier: 'FOGRA CMYK' }, pages: 1 }) }) };
  loadFunctions(context, ['escapeHtml', 'handleFileSelect']);
  await context.handleFileSelect({ name: 'invalid-icc.pdf', size: 100 });
  const markup = document.getElementById('fileDetectedIcc').innerHTML;
  assert.ok(markup.includes('Sin ICC válido incrustado'));
  assert.ok(!markup.includes('bg-emerald'));
  assert.ok(!document.getElementById('preserveIccHint').innerHTML.includes('Recomendado:'));
});

test('spot plates escape PDF names and bind literal names without inline JavaScript', () => {
  const document = fakeDocument();
  const labels = [];
  let change, toggled;
  document.createElement = () => {
    const label = { querySelector: () => ({ addEventListener: (_, fn) => { change = fn; } }) };
    labels.push(label); return label;
  };
  document.getElementById('sepSpotPlatesList').appendChild = () => {};
  const context = { document, currentSpotColors: [], disabledSpotColors: new Set(),
    toggleSpotPlate: (name, checked) => { toggled = [name, checked]; } };
  loadFunctions(context, ['escapeHtml', 'renderSpotPlates']);
  context.renderSpotPlates([{ name: maliciousText, type: maliciousText,
    color_hex: `red;" onmouseover="alert(1)` }]);
  assertInert(labels[0].innerHTML);
  assert.ok(!labels[0].innerHTML.includes('onchange='));
  assert.ok(!labels[0].innerHTML.includes('onmouseover='));
  assert.ok(labels[0].innerHTML.includes('background-color: #808080;'));
  change({ target: { checked: false } });
  assert.deepEqual(toggled, [maliciousText, false]);
});

test('spell suggestions preserve quoted PDF text without interpolating executable handlers', () => {
  let click, acted;
  const card = { querySelectorAll: () => [{ dataset: { spellAction: 'accept' },
    addEventListener: (_, fn) => { click = fn; } }] };
  const context = { document: { createElement: () => card },
    handleSpellAction: (...args) => { acted = args; } };
  loadFunctions(context, ['escapeHtml', 'createSpellSuggestionCard']);
  context.createSpellSuggestionCard({ id: 'spell_1', word: maliciousText, suggestion: maliciousText,
    context: maliciousText, page: 1 });
  assertInert(card.innerHTML);
  assert.ok(!card.innerHTML.includes('onclick='));
  click();
  assert.deepEqual(acted, ['spell_1', 'accept', maliciousText]);
});

test('barcode payloads and reasons are text even when they contain HTML', async () => {
  const document = fakeDocument();
  const item = { id: 'barcode_1', payload: maliciousText, reasons: [maliciousText], status: 'WARNING',
    type: 'QR Code', page_index: 0, page_number: 1, rect_pt: [0,0,10,10], dimensions_mm: [10,10],
    fixable: true, color_analysis: { bar_color_desc: maliciousText, tac_pct: 100 } };
  const context = { document, console, currentJobId: 'safe', currentBarcodeFindings: [],
    fetch: async () => ({ ok: true, json: async () => ({ findings: [item], warnings_count: 1 }) }) };
  loadFunctions(context, ['escapeHtml', 'loadBarcodeInspection']);
  await context.loadBarcodeInspection();
  const markup = document.getElementById('bcListContainer').innerHTML;
  assertInert(markup);
  assert.ok(!markup.includes('onclick='));
});

test('safety margin findings escape the actual PDF text and description', () => {
  const document = fakeDocument();
  const context = { document, currentSafetyMarginReport: { pages: [{ issues: [{
    severity: 'CRITICAL', side: 'left', content: maliciousText, description: maliciousText,
    distance_mm: 1, is_spine_edge: false }] }] } };
  loadFunctions(context, ['escapeHtml', 'renderSafetyMarginPageIssues']);
  context.renderSafetyMarginPageIssues(0);
  assertInert(document.getElementById('smInfractionsList').innerHTML);
});

test('groupFindings consolidates 30 bleed errors across 30 pages into 1 group and formats ranges', () => {
  const context = {};
  loadFunctions(context, ['formatPageRanges', 'groupFindings']);
  assert.equal(context.formatPageRanges([1, 2, 3, 4, 5]), 'Págs. 1-5');
  assert.equal(context.formatPageRanges([1, 2, 3, 5, 7, 8]), 'Págs. 1-3, 5, 7-8');
  assert.equal(context.formatPageRanges([4]), 'Pág. 4');

  const findings = [];
  for (let i = 1; i <= 30; i++) {
    findings.push({
      page: i,
      rule_id: 'BLEED_GEOMETRY_3MM',
      severity: 'ERROR',
      title: 'Sangrado insuficiente',
      message: `La página ${i} no tiene sangrado.`
    });
  }
  const grouped = context.groupFindings(findings);
  assert.equal(grouped.length, 1);
  assert.equal(grouped[0].findings.length, 30);
  assert.equal(grouped[0].pages.length, 30);
  assert.equal(context.formatPageRanges(grouped[0].pages), 'Págs. 1-30');
});

test('renderTimeline updates active version, undo/redo buttons and approved state', () => {
  const document = fakeDocument();
  const context = { document, currentJobId: 'job123', escapeHtml: s => String(s) };
  loadFunctions(context, ['renderTimeline']);

  const history = {
    active_id: 'v0002',
    approved_version_id: 'v0002',
    can_undo: true,
    can_redo: false,
    versions: [
      { id: 'v0001', label: 'Original', size_bytes: 10240, is_approved: false },
      { id: 'v0002', label: 'Versión aprobada', size_bytes: 20480, is_approved: true }
    ]
  };

  context.renderTimeline(history);
  assert.equal(document.getElementById('timelineActiveBadge').textContent, 'v0002');
  assert.equal(document.getElementById('timelineActiveLabel').textContent, 'Versión aprobada');
  assert.equal(document.getElementById('btnUndoVersion').disabled, false);
  assert.equal(document.getElementById('btnRedoVersion').disabled, true);
  assert.equal(document.getElementById('btnDownloadApprovedPdf').href, '/api/download-approved/job123');
});

test('renderResults updates expiration TTL notice and production package link', () => {
  const context = {
    document: fakeDocument(),
    getTacLimit: () => 300,
    closeIssueViewer: () => {},
    loadJobHistory: () => {}
  };
  vm.createContext(context);
  const start = html.indexOf('    function renderResults(data) {');
  const end = html.indexOf('      // Hide signed panel for new analysis until signed', start);
  vm.runInContext(html.slice(start, end) + '\n    }', context);

  context.renderResults({
    job_meta: { job_id: 'job_test_77', filename: 'catalogo.pdf', profile_id: 'OFFSET_300', current_sha256: 'f'.repeat(64) },
    triple_result: { release: { status: 'PENDING' } },
    expiration_info: { ttl_hours: 24, remaining_human: '21 h 40 min', is_expiring_soon: false }
  });

  assert.equal(context.document.getElementById('resJobTtlText').textContent, 'Retención 24 h (Caduca en 21 h 40 min)');
  assert.equal(context.document.getElementById('btnProductionPackage').href, '/api/production-package/job_test_77');
});

test('Separations preview advances pages, preserves current page on same-job re-init, and syncs X-Total-Pages', async () => {
  const document = fakeDocument();
  const requestedUrls = [];
  const context = {
    document,
    currentJobId: 'job_sep_1',
    selectedFile: null,
    sepActiveJobId: null,
    sepCurrentPage: 1,
    sepTotalPageCount: 1,
    sepAbortController: null,
    sepRequestSeq: 0,
    sepBlobUrl: null,
    sepDebounce: null,
    disabledSpotColors: new Set(),
    setTimeout: (fn) => { fn(); return 1; },
    clearTimeout: () => {},
    URL: {
      createObjectURL: () => 'blob:mock-sep-preview',
      revokeObjectURL: () => {}
    },
    fetch: async (url) => {
      requestedUrls.push(url);
      return {
        ok: true,
        status: 200,
        headers: { get: (k) => (k.toLowerCase() === 'x-total-pages' ? '4' : null) },
        blob: async () => ({ size: 128 })
      };
    }
  };

  loadFunctions(context, [
    'initSeparations',
    'updateSepNavButtons',
    'changeSepPage',
    'onSepPageInputChange',
    'updateSeparationPreview'
  ]);

  context.initSeparations(2);
  await new Promise(r => setImmediate(r));
  // Header X-Total-Pages=4 should sync total pages to 4
  assert.equal(document.getElementById('sepTotalPages').textContent, 4);
  assert.equal(document.getElementById('sepPrevPageBtn').disabled, true);
  assert.equal(document.getElementById('sepNextPageBtn').disabled, false);
  assert.ok(requestedUrls[0].includes('/api/separations/job_sep_1?page=1'));

  context.changeSepPage(1);
  await new Promise(r => setImmediate(r));
  assert.equal(document.getElementById('sepPageInput').value, 2);
  assert.equal(document.getElementById('sepPrevPageBtn').disabled, false);
  assert.ok(requestedUrls[requestedUrls.length - 1].includes('page=2'));

  context.onSepPageInputChange('3');
  await new Promise(r => setImmediate(r));
  assert.equal(document.getElementById('sepPageInput').value, 3);
  assert.ok(requestedUrls[requestedUrls.length - 1].includes('page=3'));

  // Re-initializing separations for the same job should preserve page 3
  context.initSeparations(4);
  await new Promise(r => setImmediate(r));
  assert.equal(document.getElementById('sepPageInput').value, 3);
});

test('updateKioskThemeButton maintains compact padding and removes intrusive ml-2', () => {
  const document = fakeDocument();
  const btn = { id: 'themeToggleBtn', className: '', innerHTML: '', title: '' };
  document.getElementById = (id) => (id === 'themeToggleBtn' ? btn : null);
  const context = { document };
  loadFunctions(context, ['updateKioskThemeButton']);

  context.updateKioskThemeButton(true);
  assert.ok(!btn.className.includes('ml-2'), 'Dark theme button should not have ml-2');
  assert.ok(btn.className.includes('whitespace-nowrap'));
  assert.ok(btn.innerHTML.includes('Modo Oficina'));

  context.updateKioskThemeButton(false);
  assert.ok(!btn.className.includes('ml-2'), 'Light theme button should not have ml-2');
  assert.ok(btn.className.includes('whitespace-nowrap'));
  assert.ok(btn.innerHTML.includes('Cabina D50'));
});

test('inline script initializes cleanly with real DOM IDs and executes full renderResults without TDZ errors', () => {
  const scriptStart = html.indexOf('<script>') + '<script>'.length;
  const scriptEnd = html.indexOf('</script>', scriptStart);
  const domPart = html.slice(0, scriptStart);
  const script = html.slice(scriptStart, scriptEnd);

  const domIds = new Set();
  for (const m of domPart.matchAll(/id=["']([^"']+)["']/g)) {
    domIds.add(m[1]);
  }

  function makeElement(id) {
    return {
      id,
      value: '',
      textContent: '',
      innerHTML: '',
      className: '',
      disabled: false,
      checked: true,
      options: [{ text: 'Default' }],
      selectedIndex: 0,
      style: {},
      classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
      addEventListener() {},
      appendChild() {},
      querySelector() { return makeElement(''); },
      querySelectorAll() { return []; },
      getAttribute() { return ''; },
      setAttribute() {},
      focus() {},
      scrollIntoView() {}
    };
  }

  const ctx = {
    console,
    window: { addEventListener() {}, location: { href: '', origin: 'http://localhost' } },
    localStorage: { getItem() { return null; }, setItem() {} },
    fetch: async () => ({
      ok: true,
      status: 200,
      headers: { get() { return null; } },
      json: async () => ({ profiles: [], history: { versions: [] } }),
      text: async () => '',
      blob: async () => ({ size: 10 })
    }),
    setTimeout: () => 1,
    clearTimeout: () => {},
    setInterval: () => 1,
    clearInterval: () => {},
    URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} },
    AbortController: class { abort() {} },
    document: {
      body: makeElement('body'),
      documentElement: makeElement('html'),
      getElementById(id) {
        return domIds.has(id) ? makeElement(id) : null;
      },
      querySelector() { return makeElement(''); },
      querySelectorAll() { return []; },
      addEventListener() {},
      createElement() { return makeElement(''); }
    }
  };
  ctx.window.document = ctx.document;
  ctx.globalThis = ctx;

  vm.runInNewContext(script, ctx);

  ctx.renderResults({
    job_meta: {
      job_id: 'job_full_boot',
      filename: 'Diptico.pdf',
      profile_id: 'OFFSET_300',
      sha256: 'a'.repeat(64),
      current_sha256: 'a'.repeat(64),
      original_icc_info: { has_icc: false, has_output_intent: false },
      icc_option: 'preserve'
    },
    job_summary: {
      pages: 2,
      trim_mm: '210 x 297 mm',
      bleed_mm: 3.0,
      max_tac_measured: 280,
      spot_colors: [],
      images: [],
      fonts_summary: { total: 1, non_embedded: 0 }
    },
    triple_result: {
      release: { status: 'PENDING', label: 'PENDIENTE' },
      technical: { label: 'APTO', status: 'PASS', errors_count: 0, warnings_count: 0 },
      content: { label: 'OK', suggestions_count: 0 }
    },
    proofreading: { suggestions: [] },
    spell_suggestions: [],
    fonts: [],
    images: [],
    findings: []
  });

  const sepActiveJob = vm.runInContext('sepActiveJobId', ctx);
  assert.equal(sepActiveJob, 'job_full_boot');
});
