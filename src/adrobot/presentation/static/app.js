const main = document.querySelector('#main');
const breadcrumb = document.querySelector('#breadcrumb');
const connection = document.querySelector('#connection');
const notice = document.querySelector('#notice');
const dialog = document.querySelector('#offer-dialog');
const offerQuery = document.querySelector('#offer-query');
const offerResults = document.querySelector('#offer-results');

const number = new Intl.NumberFormat('ru-RU');
const pageSize = 12;
const messages = new Map([
  ['Check the Keitaro key and its permissions.', 'Проверьте API-ключ Keitaro и права учётной записи.'],
  ['Could not reach Keitaro. Try again.', 'Keitaro недоступен. Повторите попытку.'],
  ['Keitaro is temporarily unavailable.', 'Keitaro временно недоступен.'],
  ['Keitaro rejected the operation.', 'Keitaro отклонил операцию. Проверьте доступ и параметры.'],
  ['Keitaro returned an unexpected response.', 'Keitaro вернул неожиданный ответ.'],
  ['The local database is unavailable.', 'Локальная база данных недоступна.'],
  ['Campaign was not found.', 'Кампания не найдена.'],
  ['Offer was not found or is unavailable.', 'Оффер не найден или недоступен.'],
  ['Offer is unavailable.', 'Оффер недоступен в Keitaro.'],
  ['The stream has changed. Refresh the campaign.', 'Поток изменился. Обновите кампанию.'],
  ['Keitaro changed this stream. Cancel the draft and refresh.', 'Поток изменился в Keitaro. Отмените черновик и обновите кампанию.'],
  ['Unpin an offer to distribute the remaining traffic.', 'Открепите долю, чтобы распределить оставшийся трафик.'],
  ['Unpin an offer to leave at least 1% for each active offer.', 'Открепите долю, чтобы каждому активному офферу досталось минимум 1%.'],
]);

const state = {
  route: 0,
  campaignId: null,
  streams: [],
  campaignQuery: '',
  campaignOffset: 0,
  showRemoved: true,
  offerStreamId: null,
  offerSearch: 0,
  queuedStreams: new Set(),
};

let noticeTimer;

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

function flash(message, bad = false) {
  clearTimeout(noticeTimer);
  notice.textContent = message;
  notice.classList.toggle('bad', bad);
  notice.hidden = false;
  noticeTimer = setTimeout(() => { notice.hidden = true; }, 5500);
}

function setConnection(ok) {
  connection.hidden = false;
  connection.classList.toggle('bad', !ok);
  connection.querySelector('.connection-text').textContent =
    ok ? 'Keitaro подключён' : 'Ошибка подключения';
}

async function api(path, method = 'GET', body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      signal: AbortSignal.timeout(45_000),
      ...(body === undefined ? {} : {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    });
  } catch {
    setConnection(false);
    throw new Error('Запрос не завершился. Повторите попытку.');
  }

  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    setConnection(true);
    return data;
  }
  if (response.status >= 500) setConnection(false);
  const detail = data.detail;
  if (Array.isArray(detail)) {
    const field = detail[0]?.loc?.at(-1);
    if (field === 'country') throw new Error('Введите двухбуквенный ISO-код страны, например AU.');
    throw new Error('Проверьте обязательные поля и формат значений.');
  }
  throw new Error(messages.get(detail) ?? detail ?? 'Запрос завершился ошибкой.');
}

function heading(title, subtitle, actions = '') {
  return `<div class="page-heading">
    <div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></div>
    <div class="heading-actions">${actions}</div>
  </div>`;
}

function setBreadcrumb(label, isList = false) {
  breadcrumb.innerHTML = isList ? 'Кампании' :
    `<a href="#campaigns">Кампании</a><span aria-hidden="true">›</span>${escapeHtml(label)}`;
}

function campaignStatus(status) {
  const label = { active: 'Активна', disabled: 'Отключена', deleted: 'Удалена' }[status];
  return `<span class="pill ${status === 'active' ? 'active' : ''}">${escapeHtml(label ?? status)}</span>`;
}

async function campaigns(route) {
  setBreadcrumb('', true);
  main.innerHTML = heading('Кампании', 'Управляйте кампаниями и распределением трафика в Keitaro.',
    '<a class="button primary" href="#new"><span aria-hidden="true">＋</span> Создать кампанию</a>') +
    `<section class="panel" aria-label="Кампании Keitaro">
      <div class="toolbar">
        <form class="search-row" id="campaign-search">
          <label class="sr-only" for="campaign-query">Название или ID кампании</label>
          <input id="campaign-query" type="search" maxlength="100" value="${escapeHtml(state.campaignQuery)}" placeholder="Название или ID кампании">
          <button type="submit" class="button secondary">Найти</button>
        </form>
      </div>
      <div id="campaign-list" aria-live="polite"><p class="empty">Загружаем кампании…</p></div>
    </section>`;
  await loadCampaigns(route);
}

async function loadCampaigns(route) {
  const panel = main.querySelector('#campaign-list');
  if (!panel) return;
  panel.setAttribute('aria-busy', 'true');
  const query = state.campaignQuery;
  const offset = state.campaignOffset;
  try {
    const params = new URLSearchParams({ query, offset, limit: pageSize });
    const result = await api(`/api/campaigns?${params}`);
    if (route !== state.route || query !== state.campaignQuery || offset !== state.campaignOffset) return;
    const items = result.items;
    const rows = items.map((item) => `<tr>
      <td><a class="campaign-name" href="#campaign/${item.id}">${escapeHtml(item.name)}</a>
        <span class="row-meta mono">#${item.id}</span></td>
      <td>${campaignStatus(item.state)}</td>
      <td>${escapeHtml(item.domain || '—')}</td>
      <td><a class="button secondary" href="#campaign/${item.id}" aria-label="Открыть кампанию ${escapeHtml(item.name)}">Открыть <span aria-hidden="true">›</span></a></td>
    </tr>`).join('');
    const table = rows ? `<div class="table-wrap"><table class="campaigns-table">
      <thead><tr><th>Кампания</th><th>Статус</th><th>Домен</th><th>Редактор</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>` : '<p class="empty">Кампании не найдены.</p>';
    panel.innerHTML = table + (offset || result.has_more ? `<div class="pager">
      <span>Страница ${Math.floor(offset / pageSize) + 1}</span>
      <div class="heading-actions">
        <button class="button secondary" data-page="-1" ${offset === 0 ? 'disabled' : ''}>Назад</button>
        <button class="button secondary" data-page="1" ${result.has_more ? '' : 'disabled'}>Далее</button>
      </div>
    </div>` : '');
  } catch (error) {
    if (route === state.route) panel.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  } finally {
    panel.removeAttribute('aria-busy');
  }
}

function selectOptions(values) {
  const preferred = values.find((option) => option.name.toUpperCase() === 'FORTESTS')?.id;
  return values.map((option) => `<option value="${option.id}" ${preferred === option.id ? 'selected' : ''}>${escapeHtml(option.name)} (#${option.id})</option>`).join('');
}

async function createPage(route) {
  setBreadcrumb('Новая кампания');
  main.innerHTML = heading('Создать кампанию', 'Выбранное гео направляется в Google, остальной трафик — на оффер.') +
    '<section class="panel form-panel" id="create-panel"><p class="empty">Загружаем домены, группы и источники…</p></section>';
  const panel = main.querySelector('#create-panel');
  try {
    const catalog = await api('/api/catalog');
    if (route !== state.route) return;
    panel.innerHTML = `<form id="create-form">
      <div class="form-grid">
        <div class="field field-wide"><label for="campaign-name">Название кампании</label>
          <input id="campaign-name" name="name" required maxlength="100" placeholder="campaign1" autocomplete="off">
          <small>Префикс ${escapeHtml(catalog.campaign_prefix)} добавляется автоматически.</small>
        </div>
        <div class="field"><label for="country">Гео-код страны</label>
          <input id="country" name="country" required pattern="[A-Za-z]{2}" minlength="2" maxlength="2" placeholder="AU" autocomplete="off">
          <small>Двухбуквенный код ISO</small>
        </div>
        <div class="field"><label for="initial-offer">ID оффера Keitaro</label>
          <input id="initial-offer" name="offer_id" type="number" min="1" max="9007199254740991" step="1" required placeholder="18813">
        </div>
        <div class="field"><label for="domain">Домен</label><select id="domain" name="domain_id" required>${selectOptions(catalog.domains)}</select></div>
        <div class="field"><label for="group">Группа кампаний</label><select id="group" name="group_id" required>${selectOptions(catalog.groups)}</select></div>
        <div class="field"><label for="source">Источник трафика</label><select id="source" name="traffic_source_id" required>${selectOptions(catalog.sources)}</select></div>
        <p id="form-error" class="error field-wide" role="alert" hidden></p>
      </div>
      <div class="form-footer">
        <button type="submit" class="button primary" ${catalog.domains.length && catalog.groups.length && catalog.sources.length ? '' : 'disabled'}>Создать кампанию</button>
        <a class="button secondary" href="#campaigns">Отмена</a>
      </div>
    </form>`;
    if (!catalog.domains.length || !catalog.groups.length || !catalog.sources.length) {
      const error = panel.querySelector('#form-error');
      error.textContent = 'Нет доступного домена, группы или источника в Keitaro.';
      error.hidden = false;
    }
  } catch (error) {
    if (route === state.route) panel.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

async function submitCampaign(form) {
  const route = state.route;
  const button = form.querySelector('button[type="submit"]');
  if (button.disabled) return;
  const data = Object.fromEntries(new FormData(form));
  data.name = data.name.trim();
  data.country = data.country.toUpperCase();
  for (const field of ['offer_id', 'domain_id', 'group_id', 'traffic_source_id']) {
    data[field] = Number(data[field]);
  }
  const key = `adrobot:create:${JSON.stringify(data)}`;
  const requestId = sessionStorage.getItem(key) ?? crypto.randomUUID();
  sessionStorage.setItem(key, requestId);
  const errorBox = form.querySelector('#form-error');
  button.disabled = true;
  button.textContent = 'Создаём…';
  errorBox.hidden = true;
  try {
    const campaign = await api('/api/campaigns', 'POST', { ...data, request_id: requestId });
    sessionStorage.removeItem(key);
    if (route !== state.route) return;
    flash('Кампания создана в Keitaro.');
    location.hash = `campaign/${campaign.id}`;
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = 'Создать кампанию';
  }
}

function streamMarkup(stream) {
  const busy = state.queuedStreams.has(stream.id) ? 'disabled' : '';
  const visible = stream.offers.filter((offer) => state.showRemoved || offer.state !== 'removed');
  const edit = stream.editable ? `<div class="heading-actions">
    <button class="button secondary" data-action="open-offers" ${busy}>＋ Добавить оффер</button>
    ${stream.dirty ? `<button class="button secondary" data-action="cancel" ${busy}>Отменить</button>
      <button class="button primary" data-action="publish" ${busy}>Опубликовать</button>` : ''}
  </div>` : '';
  const rows = visible.map((offer) => {
    const removed = offer.state === 'removed';
    const disabled = offer.state === 'disabled';
    return `<tr class="${removed ? 'removed' : ''}">
      <td class="offer-name">${escapeHtml(offer.name)}
        ${removed ? '<span class="pill">Удалён</span>' : ''}
        ${disabled ? '<span class="pill">Отключён</span>' : ''}
        <span class="row-meta mono">#${offer.offer_id}</span>
      </td>
      <td><span class="share mono">${offer.share}%<progress max="100" value="${offer.share}" aria-label="Доля трафика ${offer.share}%"></progress></span></td>
      <td><div class="row-actions">
        ${stream.editable && !removed && !disabled ? `<button class="button text" data-action="pin" data-offer="${offer.offer_id}" aria-pressed="${offer.pinned}" ${busy}>${offer.pinned ? 'Открепить' : 'Закрепить'}</button>` : ''}
        ${stream.editable ? `<button class="button text ${removed ? '' : 'danger'}" data-action="${removed ? 'restore' : 'remove'}" data-offer="${offer.offer_id}" ${busy}>${removed ? 'Вернуть' : 'Удалить'}</button>` : ''}
      </div></td>
    </tr>`;
  }).join('');
  return `<article class="stream-card ${stream.dirty ? 'unsaved' : ''}" data-stream="${stream.id}">
    <div class="stream-header">
      <div><div class="stream-title"><h2>${escapeHtml(stream.name)}</h2>
        ${stream.dirty ? '<span class="pill draft">Черновик</span>' : ''}
        ${stream.state === 'disabled' ? '<span class="pill">Отключён</span>' : ''}
      </div>
      <div class="stream-meta mono"><span>Поток #${stream.id}</span>
        <span>Клики сегодня <strong>${stream.clicks_today == null ? '—' : number.format(stream.clicks_today)}</strong></span>
      </div></div>
      ${edit}
    </div>
    ${rows ? `<div class="table-wrap"><table class="offer-table">
      <thead><tr><th>Оффер</th><th>Доля трафика</th><th>Действия</th></tr></thead>
      <tbody>${rows}</tbody></table></div>` : '<p class="empty">В потоке нет офферов.</p>'}
  </article>`;
}

function renderStreams() {
  const container = main.querySelector('#streams');
  if (container) container.innerHTML = state.streams.length ?
    state.streams.map(streamMarkup).join('') : '<p class="panel empty">У кампании нет потоков.</p>';
}

async function syncCampaign(id, route) {
  const refresh = main.querySelector('#refresh-campaign');
  if (refresh) refresh.disabled = true;
  try {
    const { campaign, streams, admin_url: adminUrl } = await api(`/api/campaigns/${id}/sync`, 'POST');
    if (route !== state.route) return;
    state.streams = streams;
    setBreadcrumb(campaign.name);
    main.innerHTML = heading(campaign.name, [`Кампания #${id}`, campaign.domain].filter(Boolean).join(' · '),
      `${campaignStatus(campaign.state)}<a class="button secondary" href="${escapeHtml(adminUrl)}" target="_blank" rel="noopener noreferrer">Открыть в Keitaro ↗</a><button id="refresh-campaign" class="button secondary" type="button">↻ Обновить из Keitaro</button>`) +
      `<div class="stream-controls">
        <label class="toggle"><input id="show-removed" type="checkbox" ${state.showRemoved ? 'checked' : ''}> Показать удалённые офферы</label>
      </div>
      <div id="streams" class="stream-list"></div>`;
    renderStreams();
  } catch (error) {
    if (route !== state.route) return;
    if (!refresh) {
      main.innerHTML = heading(`Кампания #${id}`, 'Потоки Keitaro',
        '<button id="refresh-campaign" class="button secondary" type="button">↻ Повторить</button>') +
        `<p class="error" role="alert">${escapeHtml(error.message)}</p>`;
    } else {
      flash(error.message, true);
    }
  } finally {
    if (refresh) refresh.disabled = false;
  }
}

async function editStream(streamId, action, offerId) {
  if (state.queuedStreams.has(streamId) ||
      main.querySelector('#refresh-campaign')?.disabled) return false;
  const route = state.route;
  const stream = state.streams.find((item) => item.id === streamId);
  if (!stream) return false;
  const base = `/api/campaigns/${state.campaignId}/streams/${streamId}`;
  state.queuedStreams.add(streamId);
  renderStreams();
  try {
    let result;
    if (action === 'publish') {
      result = await api(`${base}/publish?revision=${stream.revision}`, 'POST');
    } else if (action === 'cancel') {
      result = await api(`${base}/draft?revision=${stream.revision}`, 'DELETE');
    } else {
      result = await api(`${base}/draft`, 'PATCH', {
        revision: stream.revision,
        action,
        offer_id: offerId,
      });
    }
    if (route !== state.route) return false;
    Object.assign(stream, result);
    if (action === 'publish') flash('Поток обновлён в Keitaro.');
    if (action === 'cancel') flash('Черновик отменён.');
    return true;
  } catch (error) {
    if (route === state.route) {
      if (dialog.open && action === 'add') {
        offerResults.innerHTML = `<p class="error" role="alert">${escapeHtml(error.message)}</p>`;
      } else {
        flash(error.message, true);
      }
    }
    return false;
  } finally {
    state.queuedStreams.delete(streamId);
    if (route === state.route) renderStreams();
  }
}

async function searchOffers() {
  const search = ++state.offerSearch;
  const stream = state.streams.find((item) => item.id === state.offerStreamId);
  if (!stream) return;
  offerResults.innerHTML = '<p class="empty">Ищем в Keitaro…</p>';
  try {
    const query = new URLSearchParams({ query: offerQuery.value.trim() });
    const offers = await api(`/api/offers?${query}`);
    if (search !== state.offerSearch || !dialog.open) return;
    const ids = new Set(stream.offers.map((offer) => offer.offer_id));
    const results = offers.filter((offer) => !ids.has(offer.id));
    offerResults.innerHTML = results.length ? results.map((offer) => `
      <div class="offer-result"><span>${escapeHtml(offer.name)} <span class="row-meta">#${offer.id}</span></span>
      <button class="button primary" type="button" data-add-offer="${offer.id}">Добавить</button></div>
    `).join('') : '<p class="empty">Подходящие офферы не найдены.</p>';
  } catch (error) {
    if (search === state.offerSearch && dialog.open) {
      offerResults.innerHTML = `<p class="error" role="alert">${escapeHtml(error.message)}</p>`;
    }
  }
}

function openOfferDialog(id) {
  state.offerStreamId = id;
  offerQuery.value = '';
  dialog.showModal();
  void searchOffers();
}

main.addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.id === 'refresh-campaign') {
    if (state.queuedStreams.size) return;
    void syncCampaign(state.campaignId, state.route);
  } else if (button.dataset.page) {
    if (main.querySelector('#campaign-list')?.getAttribute('aria-busy') === 'true') return;
    state.campaignOffset += Number(button.dataset.page) * pageSize;
    void loadCampaigns(state.route);
  } else if (button.dataset.action) {
    if (main.querySelector('#refresh-campaign')?.disabled) return;
    const id = Number(button.closest('[data-stream]').dataset.stream);
    const action = button.dataset.action;
    if (action === 'open-offers') openOfferDialog(id);
    else void editStream(id, action, Number(button.dataset.offer));
  }
});

main.addEventListener('submit', (event) => {
  event.preventDefault();
  if (event.target.id === 'campaign-search') {
    state.campaignQuery = event.target.querySelector('input').value.trim();
    state.campaignOffset = 0;
    void loadCampaigns(state.route);
  } else if (event.target.id === 'create-form') {
    void submitCampaign(event.target);
  }
});

main.addEventListener('change', (event) => {
  if (event.target.id === 'show-removed') {
    state.showRemoved = event.target.checked;
    renderStreams();
  }
});

document.querySelector('#offer-search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  void searchOffers();
});

let searchDebounce;
offerQuery.addEventListener('input', () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => { if (dialog.open) void searchOffers(); }, 260);
});

offerResults.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-add-offer]');
  if (!button) return;
  for (const result of offerResults.querySelectorAll('button')) result.disabled = true;
  if (await editStream(state.offerStreamId, 'add', Number(button.dataset.addOffer))) {
    if (dialog.open) dialog.close();
  } else {
    for (const result of offerResults.querySelectorAll('button')) result.disabled = false;
  }
});

document.querySelector('#close-offer-dialog').addEventListener('click', () => dialog.close());

function navigate() {
  const route = ++state.route;
  if (dialog.open) dialog.close();
  const hash = location.hash.slice(1);
  const campaignMatch = /^campaign\/(\d+)$/.exec(hash);
  const section = hash === 'new' ? 'new' : 'campaigns';
  for (const link of document.querySelectorAll('[data-section]')) {
    if (link.dataset.section === section) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  state.campaignId = campaignMatch ? Number(campaignMatch[1]) : null;
  state.streams = [];
  if (state.campaignId !== null) {
    setBreadcrumb(`Кампания #${state.campaignId}`);
    main.innerHTML = '<p class="panel empty">Загружаем потоки кампании…</p>';
    void syncCampaign(state.campaignId, route);
  } else if (section === 'new') {
    void createPage(route);
  } else {
    void campaigns(route);
  }
}

window.addEventListener('hashchange', navigate);
navigate();
