/* Current-PDF issue inspector. PDF bytes and geometry come from the same SHA. */
let issueViewerState = { jobId: null, report: null, requestId: 0, index: 0,
  objectUrl: null, zoom: 1, lastFocus: null, controller: null, data: null, overflow: '' };

function issueViewerIsCurrent(token) {
  return token === issueViewerState.requestId && issueViewerState.jobId === currentJobId &&
    issueViewerState.report === currentReport && !document.getElementById('issueViewerModal').hidden;
}

function clearIssueViewerImage() {
  const image = document.getElementById('issueViewerImage');
  image.hidden = true;
  image.removeAttribute('src');
  document.getElementById('issueViewerRegions').replaceChildren();
  if (issueViewerState.objectUrl) URL.revokeObjectURL(issueViewerState.objectUrl);
  issueViewerState.objectUrl = null;
}

function openIssueViewer(index = 0) {
  if (!currentJobId || !currentReport?.findings?.length) return;
  const modal = document.getElementById('issueViewerModal');
  if (modal.hidden) {
    issueViewerState.lastFocus = document.activeElement;
    issueViewerState.overflow = document.body.style.overflow;
  }
  issueViewerState.jobId = currentJobId;
  issueViewerState.report = currentReport;
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
  document.getElementById('issueViewerClose').focus();
  return loadIssueViewer(index);
}

function closeIssueViewer(restoreFocus = true) {
  const modal = document.getElementById('issueViewerModal');
  if (modal.hidden) return;
  modal.hidden = true;
  issueViewerState.requestId++;
  issueViewerState.controller?.abort();
  issueViewerState.controller = null;
  clearIssueViewerImage();
  issueViewerState.data = null;
  document.body.style.overflow = issueViewerState.overflow;
  if (restoreFocus && issueViewerState.lastFocus?.isConnected !== false) issueViewerState.lastFocus?.focus();
}

function buildIssueViewerList() {
  const list = document.getElementById('issueViewerList');
  list.replaceChildren();
  issueViewerState.report.findings.forEach((finding, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'issue-viewer-entry';
    button.dataset.severity = finding.severity;
    button.setAttribute('aria-current', index === issueViewerState.index ? 'true' : 'false');
    const reference = document.createElement('span');
    reference.className = 'issue-viewer-entry-ref';
    reference.textContent = `${finding.severity === 'ERROR' ? 'ERROR' : 'AVISO'} · Pág. ${finding.page || '—'}`;
    const title = document.createElement('span');
    title.textContent = finding.title || 'Incidencia técnica';
    button.append(reference, title);
    button.addEventListener('click', () => loadIssueViewer(index));
    list.appendChild(button);
  });
  const count = issueViewerState.report.findings.length;
  document.getElementById('issueViewerCounter').textContent = `${issueViewerState.index + 1} de ${count}`;
  document.getElementById('issueViewerPrevious').disabled = issueViewerState.index === 0;
  document.getElementById('issueViewerNext').disabled = issueViewerState.index >= count - 1;
}

function renderIssueViewerDetails(data) {
  const finding = data.finding;
  document.getElementById('issueViewerTitle').textContent = finding.title || 'Incidencia técnica';
  document.getElementById('issueViewerDescription').textContent = finding.message || 'Consulta los requisitos del perfil de producción.';
  document.getElementById('issueViewerDocument').textContent = issueViewerState.report.job_meta.filename || 'Documento PDF';
  document.getElementById('issueViewerPageLabel').textContent = `Página ${data.page} de ${data.pages} · PDF actual`;
  const location = document.getElementById('issueViewerLocation');
  const exact = data.location_status === 'exact' && data.regions?.length > 0;
  location.textContent = exact ? `${data.regions.length} zona(s) resaltada(s) en esta página` :
    'Incidencia de página o documento. No se dispone de una ubicación exacta del objeto.';
  location.dataset.exact = String(exact);
  document.getElementById('issueViewerFocus').disabled = !exact;
  const facts = document.getElementById('issueViewerFacts');
  facts.replaceChildren();
  const labels = [['image_index', 'Imagen'], ['effective_dpi', 'Resolución efectiva'],
    ['target_dpi', 'Mínimo del perfil'], ['colorspace', 'Color'], ['placed_mm', 'Tamaño colocado']];
  labels.forEach(([key, label]) => {
    if (finding[key] === undefined || finding[key] === null) return;
    const row = document.createElement('div');
    const name = document.createElement('dt');
    const value = document.createElement('dd');
    name.textContent = label;
    value.textContent = `${finding[key]}${key.endsWith('dpi') ? ' ppp' : ''}`;
    row.append(name, value);
    facts.appendChild(row);
  });
  const regions = document.getElementById('issueViewerRegions');
  regions.replaceChildren();
  (data.regions || []).forEach(region => {
    const values = [region.x, region.y, region.width, region.height];
    if (!values.every(Number.isFinite) || region.width <= 0 || region.height <= 0) return;
    const x = Math.max(0, region.x), y = Math.max(0, region.y);
    const width = Math.min(1, region.x + region.width) - x;
    const height = Math.min(1, region.y + region.height) - y;
    if (width <= 0 || height <= 0) return;
    const box = document.createElement('div');
    box.className = 'issue-viewer-region';
    box.dataset.severity = finding.severity;
    box.style.left = `${x * 100}%`; box.style.top = `${y * 100}%`;
    box.style.width = `${width * 100}%`; box.style.height = `${height * 100}%`;
    regions.appendChild(box);
  });
}

async function loadIssueViewer(index) {
  const state = issueViewerState;
  if (!Number.isInteger(index) || index < 0 || index >= (state.report?.findings?.length || 0)) return;
  state.controller?.abort();
  state.controller = new AbortController();
  const token = ++state.requestId;
  state.index = index;
  state.data = null;
  clearIssueViewerImage();
  buildIssueViewerList();
  const status = document.getElementById('issueViewerStatus');
  const modal = document.getElementById('issueViewerModal');
  status.textContent = 'Cargando la incidencia y su página…';
  status.dataset.error = 'false';
  modal.setAttribute('aria-busy', 'true');
  document.getElementById('issueViewerRetry').hidden = true;
  const expected = state.report.job_meta.current_sha256 || state.report.job_meta.sha256;
  const path = `/api/issue-viewer/${encodeURIComponent(state.jobId)}`;
  try {
    const response = await fetch(`${path}?finding_index=${index}${expected ? '&sha256=' + encodeURIComponent(expected) : ''}`,
      {signal: state.controller.signal, cache: 'no-store'});
    const data = await response.json();
    if (!issueViewerIsCurrent(token)) return;
    if (!response.ok) throw new Error(response.status === 409 ? 'El PDF ha cambiado. Cierra el visor y actualiza el informe antes de continuar.' :
      (typeof data.detail === 'string' ? data.detail : 'No se pudo abrir esta incidencia.'));
    if (expected && expected !== data.sha256) throw new Error('La página y el informe corresponden a versiones diferentes del PDF. Actualiza el informe.');
    if (!data.render_url?.startsWith(path + '/render?')) throw new Error('La dirección de la página no es válida.');
    state.data = data;
    renderIssueViewerDetails(data);
    status.textContent = 'Cargando la vista del PDF…';
    const rendered = await fetch(data.render_url, {signal: state.controller.signal, cache: 'no-store'});
    if (!issueViewerIsCurrent(token)) return;
    if (!rendered.ok) throw new Error(rendered.status === 409 ? 'El PDF ha cambiado durante la revisión. Actualiza el informe.' : 'No se pudo cargar la vista de esta página.');
    const blob = await rendered.blob();
    if (!issueViewerIsCurrent(token)) return;
    state.objectUrl = URL.createObjectURL(blob);
    const image = document.getElementById('issueViewerImage');
    image.onload = () => { if (issueViewerIsCurrent(token)) setIssueViewerZoom(1); };
    image.onerror = () => { if (issueViewerIsCurrent(token)) { status.textContent = 'No se pudo visualizar la página. Reintenta la carga.'; document.getElementById('issueViewerRetry').hidden = false; } };
    image.src = state.objectUrl;
    image.hidden = false;
    status.textContent = data.location_status === 'exact' ? 'Objeto localizado. Puedes acercar la zona resaltada.' : 'Página disponible para revisión visual.';
    setIssueViewerZoom(1);
  } catch (error) {
    if (error.name === 'AbortError' || !issueViewerIsCurrent(token)) return;
    clearIssueViewerImage();
    status.textContent = error.message || 'No se pudo cargar el visor.';
    status.dataset.error = 'true';
    document.getElementById('issueViewerRetry').hidden = false;
  } finally {
    if (issueViewerIsCurrent(token)) modal.setAttribute('aria-busy', 'false');
  }
}

function setIssueViewerZoom(value) {
  if (!Number.isFinite(value)) return;
  issueViewerState.zoom = Math.max(.25, Math.min(4, value));
  const viewport = document.getElementById('issueViewerViewport');
  const fit = Math.max(100, (viewport.clientWidth || 850) - 48);
  document.getElementById('issueViewerPage').style.width = `${Math.round(fit * issueViewerState.zoom)}px`;
  document.getElementById('issueViewerZoomLabel').textContent = `${Math.round(issueViewerState.zoom * 100)} %`;
}

function focusIssueViewerRegion() {
  const region = issueViewerState.data?.regions?.[0];
  if (!region || ![region.width, region.height].every(Number.isFinite) || region.width <= 0 || region.height <= 0) return;
  setIssueViewerZoom(Math.min(4, Math.max(1, .7 / Math.max(region.width, region.height))));
  const box = document.getElementById('issueViewerRegions').firstElementChild;
  box?.scrollIntoView({block: 'center', inline: 'center', behavior: 'smooth'});
}

document.addEventListener('keydown', event => {
  const modal = document.getElementById('issueViewerModal');
  if (modal.hidden) return;
  if (event.key === 'Escape') { event.preventDefault(); closeIssueViewer(); }
  if (event.key === 'Tab') {
    const controls = Array.from(modal.querySelectorAll('button:not([disabled]), [href], [tabindex="0"]')).filter(el => !el.hidden);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
});
window.addEventListener('resize', () => { if (!document.getElementById('issueViewerModal').hidden) setIssueViewerZoom(issueViewerState.zoom); });
