// Run with: node --test tests/issue_viewer.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const sourcePath = path.join(__dirname, '../static/issue-viewer.js');

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}

function fakeDocument() {
  const elements = new Map();
  const document = {
    activeElement: null,
    events: new Map(),
    addEventListener(type, handler) { this.events.set(type, handler); },
    removeEventListener(type) { this.events.delete(type); },
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, makeElement('div'));
      return elements.get(id);
    },
    createElement: tag => makeElement(tag),
    querySelectorAll() { return []; },
  };
  function makeElement(tag) {
    const classes = new Set();
    const element = {
      tagName: tag.toUpperCase(), children: [], attributes: {}, dataset: {}, style: {},
      textContent: '', innerHTML: '', hidden: false, disabled: false, tabIndex: 0,
      clientWidth: 800, clientHeight: 600, scrollWidth: 1200, scrollHeight: 1600,
      offsetWidth: 800, offsetHeight: 600, naturalWidth: 1200, naturalHeight: 1600,
      complete: true,
      classList: {
        add(...values) { values.forEach(value => classes.add(value)); },
        remove(...values) { values.forEach(value => classes.delete(value)); },
        contains: value => classes.has(value),
        toggle(value, force) {
          if (force === undefined ? !classes.has(value) : force) classes.add(value);
          else classes.delete(value);
        },
      },
      appendChild(child) { this.children.push(child); child.parentElement = this; return child; },
      append(...children) { children.forEach(child => this.appendChild(child)); },
      replaceChildren(...children) { this.children = []; this.append(...children); },
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name] ?? null; },
      removeAttribute(name) { delete this.attributes[name]; if (name === 'src') this.src = ''; },
      addEventListener(type, handler) { this[`on${type}`] = handler; },
      removeEventListener(type) { delete this[`on${type}`]; },
      focus() { document.activeElement = this; },
      contains(target) { return this === target || this.children.some(child => child.contains?.(target)); },
      querySelectorAll() { return this.children; },
      getBoundingClientRect() { return {left: 0, top: 0, width: 800, height: 600}; },
      scrollIntoView() {}, scrollTo() {},
    };
    let src = '';
    let markup = '';
    Object.defineProperty(element, 'innerHTML', {
      get() { return markup; },
      set(value) { markup = String(value); this.children = []; },
    });
    Object.defineProperty(element, 'src', {
      get() { return src; },
      set(value) {
        src = String(value);
        if (src) queueMicrotask(() => element.onload?.());
      },
    });
    return element;
  }
  document.body = makeElement('body');
  document.getElementById('issueViewerModal').hidden = true;
  return document;
}

function report(jobId = 'job-a') {
  return {
    job_meta: {job_id: jobId, current_sha256: 'a'.repeat(64)},
    findings: [
      {page: 1, rule_id: 'PRINT_IMAGE_EFFECTIVE_PPI', severity: 'ERROR', title: 'Resolución insuficiente', message: 'Imagen 2: 121 ppp.'},
      {page: 2, rule_id: 'USED_FONTS_EMBEDDED', severity: 'ERROR', title: 'Fuente no incrustada', message: 'Revisar Helvetica.'},
    ],
  };
}

function metadata(index = 0, overrides = {}) {
  return {
    job_id: 'job-a', sha256: 'a'.repeat(64), page: index + 1, pages: 2,
    width: 600, height: 800, regions: [{x: .1, y: .2, width: .3, height: .1}],
    location_status: 'exact', finding: report().findings[index],
    render_url: `/api/issue-viewer/job-a/render?page=${index + 1}&sha256=${'a'.repeat(64)}`,
    ...overrides,
  };
}

function response(data) { return {ok: true, status: 200, json: async () => data}; }

function setup(fetchMetadata = async () => response(metadata())) {
  const document = fakeDocument(), urls = [], revoked = [], calls = [];
  const origin = document.createElement('button');
  origin.focus();
  class TestURL extends URL {
    static createObjectURL(blob) { const value = `blob:viewer-${urls.length + 1}`; urls.push(value); return value; }
    static revokeObjectURL(value) { revoked.push(value); }
  }
  const current = report();
  const context = {
    document, currentJobId: 'job-a', currentReport: current, console,
    AbortController, URL: TestURL, Blob, setTimeout, clearTimeout,
    location: {origin: 'http://localhost:8000'},
    requestAnimationFrame: callback => callback(),
    fetch: async (url, options) => {
      calls.push({url, options});
      if (String(url).includes('/render?')) return {ok: true, status: 200, blob: async () => new Blob(['png'], {type: 'image/png'})};
      return fetchMetadata(url, options);
    },
    addEventListener() {}, removeEventListener() {},
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), context);
  return {context, document, origin, urls, revoked, calls};
}

test('opening an issue displays the current page and untrusted labels as plain text', async () => {
  const title = '<img src=x onerror=alert(1)>', message = '<script>bad()</script>';
  const state = setup(async () => response(metadata(0, {finding: {...report().findings[0], title, message}})));
  await state.context.openIssueViewer(0);
  assert.equal(state.document.getElementById('issueViewerModal').hidden, false);
  assert.equal(state.document.getElementById('issueViewerTitle').textContent, title);
  assert.equal(state.document.getElementById('issueViewerDescription').textContent, message);
  assert.notEqual(state.document.getElementById('issueViewerImage').src, '');
  assert.equal(state.document.getElementById('issueViewerTitle').innerHTML, '');
  assert.equal(state.document.getElementById('issueViewerRegions').children.length, 1);
});

test('closing cancels the request, releases the preview and restores keyboard focus', async () => {
  const state = setup();
  await state.context.openIssueViewer(0);
  const signal = state.calls[0].options?.signal;
  state.context.closeIssueViewer();
  assert.equal(state.document.getElementById('issueViewerModal').hidden, true);
  assert.equal(state.document.activeElement, state.origin);
  assert.ok(state.revoked.includes(state.urls[0]));
  if (signal) assert.equal(signal.aborted, true);
});

test('a late issue response cannot replace a more recently selected issue', async () => {
  const first = deferred();
  const state = setup(async url => String(url).includes('finding_index=0') ? first.promise : response(metadata(1)));
  const openingFirst = state.context.openIssueViewer(0);
  const openingSecond = state.context.openIssueViewer(1);
  await openingSecond;
  first.resolve(response(metadata(0)));
  await openingFirst;
  assert.equal(state.document.getElementById('issueViewerTitle').textContent, 'Fuente no incrustada');
});

test('a response from a previously active job never opens its PDF', async () => {
  const pending = deferred();
  const state = setup(() => pending.promise);
  const opening = state.context.openIssueViewer(0);
  state.context.currentJobId = 'job-b';
  state.context.currentReport = report('job-b');
  pending.resolve(response(metadata()));
  await opening;
  assert.equal(state.urls.length, 0);
  assert.equal(state.context.currentJobId, 'job-b');
});

test('a mismatched PDF hash is reported instead of displaying an outdated highlight', async () => {
  const state = setup(async () => response(metadata(0, {sha256: 'b'.repeat(64)})));
  await state.context.openIssueViewer(0);
  assert.equal(state.urls.length, 0);
  assert.match(state.document.getElementById('issueViewerStatus').textContent, /versi[oó]n|actualiz|cambi/i);
});

test('page-only findings remain explicit and render no invented object region', async () => {
  const state = setup(async () => response(metadata(0, {location_status: 'page', regions: []})));
  await state.context.openIssueViewer(0);
  assert.equal(state.document.getElementById('issueViewerRegions').children.length, 0);
  assert.match(state.document.getElementById('issueViewerLocation').textContent, /p[aá]gina|ubicaci[oó]n/i);
});
