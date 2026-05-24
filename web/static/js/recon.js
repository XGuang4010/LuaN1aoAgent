let state = {
  taskId: new URLSearchParams(location.search).get('task_id') || '',
  allItems: [],
  filteredItems: [],
  targets: [],
  summary: null,
  search: '',
};

const typeColors = {
  domain: 'type-domain',
  ip: 'type-ip',
  port: 'type-port',
  endpoint: 'type-endpoint',
  service: 'type-service',
  tech: 'type-tech',
  credential: 'type-credential',
  sensitive: 'type-sensitive',
  auth: 'type-auth',
  file: 'type-file',
};

function getTypeClass(t) {
  return typeColors[t] || 'type-default';
}

function escapeHtml(str) {
  if (typeof str !== 'string') str = String(str);
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function loadTasks() {
  const selector = document.getElementById('task-selector');
  try {
    const data = await fetch('/api/ops').then(r => r.json());
    const items = data.items || [];
    // Keep first option
    selector.innerHTML = '<option value="">选择任务...</option>';
    items.forEach(i => {
      const opt = document.createElement('option');
      opt.value = i.task_id || i.op_id;
      opt.textContent = `${i.task_id || i.op_id} (${i.goal ? i.goal.slice(0, 30) + '...' : 'no goal'})`;
      if (opt.value === state.taskId) opt.selected = true;
      selector.appendChild(opt);
    });
  } catch (e) {
    console.error('loadTasks error', e);
  }
}

async function loadRecon() {
  if (!state.taskId) {
    renderEmpty('选择一个任务查看侦察数据');
    return;
  }
  const list = document.getElementById('results-list');
  list.innerHTML = '<div class="recon-empty">加载中...</div>';

  try {
    const [itemsData, summaryData, targetsData] = await Promise.all([
      fetch(`/api/recon/${encodeURIComponent(state.taskId)}?limit=500`).then(r => r.json()),
      fetch(`/api/recon/${encodeURIComponent(state.taskId)}/summary`).then(r => r.json()),
      fetch(`/api/recon/${encodeURIComponent(state.taskId)}/targets`).then(r => r.json()),
    ]);

    state.allItems = itemsData.items || [];
    state.summary = summaryData;
    state.targets = targetsData.targets || [];

    updateTargetFilter();
    applyFilters();
    renderSummary();
    updateUrl();
  } catch (e) {
    console.error('loadRecon error', e);
    renderEmpty('加载失败: ' + e.message);
  }
}

function updateTargetFilter() {
  const select = document.getElementById('target-filter');
  const current = select.value;
  select.innerHTML = '<option value="">全部目标</option>';
  state.targets.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t;
    opt.textContent = t;
    if (t === current) opt.selected = true;
    select.appendChild(opt);
  });
}

function renderSummary() {
  const bar = document.getElementById('summary-bar');
  if (!state.summary) {
    bar.innerHTML = '';
    return;
  }
  const sb = state.summary;
  let h = `<div class="recon-summary-pill"><b>${sb.total_records}</b> 条记录</div>`;
  h += `<div class="recon-summary-pill"><b>${sb.unique_targets}</b> 个目标</div>`;
  Object.entries(sb.type_breakdown || {}).forEach(([type, count]) => {
    h += `<div class="recon-summary-pill"><b>${count}</b> ${escapeHtml(type)}</div>`;
  });
  bar.innerHTML = h;
}

function applyFilters() {
  const checkedTypes = new Set(
    Array.from(document.querySelectorAll('#recon-filter input[type="checkbox"]:checked')).map(cb => cb.value)
  );
  const targetFilter = document.getElementById('target-filter').value;
  const searchLower = state.search.toLowerCase();

  state.filteredItems = state.allItems.filter(item => {
    if (!checkedTypes.has(item.record_type)) return false;
    if (targetFilter && item.target !== targetFilter) return false;
    if (searchLower) {
      const text = `${item.target} ${item.record_type} ${JSON.stringify(item.value)}`.toLowerCase();
      if (!text.includes(searchLower)) return false;
    }
    return true;
  });

  renderResults();
}

function renderResults() {
  const list = document.getElementById('results-list');
  if (state.filteredItems.length === 0) {
    list.innerHTML = '<div class="recon-empty">无匹配记录</div>';
    return;
  }

  let h = '';
  state.filteredItems.forEach(item => {
    const typeClass = getTypeClass(item.record_type);
    const time = item.created_at
      ? new Date(item.created_at * 1000).toLocaleString()
      : '';
    const valueJson = JSON.stringify(item.value, null, 2);

    h += `<div class="recon-card">
      <div class="recon-card-header">
        <span class="recon-type-badge ${typeClass}">${escapeHtml(item.record_type)}</span>
        <span style="font-size:11px;color:var(--text-muted);">#${item.id}</span>
      </div>
      <div class="recon-target">${escapeHtml(item.target)}</div>
      <div class="recon-value">${escapeHtml(valueJson)}</div>
      <div class="recon-meta">
        <span>来源: ${escapeHtml(item.source_step_id || '-')}</span>
        ${item.confidence !== null && item.confidence !== undefined ? `<span>置信度: ${(item.confidence * 100).toFixed(0)}%</span>` : ''}
        <span>${time}</span>
      </div>
    </div>`;
  });

  list.innerHTML = h;
}

function renderEmpty(msg) {
  document.getElementById('results-list').innerHTML = `<div class="recon-empty">${escapeHtml(msg)}</div>`;
  document.getElementById('summary-bar').innerHTML = '';
}

function onTaskChange() {
  const selector = document.getElementById('task-selector');
  state.taskId = selector.value;
  loadRecon();
}

function onSearch() {
  state.search = document.getElementById('search-input').value;
  applyFilters();
}

function updateUrl() {
  if (state.taskId) {
    history.replaceState(null, '', `?task_id=${encodeURIComponent(state.taskId)}`);
  } else {
    history.replaceState(null, '', location.pathname);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadTasks().then(() => {
    if (state.taskId) {
      loadRecon();
    }
  });
});
