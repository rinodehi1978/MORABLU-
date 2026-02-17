const API = '/api';
let messages = [];
let accounts = [];
let selectedMessageId = null;

// --- Utilities ---
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '今';
  if (mins < 60) return `${mins}分前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}時間前`;
  return `${Math.floor(hrs / 24)}日前`;
}

function formatDateTime(dateStr) {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleString('ja-JP', {
    month: 'numeric', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function statusLabel(status) {
  const map = { new: '新着', ai_drafted: 'AI回答済', reviewed: '確認済', sent: '送信済', handled: '対応済' };
  return map[status] || status;
}

const CATEGORY_LABELS = {
  shipping: '発送・配送', defect: '商品不備', return: '返品・交換',
  refund: '返金', cancel: 'キャンセル', spec: '仕様確認',
  receipt: '領収書', address: '届け先変更', delivery_time: '配送日時指定',
  resend: '再送', stock: '欠品', other: 'その他'
};

const CATEGORY_ICONS = {
  shipping: '\u{1F4E6}', defect: '\u{1F6A8}', return: '\u{1F504}',
  refund: '\u{1F4B0}', cancel: '\u{274C}', spec: '\u{1F50D}',
  receipt: '\u{1F4C4}', address: '\u{1F4CD}', delivery_time: '\u{1F552}',
  resend: '\u{1F4E8}', stock: '\u{1F4E6}', other: '\u{2753}'
};

// category_key完全一致で検索（キーワード検索は不要になった）

function showToast(msg, type = 'success') {
  const container = $('.toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// --- API Calls ---
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

async function loadAccounts() {
  accounts = await api('/accounts/');
  const sel = $('#filter-account');
  sel.innerHTML = '<option value="">全アカウント</option>';
  accounts.forEach(a => {
    sel.innerHTML += `<option value="${a.id}">${a.name}</option>`;
  });
}

async function loadMessages() {
  const params = new URLSearchParams();
  const accountId = $('#filter-account').value;
  const status = $('#filter-status').value;
  const search = $('#filter-search').value;
  if (accountId) params.set('account_id', accountId);
  if (status) params.set('status', status);
  if (search) params.set('search', search);
  params.set('limit', '100');

  messages = await api(`/messages/?${params}`);
  renderMessageList();
  updateStats();
}

// --- Rendering ---
function renderMessageList() {
  const list = $('.message-list');
  if (messages.length === 0) {
    list.innerHTML = '<div style="padding:24px;text-align:center;color:#80868b">メッセージがありません</div>';
    return;
  }

  list.innerHTML = messages.map(m => `
    <div class="message-item status-${m.status} ${m.id === selectedMessageId ? 'active' : ''}"
         data-id="${m.id}" onclick="selectMessage(${m.id})">
      <div class="msg-header">
        <span class="msg-sender">${esc(m.sender)}</span>
        <span class="msg-time">${timeAgo(m.received_at)}</span>
      </div>
      <div class="msg-subject">${esc(m.subject || '(件名なし)')}</div>
      <div class="msg-preview">${esc(m.body)}</div>
      <div class="msg-meta">
        <span class="badge badge-account">${esc(m.account_name || '')}</span>
        <span class="badge badge-status-${m.status}">${statusLabel(m.status)}</span>
        ${m.question_category ? `<span class="badge badge-category">${CATEGORY_LABELS[m.question_category] || m.question_category}</span>` : ''}
      </div>
    </div>
  `).join('');
}

function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function selectMessage(id) {
  selectedMessageId = id;
  renderMessageList();
  renderDetail();
}

function renderDetail() {
  const panel = $('.main-panel');
  const msg = messages.find(m => m.id === selectedMessageId);

  if (!msg) {
    panel.innerHTML = '<div class="detail-empty">左のメッセージを選択してください</div>';
    return;
  }

  panel.innerHTML = `
    <div class="detail-view">
      <div class="detail-header">
        <h2>${esc(msg.subject || '(件名なし)')}</h2>
        <div class="detail-info">
          <span><strong>送信者:</strong> ${esc(msg.sender)}</span>
          <span><strong>アカウント:</strong> ${esc(msg.account_name)}</span>
          <span><strong>注文:</strong> ${esc(msg.external_order_id || '-')}</span>
          <span><strong>ASIN:</strong> ${esc(msg.asin || '-')}</span>
          <span><strong>商品:</strong> ${esc(msg.product_title || '-')}</span>
        </div>
      </div>
      <div id="thread-area">
        <div style="padding:16px;color:#5f6368;">読み込み中...</div>
      </div>
    </div>
  `;

  loadAndRenderThread(msg);
}

async function loadAndRenderThread(currentMsg) {
  const threadArea = $('#thread-area');
  if (!threadArea) return;

  try {
    const data = await api(`/messages/${currentMsg.id}/thread`);
    renderThread(data, currentMsg);
  } catch (err) {
    threadArea.innerHTML = `
      <div style="padding:12px;color:var(--danger);">読み込みエラー: ${esc(err.message)}</div>
    `;
  }
}

function renderThread(data, currentMsg) {
  const threadArea = $('#thread-area');
  if (!threadArea) return;

  const thread = data.thread;
  let html = '';

  if (thread.length > 1) {
    html += `<div style="padding:4px 0 8px;font-size:12px;color:#5f6368;">
      注文 ${esc(data.order_id)} のやり取り（${thread.length}件のメッセージ）
    </div>`;
  }

  thread.forEach((entry, threadIdx) => {
    const m = entry.message;
    const responses = entry.responses;
    const isCurrentMsg = m.id === currentMsg.id;

    // --- お客様のメッセージ ---
    html += `
      <div class="section" style="${isCurrentMsg ? '' : 'opacity:0.85;'}">
        <div class="section-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>お客様のメッセージ${thread.length > 1 ? ` #${threadIdx + 1}` : ''}</span>
          <span style="font-size:11px;color:#80868b;">${formatDateTime(m.received_at)}</span>
        </div>
        ${m.subject ? `<div style="font-size:12px;color:#5f6368;margin-bottom:4px;">件名: ${esc(m.subject)}</div>` : ''}
        <div class="message-bubble">${esc(m.body)}</div>
      </div>
    `;

    // --- 送信済みの回答 ---
    const sentResponses = responses.filter(r => r.is_sent && r.final_body);
    sentResponses.forEach(r => {
      html += `
        <div class="section">
          <div class="section-title" style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:var(--success);">送信済み回答</span>
            <span style="font-size:11px;color:#80868b;">${formatDateTime(r.sent_at)}</span>
          </div>
          <div class="message-bubble" style="background:#e8f5e9;border-left:3px solid var(--success);">
            <div style="font-size:14px;white-space:pre-wrap;line-height:1.7;">${esc(r.final_body)}</div>
          </div>
          ${r.draft_body !== r.final_body ? `
            <details style="margin-top:4px;">
              <summary style="font-size:11px;color:#80868b;cursor:pointer;">元のAI回答案を表示</summary>
              <div style="font-size:12px;white-space:pre-wrap;line-height:1.5;margin-top:4px;padding:8px;background:#f5f5f5;border-radius:4px;color:#666;">${esc(r.draft_body)}</div>
            </details>
          ` : ''}
        </div>
      `;
    });

    // --- 現在のメッセージ: アクションUI ---
    if (isCurrentMsg) {
      const unsent = responses.filter(r => !r.is_sent);
      const latestUnsent = unsent.length > 0 ? unsent[unsent.length - 1] : null;

      if (latestUnsent) {
        // 未送信の下書きがある → エディタ表示
        html += renderDraftEditor(latestUnsent);
      } else if (m.status === 'handled') {
        // 対応済み
        html += `<div class="section" style="text-align:center;padding:16px;color:var(--text-light);">
          <div style="font-size:14px;margin-bottom:8px;">このメッセージは対応済みです</div>
          <button class="btn btn-outline btn-sm" onclick="handleUnmarkHandled(${m.id})">新着に戻す</button>
        </div>`;
      } else if (sentResponses.length === 0) {
        // 未回答 → スタッフがカテゴリ選択 → テンプレート選択 or AI生成
        html += `<div class="section" id="action-section"></div>`;
        // カテゴリ選択UIを即表示（API呼び出し不要）
        setTimeout(() => showCategoryPicker(m), 0);
      } else {
        // 送信済みのみ
        html += `<div class="section" id="action-section">
          <button class="btn btn-outline btn-sm" onclick="handleRegenerate()">
            新しいAI回答案を生成（APIコスト発生）
          </button>
        </div>`;
      }
    }
  });

  threadArea.innerHTML = html;
}

// --- カテゴリ手動選択 → テンプレート表示 ---
function showCategoryPicker(msg) {
  const section = $('#action-section');
  if (!section) return;

  const preSelected = msg.question_category || '';

  let html = `
    <div class="template-picker">
      <div style="margin-bottom:12px;">
        <div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">カテゴリを選択</div>
        <div class="category-buttons" id="category-buttons">
  `;

  Object.entries(CATEGORY_LABELS).forEach(([key, label]) => {
    const icon = CATEGORY_ICONS[key] || '';
    const selected = key === preSelected ? ' selected' : '';
    html += `<button class="category-btn${selected}" data-cat="${key}" onclick="onCategorySelect('${key}')">${icon} ${label}</button>`;
  });

  html += `
        </div>
      </div>
      <div id="template-area">
        ${preSelected ? '' : '<div style="padding:16px;text-align:center;color:var(--text-light);font-size:13px;">カテゴリを選択するとテンプレートが表示されます</div>'}
      </div>
      <div class="action-divider">または</div>
      <div style="text-align:center;display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
        <button class="btn btn-primary" onclick="handleGenerate()" id="btn-ai-generate">
          AI回答案を生成（~$0.02）
        </button>
        <button class="btn btn-outline" onclick="handleMarkHandled()" title="既にSeller Central等で対応済みの場合">
          対応済みにする
        </button>
      </div>
    </div>
    <div id="editor-area" style="display:none;"></div>
  `;

  section.innerHTML = html;

  // 既にカテゴリが設定済みならテンプレートを即表示
  if (preSelected) {
    onCategorySelect(preSelected);
  }
}

async function onCategorySelect(category) {
  // ボタンの選択状態を更新
  $$('.category-btn').forEach(b => b.classList.remove('selected'));
  const btn = $(`.category-btn[data-cat="${category}"]`);
  if (btn) btn.classList.add('selected');

  // エディタをリセット
  const editorArea = $('#editor-area');
  if (editorArea) editorArea.style.display = 'none';

  // メッセージのカテゴリを更新
  const msg = messages.find(m => m.id === selectedMessageId);
  if (msg) {
    msg.question_category = category;
    renderMessageList();
  }

  // テンプレートを取得（ローカルAPI、AI不使用）
  const templateArea = $('#template-area');
  if (!templateArea) return;

  // アカウントのプラットフォームを取得
  const account = accounts.find(a => a.id === msg?.account_id);
  const platform = account?.channel || 'amazon';

  try {
    // category_keyで完全一致検索（キーワード検索ではなく正確な紐づけ）
    const templates = await api(`/qa-templates/?category_key=${encodeURIComponent(category)}&platform=${encodeURIComponent(platform)}`);
    renderTemplateCards(templateArea, category, templates);
  } catch (err) {
    templateArea.innerHTML = `<div style="padding:12px;color:var(--danger);font-size:13px;">テンプレート取得エラー: ${esc(err.message)}</div>`;
  }
}

function renderTemplateCards(container, category, templates) {
  const icon = CATEGORY_ICONS[category] || '';
  const label = CATEGORY_LABELS[category] || category;

  let html = '';

  if (templates.length > 0) {
    html += `
      <div style="font-size:13px;color:var(--text-secondary);margin-bottom:10px;">
        ${esc(label)} のテンプレート（${templates.length}件） — 選択して回答（APIコスト不要）
      </div>
      <div class="template-grid">
    `;

    templates.forEach((t, idx) => {
      const preview = (t.answer_template || '').substring(0, 150);
      const title = t.subcategory
        ? `${esc(t.category)} - ${esc(t.subcategory)}`
        : esc(t.category);
      const platformLabel = t.platform === 'common' ? '' : t.platform;

      html += `
        <div class="template-card" data-idx="${idx}" onclick="selectTemplate(${idx})">
          <div class="template-card-title">
            ${title}
            ${platformLabel ? `<span class="platform-tag">${esc(platformLabel)}</span>` : ''}
          </div>
          <div class="template-card-preview">${esc(preview)}${preview.length >= 150 ? '...' : ''}</div>
          ${t.staff_notes ? `<div class="template-card-notes">メモ: ${esc(t.staff_notes)}</div>` : ''}
        </div>
      `;
    });

    html += `</div>`;
  } else {
    html += `
      <div style="padding:16px;text-align:center;color:var(--text-light);font-size:13px;background:#f8f9fa;border-radius:var(--radius);">
        「${esc(label)}」のテンプレートはまだありません
      </div>
    `;
  }

  container.innerHTML = html;

  // テンプレートデータを保存（selectTemplateで使用）
  const section = $('#action-section');
  if (section) section._templates = templates;
}


function selectTemplate(idx) {
  const section = $('#action-section');
  if (!section || !section._templates) return;
  const template = section._templates[idx];
  if (!template) return;

  // カードの選択状態を更新
  $$('.template-card').forEach(c => c.classList.remove('selected'));
  const card = $(`.template-card[data-idx="${idx}"]`);
  if (card) card.classList.add('selected');

  // エディタエリアに回答テンプレートを展開
  const editorArea = $('#editor-area');
  if (!editorArea) return;

  editorArea.style.display = 'block';
  editorArea.innerHTML = `
    <div style="margin-top:20px;">
      <div class="section-title">回答を編集して送信</div>
      ${template.staff_notes ? `
        <div style="background:#fff8e1;padding:8px 12px;border-radius:var(--radius);margin-bottom:12px;font-size:12px;color:#b06000;border-left:3px solid var(--warning);">
          <strong>スタッフメモ:</strong> ${esc(template.staff_notes)}
        </div>
      ` : ''}
      <textarea class="response-editor" id="response-text">${esc(template.answer_template)}</textarea>
      <div class="action-bar">
        <button class="btn btn-success" id="btn-send" onclick="handleSendDirect()">
          確認して送信
        </button>
      </div>
    </div>
  `;

  // エディタにスクロール
  editorArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// --- Handlers ---
async function handleGenerate() {
  const msg = messages.find(m => m.id === selectedMessageId);
  if (!msg) return;

  const section = $('#action-section');
  if (section) {
    section.innerHTML = `
      <div style="padding:24px;color:#5f6368;text-align:center;">
        <span class="spinner" style="border-color:var(--primary);border-top-color:transparent;width:24px;height:24px;"></span>
        <div style="margin-top:8px;">AI回答案を生成中...</div>
        <div style="font-size:11px;color:var(--text-light);margin-top:4px;">カテゴリ分類 + 回答生成（10〜15秒）</div>
      </div>
    `;
  }

  try {
    const result = await api('/ai/generate', {
      method: 'POST',
      body: JSON.stringify({ message_id: msg.id }),
    });
    msg.status = 'ai_drafted';
    msg.question_category = result.ai_suggested_category;
    renderMessageList();
    renderDetail();
  } catch (err) {
    if (section) {
      section.innerHTML = `
        <div style="padding:16px;color:var(--danger);">エラー: ${esc(err.message)}</div>
        <button class="btn btn-outline" onclick="handleGenerate()">再試行</button>
      `;
    }
  }
}

async function handleRegenerate() {
  if (!confirm('AI回答を再生成します。APIコスト（従量課金）が発生します。\n\n続けますか？')) return;
  await handleGenerate();
}

async function handleSend(responseId) {
  const finalBody = $('#response-text').value.trim();
  if (!finalBody) { showToast('回答を入力してください', 'error'); return; }

  const btn = $('#btn-send');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>送信中...';

  const msg = messages.find(m => m.id === selectedMessageId);
  const selectedCategory = $('#send-category')?.value;
  const originalCategory = msg?.question_category;
  const corrected = selectedCategory !== originalCategory ? selectedCategory : null;

  try {
    await api(`/ai/${responseId}/send`, {
      method: 'PUT',
      body: JSON.stringify({ final_body: finalBody, corrected_category: corrected }),
    });
    showToast('送信完了しました');
    if (msg) {
      msg.status = 'sent';
      if (corrected) msg.question_category = corrected;
    }
    renderMessageList();
    renderDetail();
  } catch (err) {
    showToast(`送信失敗: ${err.message}`, 'error');
    btn.disabled = false;
    btn.textContent = '確認して送信';
  }
}

async function handleSendDirect() {
  // テンプレートから直接送信（AI生成なし）
  const finalBody = $('#response-text').value.trim();
  if (!finalBody) { showToast('回答を入力してください', 'error'); return; }

  const btn = $('#btn-send');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>送信中...';

  const msg = messages.find(m => m.id === selectedMessageId);

  try {
    // テンプレート直送信: AI生成せずにAiResponseレコードを作成して即送信
    const result = await api('/ai/send-direct', {
      method: 'POST',
      body: JSON.stringify({
        message_id: msg.id,
        final_body: finalBody,
      }),
    });
    showToast('送信完了しました');
    if (msg) msg.status = 'sent';
    renderMessageList();
    renderDetail();
  } catch (err) {
    showToast(`送信失敗: ${err.message}`, 'error');
    btn.disabled = false;
    btn.textContent = '確認して送信';
  }
}

async function handleDiscard(responseId) {
  if (!confirm('この下書きを破棄しますか？')) return;

  try {
    const result = await api(`/ai/${responseId}/discard`, { method: 'DELETE' });
    showToast('下書きを破棄しました');
    const msg = messages.find(m => m.id === selectedMessageId);
    if (msg && result.message_status) msg.status = result.message_status;
    renderMessageList();
    renderDetail();
  } catch (err) {
    showToast(`破棄に失敗: ${err.message}`, 'error');
  }
}

function renderDraftEditor(draft) {
  return `
    <div class="section">
      <div class="section-title">AI回答案</div>
      <div class="ai-draft-area" style="margin-bottom:12px;">
        <div class="draft-label">
          AI生成 (${formatDateTime(draft.created_at)})
          カテゴリ: ${CATEGORY_LABELS[draft.ai_suggested_category] || draft.ai_suggested_category || '未分類'}
        </div>
        <div style="font-size:14px;white-space:pre-wrap;line-height:1.7;">${esc(draft.draft_body)}</div>
      </div>

      <div class="section-title">回答を編集して送信</div>
      <div class="category-row">
        <label>カテゴリ修正:</label>
        <select id="send-category">
          ${Object.entries(CATEGORY_LABELS)
            .map(([k, v]) => `<option value="${k}" ${k === draft.ai_suggested_category ? 'selected' : ''}>${v}</option>`)
            .join('')}
        </select>
      </div>
      <textarea class="response-editor" id="response-text">${esc(draft.draft_body)}</textarea>
      <div class="action-bar">
        <button class="btn btn-success" id="btn-send" onclick="handleSend(${draft.id})">
          確認して送信
        </button>
        <button class="btn btn-outline btn-sm" onclick="handleRegenerate()">再生成</button>
        <button class="btn btn-danger-outline btn-sm" onclick="handleDiscard(${draft.id})">
          下書き破棄
        </button>
      </div>
    </div>
  `;
}

async function handleMarkHandled() {
  const msg = messages.find(m => m.id === selectedMessageId);
  if (!msg) return;

  try {
    await api(`/messages/${msg.id}/handled`, { method: 'PUT' });
    msg.status = 'handled';
    showToast('対応済みにしました');
    renderMessageList();
    renderDetail();
  } catch (err) {
    showToast(`エラー: ${err.message}`, 'error');
  }
}

async function handleUnmarkHandled(messageId) {
  try {
    await api(`/messages/${messageId}/reopen`, { method: 'PUT' });
    const msg = messages.find(m => m.id === messageId);
    if (msg) msg.status = 'new';
    showToast('新着に戻しました');
    renderMessageList();
    renderDetail();
  } catch (err) {
    showToast(`エラー: ${err.message}`, 'error');
  }
}

function updateStats() {
  const total = messages.length;
  const newCount = messages.filter(m => m.status === 'new').length;
  const draftCount = messages.filter(m => m.status === 'ai_drafted').length;
  const sentCount = messages.filter(m => m.status === 'sent').length;
  const handledCount = messages.filter(m => m.status === 'handled').length;
  $('.header .stats').textContent =
    `全${total}件 | 新着${newCount} | AI回答済${draftCount} | 送信済${sentCount} | 対応済${handledCount}`;
}

// --- メッセージ取込 ---
async function handleFetchMessages() {
  const btn = $('#btn-fetch');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" style="border-color:var(--primary);border-top-color:transparent;width:12px;height:12px;"></span> 取込中...';

  try {
    const result = await api('/messages/fetch', { method: 'POST' });
    const totalNew = result.total_new;
    if (totalNew > 0) {
      showToast(`${totalNew}件の新しいメッセージを取込みました`);
      await loadMessages();
    } else {
      showToast('新しいメッセージはありません');
    }
  } catch (err) {
    showToast(`取込エラー: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'メッセージ取込';
  }
}

// --- Event Listeners ---
let searchTimer;
function onSearchInput() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadMessages, 300);
}

// --- Init ---
async function init() {
  await loadAccounts();
  await loadMessages();

  $('#filter-account').addEventListener('change', loadMessages);
  $('#filter-status').addEventListener('change', loadMessages);
  $('#filter-search').addEventListener('input', onSearchInput);

  setInterval(loadMessages, 30000);
}

document.addEventListener('DOMContentLoaded', init);
