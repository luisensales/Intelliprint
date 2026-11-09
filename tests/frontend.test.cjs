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
        value: '', checked: false, innerHTML: '',
        classList: { add() {}, remove() {}, toggle() {} },
        querySelectorAll() { return []; },
      });
      return elements.get(id);
    },
  };
}

test('all inline JavaScript parses', () => {
  for (const script of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    if (!/\bsrc\s*=/.test(script[1])) new vm.Script(script[2]);
  }
});

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
    loadFunctions(context, [name]);
    await context[name]({ innerHTML: 'Convertir', closest: () => null });
    assert.equal(rendered, report);
    assert.equal(context.currentReport.triple_result.technical.status, 'FAIL');
    assert.equal(context.currentReport.findings.length, 1);
  });
}

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
