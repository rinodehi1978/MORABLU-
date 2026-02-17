const API = '/api';
let templates = [];

function $(sel) { return document.querySelector(sel); }

const PLATFORM_LABELS = {
  common: '共通', amazon: 'Amazon', yahoo_auction: 'ヤフオク',
  yahoo_shopping: 'Yahoo!ショ', mercari: 'メルカリ',
  rakuten: '楽天', multi_channel: 'マルチCH'
};

const CATEGORY_LABELS = {
  shipping: '発送・配送', defect: '商品不備', return: '返品・交換',
  refund: '返金', cancel: 'キャンセル', spec: '仕様確認',
  receipt: '領収書', address: '届け先変更', delivery_time: '配送日時指定',
  resend: '再送', stock: '欠品', other: 'その他'
};

function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function showToast(msg, type = 'success') {
  const container = $('.toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// --- API ---
async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API Error ${res.status}`);
  }
  return res.json();
}

// --- Load & Render ---
async function loadTemplates() {
  const params = new URLSearchParams();
  const search = $('#filter-search').value;
  const platform = $('#filter-platform').value;
  if (search) params.set('search', search);
  if (platform) params.set('platform', platform);

  templates = await api(`/qa-templates/?${params}`);
  renderTable();
  $('#stats').textContent = `全${templates.length}件`;
}

function renderTable() {
  const tbody = $('#template-body');

  if (templates.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:#80868b;">テンプレートがありません</td></tr>';
    return;
  }

  tbody.innerHTML = templates.map(t => {
    const preview = (t.answer_template || '').substring(0, 80);
    const notesPreview = (t.staff_notes || '').substring(0, 30);
    const catLabel = CATEGORY_LABELS[t.category_key] || t.category_key;
    return `
      <tr>
        <td><span class="badge badge-category">${esc(catLabel)}</span></td>
        <td class="cell-category">${esc(t.category)}</td>
        <td>${esc(t.subcategory || '-')}</td>
        <td><span class="platform-label platform-${t.platform}">${PLATFORM_LABELS[t.platform] || t.platform}</span></td>
        <td class="cell-preview">${esc(preview)}${preview.length >= 80 ? '...' : ''}</td>
        <td class="cell-notes">${notesPreview ? esc(notesPreview) + (notesPreview.length >= 30 ? '...' : '') : '-'}</td>
        <td class="cell-actions">
          <button class="btn-icon" title="編集" onclick="openEditModal(${t.id})">&#9998;</button>
          <button class="btn-icon btn-icon-danger" title="削除" onclick="deleteTemplate(${t.id})">&#128465;</button>
        </td>
      </tr>
    `;
  }).join('');
}

// --- Modal ---
function openModal() {
  $('#modal-title').textContent = 'テンプレート新規作成';
  $('#edit-id').value = '';
  $('#edit-category-key').value = '';
  $('#edit-category').value = '';
  $('#edit-subcategory').value = '';
  $('#edit-platform').value = 'common';
  $('#edit-template').value = '';
  $('#edit-notes').value = '';
  $('#btn-save').textContent = '作成';
  $('#modal-overlay').classList.add('show');
}

function openEditModal(id) {
  const t = templates.find(x => x.id === id);
  if (!t) return;

  $('#modal-title').textContent = 'テンプレート編集';
  $('#edit-id').value = t.id;
  $('#edit-category-key').value = t.category_key || 'other';
  $('#edit-category').value = t.category;
  $('#edit-subcategory').value = t.subcategory || '';
  $('#edit-platform').value = t.platform;
  $('#edit-template').value = t.answer_template;
  $('#edit-notes').value = t.staff_notes || '';
  $('#btn-save').textContent = '保存';
  $('#modal-overlay').classList.add('show');
}

function closeModal() {
  $('#modal-overlay').classList.remove('show');
}

// --- CRUD ---
async function saveTemplate() {
  const id = $('#edit-id').value;
  const category_key = $('#edit-category-key').value;
  const category = $('#edit-category').value.trim();
  const answer_template = $('#edit-template').value.trim();

  if (!category_key) { showToast('カテゴリを選択してください', 'error'); return; }
  if (!category) { showToast('質問タイトルを入力してください', 'error'); return; }
  if (!answer_template) { showToast('回答テンプレートを入力してください', 'error'); return; }

  const data = {
    category_key,
    category,
    subcategory: $('#edit-subcategory').value.trim() || null,
    platform: $('#edit-platform').value,
    answer_template,
    staff_notes: $('#edit-notes').value.trim() || null,
  };

  const btn = $('#btn-save');
  btn.disabled = true;

  try {
    if (id) {
      await api(`/qa-templates/${id}`, { method: 'PUT', body: JSON.stringify(data) });
      showToast('テンプレートを更新しました');
    } else {
      await api('/qa-templates/', { method: 'POST', body: JSON.stringify(data) });
      showToast('テンプレートを作成しました');
    }
    closeModal();
    await loadTemplates();
  } catch (err) {
    showToast(`保存失敗: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
  }
}

async function deleteTemplate(id) {
  const t = templates.find(x => x.id === id);
  if (!t) return;
  if (!confirm(`「${t.category}」を削除しますか？\n\nこの操作は取り消せません。`)) return;

  try {
    await api(`/qa-templates/${id}`, { method: 'DELETE' });
    showToast('テンプレートを削除しました');
    await loadTemplates();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'error');
  }
}

// --- Events ---
let searchTimer;
function onSearchInput() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadTemplates, 300);
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  loadTemplates();
  $('#filter-search').addEventListener('input', onSearchInput);
  $('#filter-platform').addEventListener('change', loadTemplates);
});
