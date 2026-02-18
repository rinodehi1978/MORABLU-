const API = '/api';

async function api(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API Error ${res.status}`);
  }
  return res.json();
}

function formatNumber(n) {
  return n.toLocaleString('ja-JP');
}

function initPickers() {
  const now = new Date();
  const yearSel = document.querySelector('#pick-year');
  const monthSel = document.querySelector('#pick-month');

  // 年: 2026から現在年まで
  for (let y = 2026; y <= now.getFullYear(); y++) {
    const opt = document.createElement('option');
    opt.value = y;
    opt.textContent = `${y}年`;
    if (y === now.getFullYear()) opt.selected = true;
    yearSel.appendChild(opt);
  }

  // 月: 1-12
  for (let m = 1; m <= 12; m++) {
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = `${m}月`;
    if (m === now.getMonth() + 1) opt.selected = true;
    monthSel.appendChild(opt);
  }
}

async function loadUsage() {
  const year = document.querySelector('#pick-year').value;
  const month = document.querySelector('#pick-month').value;
  const container = document.querySelector('#usage-content');

  container.innerHTML = '<div class="no-data">読み込み中...</div>';

  try {
    const data = await api(`/ai/usage?year=${year}&month=${month}`);
    renderUsage(data, container);
  } catch (err) {
    container.innerHTML = `<div class="no-data" style="color:var(--danger);">エラー: ${err.message}</div>`;
  }
}

function renderUsage(data, container) {
  if (data.total.count === 0) {
    container.innerHTML = `<div class="no-data">${data.year}年${data.month}月のAI利用データはありません</div>`;
    return;
  }

  // 為替レート（概算）
  const JPY_RATE = 150;

  let html = `
    <table class="usage-table">
      <thead>
        <tr>
          <th>アカウント</th>
          <th>AI生成回数</th>
          <th>入力トークン</th>
          <th>出力トークン</th>
          <th>コスト (USD)</th>
          <th>コスト (JPY)</th>
        </tr>
      </thead>
      <tbody>
  `;

  data.accounts.forEach(a => {
    const jpyCost = Math.round(a.cost_usd * JPY_RATE);
    html += `
      <tr>
        <td><strong>${a.account_name}</strong></td>
        <td>${formatNumber(a.count)}</td>
        <td>${formatNumber(a.input_tokens)}</td>
        <td>${formatNumber(a.output_tokens)}</td>
        <td>$${a.cost_usd.toFixed(4)}</td>
        <td class="cost-highlight">&yen;${formatNumber(jpyCost)}</td>
      </tr>
    `;
  });

  const totalJpy = Math.round(data.total.cost_usd * JPY_RATE);
  html += `
      <tr class="total-row">
        <td>合計</td>
        <td>${formatNumber(data.total.count)}</td>
        <td>${formatNumber(data.total.input_tokens)}</td>
        <td>${formatNumber(data.total.output_tokens)}</td>
        <td>$${data.total.cost_usd.toFixed(4)}</td>
        <td class="cost-highlight">&yen;${formatNumber(totalJpy)}</td>
      </tr>
    </tbody>
    </table>
    <div class="jpy-note">
      * JPY換算は概算レート（1 USD = ${JPY_RATE} JPY）です。損益計算書には実際のレートをご使用ください。<br>
      * Claude Sonnet 4.5 料金: 入力 $3.00/100万トークン、出力 $15.00/100万トークン
    </div>
  `;

  container.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', () => {
  initPickers();
  loadUsage();
});
