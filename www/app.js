/* ===================================================================
   PENNY BUDDY — Frontend Application
   app.js — API-driven state, rendering, and interactions
   All data comes from the Flask + SQLite backend (server.py)
   =================================================================== */

const API = '';  // same origin

// ===== CAPACITOR NATIVE BRIDGE =====
const isNativeApp = typeof window.Capacitor !== 'undefined';

async function initNativeBridge() {
  if (!isNativeApp) return;

  try {
    // Status bar styling
    const { StatusBar } = window.Capacitor.Plugins;
    if (StatusBar) {
      StatusBar.setBackgroundColor({ color: '#4F46E5' });
      StatusBar.setStyle({ style: 'LIGHT' });
    }
  } catch (e) { /* not available */ }

  try {
    // Haptic feedback helper
    const { Haptics } = window.Capacitor.Plugins;
    if (Haptics) {
      window.hapticFeedback = () => Haptics.impact({ style: 'LIGHT' });
    }
  } catch (e) { /* not available */ }

  try {
    // Keyboard handling
    const { Keyboard } = window.Capacitor.Plugins;
    if (Keyboard) {
      Keyboard.addListener('keyboardWillShow', (info) => {
        document.body.style.setProperty('--keyboard-height', info.keyboardHeight + 'px');
        document.body.classList.add('keyboard-open');
      });
      Keyboard.addListener('keyboardWillHide', () => {
        document.body.style.setProperty('--keyboard-height', '0px');
        document.body.classList.remove('keyboard-open');
      });
    }
  } catch (e) { /* not available */ }

  try {
    // Handle back button on Android
    const { App } = window.Capacitor.Plugins;
    if (App) {
      App.addListener('backButton', () => {
        const activeScreen = document.querySelector('.screen.active');
        if (activeScreen && activeScreen.id !== 'dashboard') {
          navigateTo('dashboard');
        } else {
          App.exitApp();
        }
      });
    }
  } catch (e) { /* not available */ }

  // Hide splash screen after load
  try {
    const { SplashScreen } = window.Capacitor.Plugins;
    if (SplashScreen) {
      SplashScreen.hide();
    }
  } catch (e) { /* not available */ }
}

// Schedule EMI reminder notifications natively
async function scheduleEmiNotification(name, amount, dueDate) {
  if (!isNativeApp) return;
  try {
    const { LocalNotifications } = window.Capacitor.Plugins;
    if (!LocalNotifications) return;

    const due = new Date(dueDate);
    const reminderDate = new Date(due);
    reminderDate.setDate(reminderDate.getDate() - 1);
    reminderDate.setHours(9, 0, 0, 0);

    if (reminderDate > new Date()) {
      await LocalNotifications.schedule({
        notifications: [{
          title: 'EMI Due Tomorrow',
          body: `${name} payment of ${amount} is due tomorrow`,
          id: Math.floor(Math.random() * 100000),
          schedule: { at: reminderDate },
          sound: 'default',
          actionTypeId: 'EMI_REMINDER'
        }]
      });
    }
  } catch (e) { /* not available */ }
}

// ===== CURRENCY CONFIGURATION =====
const CURRENCIES = {
  INR: { symbol: '\u20b9', code: 'INR', name: 'Indian Rupee', locale: 'en-IN' },
  USD: { symbol: '$', code: 'USD', name: 'US Dollar', locale: 'en-US' },
  EUR: { symbol: '\u20ac', code: 'EUR', name: 'Euro', locale: 'de-DE' },
  GBP: { symbol: '\u00a3', code: 'GBP', name: 'British Pound', locale: 'en-GB' }
};

// ===== APP STATE (loaded from API) =====
let user = null;       // user profile from /api/user
let txFilter = 'all';
let selectedMonth = null;
let selectedYear = null;

function getCurrency() {
  return CURRENCIES[(user && user.currency) || 'INR'];
}

// ===== FORMATTING =====
function fmt(n) {
  const c = getCurrency();
  const prefix = n < 0 ? '-' : '';
  return prefix + c.symbol + Math.abs(n).toLocaleString(c.locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtShort(n) {
  const c = getCurrency();
  const prefix = n < 0 ? '-' : '';
  return prefix + c.symbol + Math.abs(n).toLocaleString(c.locale, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

// ===== API HELPERS =====
async function api(endpoint, options = {}) {
  const fetchOpts = { method: options.method || 'GET' };
  if (options.body) {
    fetchOpts.headers = { 'Content-Type': 'application/json' };
    fetchOpts.body = JSON.stringify(options.body);
  }
  const res = await fetch(API + endpoint, fetchOpts);
  return res.json();
}

function getMonthStr(y, m) {
  return `${y}-${String(m + 1).padStart(2, '0')}`;
}

// ===== INITIALIZATION =====
async function init() {
  const now = new Date();
  selectedMonth = now.getMonth();
  selectedYear = now.getFullYear();

  const data = await api('/api/user');
  if (data.exists) {
    user = data;
    if (user.theme === 'dark') document.documentElement.dataset.theme = 'dark';
    document.getElementById('onboarding').classList.remove('active');
    document.getElementById('app-shell').classList.add('active');
    await renderAll();
  }
  // else: stay on onboarding
}

// ===== ONBOARDING =====
let obStep = 1;

function nextOnboardingStep() {
  if (obStep === 1) {
    const name = document.getElementById('ob-name').value.trim();
    if (!name) { document.getElementById('ob-name').focus(); return; }
  }
  if (obStep === 2) {
    // Currency selected — update income/savings placeholders
    const sel = document.querySelector('#currency-grid .selected');
    const code = sel ? sel.dataset.currency : 'INR';
    const defaults = { INR: [45000, 8000], USD: [4500, 500], EUR: [3800, 450], GBP: [3200, 400] };
    const c = CURRENCIES[code];
    const d = defaults[code];
    document.getElementById('ob-income').placeholder = c.symbol + d[0].toLocaleString(c.locale);
    document.getElementById('ob-savings').placeholder = c.symbol + d[1].toLocaleString(c.locale);
  }
  obStep++;
  updateOnboarding();
}

function toggleCategory(el) { el.classList.toggle('selected'); }
function toggleCurrency(el) {
  document.querySelectorAll('#currency-grid .category-chip').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
}

async function completeOnboarding() {
  const name = document.getElementById('ob-name').value.trim();
  const currencyEl = document.querySelector('#currency-grid .selected');
  const currency = currencyEl ? currencyEl.dataset.currency : 'INR';
  const income = parseFloat(document.getElementById('ob-income').value.replace(/[^0-9.]/g, '')) || 0;
  const savings = parseFloat(document.getElementById('ob-savings').value.replace(/[^0-9.]/g, '')) || 0;
  const cats = [...document.querySelectorAll('#category-grid .selected')].map(c => c.dataset.cat);

  await api('/api/user', {
    method: 'POST',
    body: { name, currency, income, savings_target: savings, budget: 0, categories: cats, theme: 'light' }
  });

  // Auto-create this month's salary transaction so balance shows immediately
  if (income > 0) {
    await api('/api/transactions', {
      method: 'POST',
      body: {
        name: 'Monthly Salary',
        category: 'income',
        emoji: '\ud83d\udcb0',
        amount: income,
        type: 'income',
        date: new Date().toISOString().split('T')[0]
      }
    });
  }

  user = { name, currency, income, savings_target: savings, budget: 0, categories: cats, theme: 'light', exists: true };

  document.getElementById('onboarding').classList.remove('active');
  document.getElementById('app-shell').classList.add('active');
  await renderAll();
}

function updateOnboarding() {
  document.querySelectorAll('.onboarding-step').forEach(s => s.classList.remove('active'));
  document.querySelector(`.onboarding-step[data-step="${obStep}"]`).classList.add('active');
  document.querySelectorAll('.onboarding-dot').forEach((d, i) => {
    d.classList.toggle('active', i === obStep - 1);
  });
}

// ===== NAVIGATION =====
function navigateTo(viewId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(viewId);
  if (target) { target.classList.add('active'); }
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.view === viewId);
  });
  window.scrollTo(0, 0);
}

// ===== BOTTOM SHEETS =====
function openSheet(id) {
  document.getElementById('sheet-overlay').classList.add('active');
  document.getElementById('sheet-' + id).classList.add('active');
  document.body.style.overflow = 'hidden';
}
function closeSheet() {
  document.getElementById('sheet-overlay').classList.remove('active');
  document.querySelectorAll('.bottom-sheet').forEach(s => s.classList.remove('active'));
  document.body.style.overflow = '';
}

// ===== UTILITY =====
function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

function formatTimeAgo(dateStr) {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now - d;
  const days = Math.floor(diff / 86400000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return days + 'd ago';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function getISOWeek() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + 3 - (d.getDay() + 6) % 7);
  const week1 = new Date(d.getFullYear(), 0, 4);
  const wn = Math.round(((d - week1) / 86400000 - 3 + (week1.getDay() + 6) % 7) / 7) + 1;
  return `${d.getFullYear()}-W${wn}`;
}

// ===== RENDER ALL =====
async function renderAll() {
  await Promise.all([
    renderDashboard(),
    renderTransactions(),
    renderGoals(),
    renderInsights(),
    renderProfile(),
    renderEmiSection()
  ]);
  renderExpenseCategories();
  updateCurrencyPlaceholders();
}

function updateCurrencyPlaceholders() {
  const c = getCurrency();
  document.getElementById('quick-amount').placeholder = c.symbol + ' Amount';
  document.getElementById('due-amount').placeholder = c.symbol + '0';
  document.getElementById('income-amount').placeholder = c.symbol + '0';
  document.getElementById('expense-amount').placeholder = c.symbol + '0';
  document.getElementById('goal-add-amount').placeholder = c.symbol + '500';
  document.getElementById('budget-amount').placeholder = c.symbol + '30,000';
  document.getElementById('new-goal-target').placeholder = c.symbol + '25,000';
}

// ===== DASHBOARD =====
async function renderDashboard() {
  const now = new Date();
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  document.getElementById('greeting-date').textContent = months[now.getMonth()] + ' ' + now.getFullYear();
  document.getElementById('greeting-name').textContent = 'Hey, ' + (user.name || 'there');
  const initial = (user.name || 'U')[0].toUpperCase();
  document.getElementById('nav-avatar').textContent = initial;

  const month = getMonthStr(now.getFullYear(), now.getMonth());
  const summary = await api('/api/summary?month=' + month);

  document.getElementById('balance-amount').textContent = fmt(summary.balance);
  document.getElementById('dash-income').textContent = fmt(summary.income);
  document.getElementById('dash-spent').textContent = fmt(summary.expenses);
  document.getElementById('dash-saved').textContent = fmtShort(summary.total_saved);

  const ratio = summary.spending_ratio;
  document.getElementById('ratio-pct').textContent = Math.round(ratio) + '%';
  const bar = document.getElementById('ratio-bar');
  bar.style.width = Math.min(ratio, 100) + '%';
  bar.style.background = ratio < 70 ? '#10B981' : ratio < 90 ? '#F59E0B' : '#EF4444';

  // Goals preview
  const goals = await api('/api/goals');
  document.getElementById('goals-scroll').innerHTML = goals.length === 0
    ? '<p style="color:var(--text-secondary);font-size:0.8125rem;padding:8px 0">No goals yet — set one to start saving!</p>'
    : goals.map(g => {
      const pct = g.target > 0 ? Math.round((g.saved / g.target) * 100) : 0;
      return `<div class="card goal-mini-card" onclick="navigateTo('goals-screen')">
        <div class="goal-mini-top">
          <span class="goal-mini-emoji">${g.emoji}</span>
          <span class="goal-mini-name">${g.name}</span>
        </div>
        <div class="goal-mini-progress"><div class="goal-mini-progress-fill" style="width:${pct}%"></div></div>
        <div class="goal-mini-amount">${fmtShort(g.saved)} / ${fmtShort(g.target)}</div>
      </div>`;
    }).join('');

  // Recent transactions
  const txs = await api('/api/transactions?month=' + month);
  const recent = txs.slice(0, 5);
  document.getElementById('recent-transactions').innerHTML = recent.length === 0
    ? '<p style="color:var(--text-secondary);font-size:0.8125rem;padding:16px 0;text-align:center">No transactions yet. Add your first one!</p>'
    : recent.map(t => renderTxItem(t)).join('');

  // Pulse widget
  const pulse = await api('/api/pulse/current-week');
  const pulseWidget = document.getElementById('pulse-widget');
  if (pulse.completed) {
    pulseWidget.classList.add('pulse-done');
    pulseWidget.querySelector('h3').textContent = 'Pulse Complete \u2713';
    pulseWidget.querySelector('p').textContent = 'See your wellness score';
  } else {
    pulseWidget.classList.remove('pulse-done');
    pulseWidget.querySelector('h3').textContent = 'Weekly Money Pulse';
    pulseWidget.querySelector('p').textContent = 'Your check-in is ready \u2014 takes 30 seconds';
  }
}

function renderTxItem(t) {
  const timeStr = formatTimeAgo(t.date);
  const isExpense = t.amount < 0 || t.type === 'expense';
  const displayAmt = Math.abs(t.amount);
  return `<div class="transaction-item">
    <div class="tx-icon">${t.emoji}</div>
    <div class="tx-info">
      <div class="tx-name">${t.name}</div>
      <div class="tx-category">${capitalize(t.category)}</div>
    </div>
    <div style="text-align:right">
      <div class="tx-amount ${isExpense ? 'expense' : 'income'}">${isExpense ? '-' : '+'}${fmt(displayAmt)}</div>
      <div class="tx-time">${timeStr}</div>
    </div>
  </div>`;
}

// ===== TRANSACTIONS =====
async function renderTransactions() {
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const now = new Date();
  const pills = [];
  for (let i = 2; i >= 0; i--) {
    let m = now.getMonth() - i, yr = now.getFullYear();
    if (m < 0) { m += 12; yr--; }
    const active = m === selectedMonth && yr === selectedYear;
    pills.push(`<button class="month-pill${active ? ' active' : ''}" onclick="selectMonth(${m},${yr})">${months[m]} ${yr}</button>`);
  }
  document.getElementById('month-pills').innerHTML = pills.join('');

  const monthStr = getMonthStr(selectedYear, selectedMonth);
  const allTxs = await api('/api/transactions?month=' + monthStr);

  const income = allTxs.filter(t => t.type === 'income').reduce((s, t) => s + Math.abs(t.amount), 0);
  const expenses = allTxs.filter(t => t.type === 'expense').reduce((s, t) => s + Math.abs(t.amount), 0);
  document.getElementById('tx-total-income').textContent = fmt(income);
  document.getElementById('tx-total-expense').textContent = fmt(expenses);

  // Filter chips
  const cats = ['all', ...new Set(allTxs.map(t => t.category))];
  document.getElementById('filter-chips').innerHTML = cats.map(c =>
    `<button class="chip${txFilter === c ? ' active' : ''}" onclick="filterTx('${c}')">${c === 'all' ? 'All' : capitalize(c)}</button>`
  ).join('');

  // List
  let filtered = txFilter === 'all' ? allTxs : allTxs.filter(t => t.category === txFilter);

  let html = '';
  let lastDate = '';
  filtered.forEach(t => {
    const d = new Date(t.date);
    const dateStr = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    if (dateStr !== lastDate) {
      html += `<div class="tx-date-group">${dateStr}</div>`;
      lastDate = dateStr;
    }
    html += renderTxItem(t);
  });
  document.getElementById('tx-list').innerHTML = html || '<p style="text-align:center;color:var(--text-secondary);padding:40px 0">No transactions this month</p>';
}

function selectMonth(m, y) {
  selectedMonth = m;
  selectedYear = y;
  txFilter = 'all';
  renderTransactions();
}
function filterTx(cat) {
  txFilter = cat;
  renderTransactions();
}

// ===== GOALS =====
async function renderGoals() {
  const goals = await api('/api/goals');
  const grid = document.getElementById('goals-grid');
  let html = goals.map(g => {
    const pct = g.target > 0 ? Math.round((g.saved / g.target) * 100) : 0;
    const circumference = 2 * Math.PI * 22;
    const offset = circumference - (pct / 100) * circumference;
    return `<div class="card goal-card">
      <div class="goal-card-header">
        <div class="goal-card-left">
          <span class="goal-emoji">${g.emoji}</span>
          <div>
            <div class="goal-name">${g.name}</div>
            <div class="goal-target">Target: ${fmtShort(g.target)}</div>
          </div>
        </div>
        <div class="goal-progress-ring">
          <svg width="56" height="56"><circle cx="28" cy="28" r="22" fill="none" stroke="var(--border)" stroke-width="4"/><circle cx="28" cy="28" r="22" fill="none" stroke="var(--primary)" stroke-width="4" stroke-linecap="round" stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"/></svg>
          <div class="percentage">${pct}%</div>
        </div>
      </div>
      <div class="goal-amounts">
        <span class="goal-saved">${fmtShort(g.saved)}</span>
        <span class="goal-of">of ${fmtShort(g.target)}</span>
      </div>
      <div class="goal-progress-full"><div class="goal-progress-full-fill" style="width:${pct}%"></div></div>
    </div>`;
  }).join('');

  html += `<div class="card add-goal-card" onclick="openSheet('add-goal')">
    <span style="font-size:1.5rem">+</span> Add New Goal
  </div>`;
  grid.innerHTML = html;

  // Emoji picker
  const emojis = ['\ud83d\udef1','\u2708\ufe0f','\ud83c\udf93','\ud83c\udfe0','\ud83d\ude97','\ud83d\udcbb','\ud83c\udfb8','\ud83c\udfd6\ufe0f','\ud83d\udc8d','\ud83d\udcf1','\ud83c\udfae','\ud83d\udc76'];
  document.getElementById('goal-emoji-grid').innerHTML = emojis.map(e =>
    `<div class="category-chip" onclick="selectGoalEmoji(this, '${e}')">${e}</div>`
  ).join('');

  // Goal select list for "save to goal" sheet
  document.getElementById('goal-select-list').innerHTML = goals.length === 0
    ? '<p style="color:var(--text-secondary);font-size:0.8125rem">Create a goal first!</p>'
    : goals.map(g =>
      `<div class="chip" style="margin-bottom:8px" onclick="selectGoalForAdd(this, ${g.id})" data-goal="${g.id}">${g.emoji} ${g.name}</div>`
    ).join('');
}

let selectedGoalId = null;
let selectedGoalEmoji = '\ud83c\udfaf';

function selectGoalForAdd(el, id) {
  document.querySelectorAll('#goal-select-list .chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  selectedGoalId = id;
}
function selectGoalEmoji(el, emoji) {
  document.querySelectorAll('#goal-emoji-grid .category-chip').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  selectedGoalEmoji = emoji;
}

// ===== INSIGHTS =====
async function renderInsights() {
  const now = new Date();
  const month = getMonthStr(now.getFullYear(), now.getMonth());
  const summary = await api('/api/summary?month=' + month);

  const entries = summary.categories || [];
  const total = entries.reduce((s, e) => s + e.total, 0);
  const colors = {
    food: '#F59E0B', transport: '#3B82F6', shopping: '#EC4899', entertainment: '#8B5CF6',
    bills: '#6366F1', health: '#10B981', education: '#F97316', subscriptions: '#14B8A6', other: '#94A3B8'
  };

  // Donut chart
  if (total > 0) {
    let donutHTML = '<svg viewBox="0 0 200 200" width="200" height="200">';
    let startAngle = 0;
    const cx = 100, cy = 100, r = 70;
    entries.forEach(e => {
      const pct = e.total / total;
      const angle = pct * 360;
      const endAngle = startAngle + angle;
      const largeArc = angle > 180 ? 1 : 0;
      const x1 = cx + r * Math.cos((startAngle - 90) * Math.PI / 180);
      const y1 = cy + r * Math.sin((startAngle - 90) * Math.PI / 180);
      const x2 = cx + r * Math.cos((endAngle - 90) * Math.PI / 180);
      const y2 = cy + r * Math.sin((endAngle - 90) * Math.PI / 180);
      donutHTML += `<path d="M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${largeArc},1 ${x2},${y2} Z" fill="${colors[e.category] || '#94A3B8'}" opacity="0.85"/>`;
      startAngle = endAngle;
    });
    donutHTML += `<circle cx="${cx}" cy="${cy}" r="48" fill="var(--surface)"/>`;
    donutHTML += '</svg>';
    document.getElementById('donut-chart').innerHTML = donutHTML +
      `<div class="donut-center"><div class="total">${fmt(total)}</div><div class="label">Total Spent</div></div>`;
  } else {
    document.getElementById('donut-chart').innerHTML = '<div class="donut-center"><div class="total">' + fmt(0) + '</div><div class="label">No spending yet</div></div>';
  }

  // Legend
  document.getElementById('donut-legend').innerHTML = entries.map(e => {
    const pct = total > 0 ? Math.round((e.total / total) * 100) : 0;
    return `<div class="legend-item">
      <div class="legend-left"><div class="legend-dot" style="background:${colors[e.category] || '#94A3B8'}"></div><span class="legend-name">${capitalize(e.category)}</span></div>
      <div class="legend-right"><span class="legend-amount">${fmt(e.total)}</span><br><span class="legend-pct">${pct}%</span></div>
    </div>`;
  }).join('');

  // Trend chart
  const daily = summary.daily_spending || {};
  const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const maxSpend = Math.max(...Object.values(daily), 1);
  const chartW = 320, chartH = 120, padX = 10, padY = 10;
  const usableW = chartW - padX * 2, usableH = chartH - padY * 2;
  let points = [];
  for (let d = 1; d <= Math.min(now.getDate(), daysInMonth); d++) {
    const x = padX + ((d - 1) / Math.max(daysInMonth - 1, 1)) * usableW;
    const y = padY + usableH - ((daily[d] || 0) / maxSpend) * usableH;
    points.push(`${x},${y}`);
  }
  if (points.length > 0) {
    const polyline = points.join(' ');
    const areaPoints = `${padX},${padY + usableH} ${polyline} ${points[points.length-1].split(',')[0]},${padY + usableH}`;
    document.getElementById('trend-chart').innerHTML = `<svg viewBox="0 0 ${chartW} ${chartH}">
      <defs><linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--primary)" stop-opacity="0.2"/><stop offset="100%" stop-color="var(--primary)" stop-opacity="0"/></linearGradient></defs>
      <polygon points="${areaPoints}" fill="url(#trendGrad)"/>
      <polyline points="${polyline}" fill="none" stroke="var(--primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      ${points.map(p => `<circle cx="${p.split(',')[0]}" cy="${p.split(',')[1]}" r="3" fill="var(--primary)"/>`).join('')}
    </svg>`;
  } else {
    document.getElementById('trend-chart').innerHTML = '<p style="text-align:center;color:var(--text-secondary);padding:40px 0;font-size:0.8125rem">Add expenses to see your spending trend</p>';
  }

  // Smart insights
  const prev = summary.prev_categories || {};
  let insights = [];
  entries.forEach(e => {
    const prevVal = prev[e.category] || 0;
    if (prevVal > 0) {
      const change = Math.round(((e.total - prevVal) / prevVal) * 100);
      if (change > 15) {
        insights.push({ type: 'warning', text: `You spent ${change}% more on ${capitalize(e.category)} compared to last month.` });
      } else if (change < -10) {
        insights.push({ type: 'positive', text: `${capitalize(e.category)} spending is down ${Math.abs(change)}% from last month \u2014 nice work!` });
      }
    }
  });

  const userIncome = user.income || 0;
  if (userIncome > 0 && total > userIncome * 0.8) {
    insights.push({ type: 'warning', text: `You've spent over 80% of your income this month. Review non-essential expenses.` });
  }

  if (total === 0) {
    insights.push({ type: 'positive', text: 'Start adding transactions to get personalized spending insights!' });
  } else if (insights.length === 0) {
    insights.push({ type: 'positive', text: 'Your spending looks balanced this month. Keep it up!' });
  }

  document.getElementById('smart-insights').innerHTML = insights.map(i =>
    `<div class="card insight-card ${i.type}"><p class="insight-label">${i.type === 'positive' ? '\u2713 Positive' : '\u26a0 Heads up'}</p><p>${i.text}</p></div>`
  ).join('');
}

// ===== MONEY PULSE =====
let pulseStep = 0;
let pulseData = { mood: '', highlight: '', challenge: '', goal: '' };

async function renderMoneyPulse() {
  const pulse = await api('/api/pulse/current-week');
  if (pulse.completed) {
    renderPulseSummary();
    return;
  }
  pulseStep = 0;
  pulseData = { mood: '', highlight: '', challenge: '', goal: '' };
  renderPulseStep();
}

function renderPulseStep() {
  const flow = document.getElementById('pulse-flow');
  const steps = [
    { title: 'How do you feel about your money this week?', subtitle: 'No wrong answers \u2014 just check in with yourself.',
      content: `<div class="mood-options">
        <button class="mood-btn" onclick="selectMood(this,'stressed')"><span class="emoji">\ud83d\ude30</span><span class="mood-label">Stressed</span></button>
        <button class="mood-btn" onclick="selectMood(this,'worried')"><span class="emoji">\ud83d\ude1f</span><span class="mood-label">Worried</span></button>
        <button class="mood-btn" onclick="selectMood(this,'neutral')"><span class="emoji">\ud83d\ude10</span><span class="mood-label">Neutral</span></button>
        <button class="mood-btn" onclick="selectMood(this,'good')"><span class="emoji">\ud83d\ude0a</span><span class="mood-label">Good</span></button>
        <button class="mood-btn" onclick="selectMood(this,'confident')"><span class="emoji">\ud83d\ude0e</span><span class="mood-label">Great</span></button>
      </div>` },
    { title: 'What was your best money moment?', subtitle: 'Celebrate the small wins.',
      content: `<div class="pulse-chips">
        <button class="pulse-chip" onclick="selectPulseChip(this,'highlight')">Stayed on budget</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'highlight')">Saved extra</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'highlight')">Avoided impulse buy</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'highlight')">Cooked at home</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'highlight')">Found a deal</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'highlight')">Earned extra</button>
      </div>` },
    { title: 'Biggest money challenge?', subtitle: 'Awareness is the first step.',
      content: `<div class="pulse-chips">
        <button class="pulse-chip" onclick="selectPulseChip(this,'challenge')">Unexpected expense</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'challenge')">Overspent on food</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'challenge')">Peer pressure</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'challenge')">Forgot a bill</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'challenge')">Impulse purchase</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'challenge')">No challenges!</button>
      </div>` },
    { title: 'One money goal for next week?', subtitle: 'Keep it simple and achievable.',
      content: `<div class="pulse-chips">
        <button class="pulse-chip" onclick="selectPulseChip(this,'goal')">Pack lunch daily</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'goal')">No online shopping</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'goal')">Save extra this week</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'goal')">Track every expense</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'goal')">Cancel a subscription</button>
        <button class="pulse-chip" onclick="selectPulseChip(this,'goal')">Review my goals</button>
      </div>
      <button class="btn btn-primary btn-full" onclick="completePulse()" style="margin-top:8px">Complete Check-in</button>` }
  ];
  const step = steps[pulseStep];
  flow.innerHTML = `<div class="pulse-step active">
    <div class="onboarding-dots" style="margin-bottom:24px">${steps.map((_, i) => `<div class="onboarding-dot${i === pulseStep ? ' active' : ''}"></div>`).join('')}</div>
    <h3>${step.title}</h3><p>${step.subtitle}</p>${step.content}
  </div>`;
}

function selectMood(btn, mood) {
  document.querySelectorAll('.mood-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  pulseData.mood = mood;
  setTimeout(() => { pulseStep++; renderPulseStep(); }, 400);
}

function selectPulseChip(chip, field) {
  chip.parentElement.querySelectorAll('.pulse-chip').forEach(c => c.classList.remove('selected'));
  chip.classList.add('selected');
  pulseData[field] = chip.textContent;
  if (field !== 'goal') {
    setTimeout(() => { pulseStep++; renderPulseStep(); }, 400);
  }
}

async function completePulse() {
  if (!pulseData.goal) return;
  const week = getISOWeek();
  await api('/api/pulse', { method: 'POST', body: { ...pulseData, week } });
  renderPulseSummary();
  renderDashboard();
}

async function renderPulseSummary() {
  const moodScores = { stressed: 20, worried: 40, neutral: 60, good: 80, confident: 95 };
  const allPulse = await api('/api/pulse');
  const latest = allPulse[0];
  const score = latest ? (moodScores[latest.mood] || 60) : 60;
  const recent = allPulse.slice(0, 4);

  document.getElementById('pulse-flow').innerHTML = `
    <div class="pulse-step active">
      <div class="card pulse-summary-card">
        <div class="pulse-score">
          <div class="score-num">${score}</div>
          <div class="score-label">Wellness Score</div>
        </div>
        <h3 style="font-size:1.125rem;font-weight:700;margin-bottom:4px">This Week's Pulse</h3>
        <p style="color:var(--text-secondary);font-size:0.875rem;margin-bottom:16px">${getPulseMessage(score)}</p>
        ${latest ? `<div style="text-align:left;margin-top:16px">
          <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:4px">Your highlight</div>
          <div class="chip active" style="margin-bottom:12px;pointer-events:none">${latest.highlight}</div>
          <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:4px">Next week's goal</div>
          <div class="chip active" style="pointer-events:none">${latest.goal}</div>
        </div>` : ''}
        <div class="pulse-history">
          ${recent.map((r, i) => {
            const s = moodScores[r.mood] || 60;
            return `<div class="pulse-week">
              <div class="pulse-week-bar" style="height:60px"><div class="pulse-week-fill" style="height:${s}%"></div></div>
              <div class="pulse-week-label">W${i + 1}</div>
            </div>`;
          }).join('')}
        </div>
      </div>
    </div>`;
}

function getPulseMessage(score) {
  if (score >= 80) return "You're feeling great about your finances! Keep the momentum going.";
  if (score >= 60) return "You're in a steady place. Small improvements add up over time.";
  if (score >= 40) return "Some financial stress is normal. Focus on one small win this week.";
  return "It's okay to feel overwhelmed. Start with what you can control.";
}

// ===== INSIGHT TABS =====
function switchInsightTab(tab) {
  document.querySelectorAll('.insight-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.insight-panel').forEach(p => p.classList.remove('active'));
  if (tab === 'overview') {
    document.querySelectorAll('.insight-tab')[0].classList.add('active');
    document.getElementById('panel-overview').classList.add('active');
  } else {
    document.querySelectorAll('.insight-tab')[1].classList.add('active');
    document.getElementById('panel-pulse').classList.add('active');
    renderMoneyPulse();
  }
}

// ===== PROFILE =====
function renderProfile() {
  const initial = (user.name || 'U')[0].toUpperCase();
  document.getElementById('profile-avatar').textContent = initial;
  document.getElementById('profile-name').textContent = user.name || 'User';
  document.getElementById('dark-toggle').classList.toggle('active', user.theme === 'dark');
  const c = getCurrency();
  document.getElementById('currency-display').textContent = c.code + ' ' + c.symbol;
}

async function toggleDarkMode() {
  const newTheme = (user.theme === 'dark') ? 'light' : 'dark';
  user.theme = newTheme;
  document.documentElement.dataset.theme = newTheme;
  document.getElementById('dark-toggle').classList.toggle('active', newTheme === 'dark');
  await api('/api/user', { method: 'PUT', body: { theme: newTheme } });
}

// ===== ACTIONS =====
const CAT_EMOJIS = { food: '\ud83c\udf55', transport: '\ud83d\ude97', shopping: '\ud83d\udecd\ufe0f', entertainment: '\ud83c\udfac', bills: '\ud83d\udcf1', health: '\ud83d\udc8a', education: '\ud83d\udcda', subscriptions: '\ud83d\udcfa', other: '\ud83d\udce6' };

async function addExpense() {
  const amount = parseFloat(document.getElementById('expense-amount').value.replace(/[^0-9.]/g, ''));
  const desc = document.getElementById('expense-desc').value.trim();
  const catEl = document.querySelector('#expense-categories .selected');
  if (!amount || amount <= 0) { document.getElementById('expense-amount').focus(); return; }
  const cat = catEl ? catEl.dataset.cat : 'other';

  await api('/api/transactions', {
    method: 'POST',
    body: {
      name: desc || 'Expense',
      category: cat,
      emoji: CAT_EMOJIS[cat] || '\ud83d\udce6',
      amount: amount,
      type: 'expense',
      date: new Date().toISOString().split('T')[0]
    }
  });

  closeSheet();
  document.getElementById('expense-amount').value = '';
  document.getElementById('expense-desc').value = '';
  document.querySelectorAll('#expense-categories .selected').forEach(c => c.classList.remove('selected'));
  await renderAll();
}

async function addIncome() {
  const amount = parseFloat(document.getElementById('income-amount').value.replace(/[^0-9.]/g, ''));
  const desc = document.getElementById('income-desc').value.trim();
  if (!amount || amount <= 0) { document.getElementById('income-amount').focus(); return; }

  await api('/api/transactions', {
    method: 'POST',
    body: {
      name: desc || 'Income',
      category: 'income',
      emoji: '\ud83d\udcb0',
      amount: amount,
      type: 'income',
      date: new Date().toISOString().split('T')[0]
    }
  });

  closeSheet();
  document.getElementById('income-amount').value = '';
  document.getElementById('income-desc').value = '';
  await renderAll();
}

async function addToGoal() {
  const amount = parseFloat(document.getElementById('goal-add-amount').value.replace(/[^0-9.]/g, ''));
  if (!amount || !selectedGoalId) return;

  await api(`/api/goals/${selectedGoalId}`, {
    method: 'PUT',
    body: { add_amount: amount }
  });

  closeSheet();
  document.getElementById('goal-add-amount').value = '';
  await renderAll();
}

async function setBudget() {
  const amount = parseFloat(document.getElementById('budget-amount').value.replace(/[^0-9.]/g, ''));
  if (amount) {
    await api('/api/user', { method: 'PUT', body: { budget: amount } });
    user.budget = amount;
    closeSheet();
  }
}

async function addNewGoal() {
  const name = document.getElementById('new-goal-name').value.trim();
  const target = parseFloat(document.getElementById('new-goal-target').value.replace(/[^0-9.]/g, ''));
  if (!name || !target) return;

  await api('/api/goals', {
    method: 'POST',
    body: { name, emoji: selectedGoalEmoji, saved: 0, target }
  });

  closeSheet();
  document.getElementById('new-goal-name').value = '';
  document.getElementById('new-goal-target').value = '';
  await renderAll();
}

async function resetApp() {
  if (confirm('Reset all data and start fresh? This will delete all your transactions, goals, and settings.')) {
    await api('/api/reset', { method: 'POST' });
    location.reload();
  }
}

// ===== QUICK ADD EXPENSE (Dashboard) =====
async function quickAddExpense() {
  const cat = document.getElementById('quick-cat').value;
  const amount = parseFloat(document.getElementById('quick-amount').value.replace(/[^0-9.]/g, ''));
  const desc = document.getElementById('quick-desc').value.trim();
  if (!amount || amount <= 0) { document.getElementById('quick-amount').focus(); return; }

  await api('/api/transactions', {
    method: 'POST',
    body: {
      name: desc || capitalize(cat),
      category: cat,
      emoji: CAT_EMOJIS[cat] || '\ud83d\udce6',
      amount: amount,
      type: 'expense',
      date: new Date().toISOString().split('T')[0]
    }
  });

  document.getElementById('quick-amount').value = '';
  document.getElementById('quick-desc').value = '';
  await renderAll();
}

// ===== EXPENSE CATEGORIES IN SHEET =====
function renderExpenseCategories() {
  const cats = ['food','transport','shopping','entertainment','bills','health','education','subscriptions'];
  const catLabels = { food:'\ud83c\udf55 Food', transport:'\ud83d\ude97 Transport', shopping:'\ud83d\udecd\ufe0f Shopping', entertainment:'\ud83c\udfac Fun', bills:'\ud83d\udcf1 Bills', health:'\ud83d\udc8a Health', education:'\ud83d\udcda Education', subscriptions:'\ud83d\udcfa Subs' };
  document.getElementById('expense-categories').innerHTML = cats.map(c =>
    `<div class="category-chip" data-cat="${c}" onclick="toggleExpenseCat(this)">${catLabels[c]}</div>`
  ).join('');
}

function toggleExpenseCat(el) {
  document.querySelectorAll('#expense-categories .category-chip').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
}

// ===== EMI / DUE PAYMENTS =====
let dueRecurring = true;

function selectDueType(el) {
  document.querySelectorAll('#due-type-grid .category-chip').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
}

function toggleDueRecurring() {
  dueRecurring = !dueRecurring;
  document.getElementById('due-recurring-toggle').classList.toggle('active', dueRecurring);
}

async function addDue() {
  const name = document.getElementById('due-name').value.trim();
  const amount = parseFloat(document.getElementById('due-amount').value.replace(/[^0-9.]/g, ''));
  const dueDate = document.getElementById('due-date').value;
  const typeEl = document.querySelector('#due-type-grid .selected');
  const type = typeEl ? typeEl.dataset.type : 'emi';

  if (!name) { document.getElementById('due-name').focus(); return; }
  if (!amount || amount <= 0) { document.getElementById('due-amount').focus(); return; }
  if (!dueDate) { document.getElementById('due-date').focus(); return; }

  await api('/api/dues', {
    method: 'POST',
    body: { name, amount, due_date: dueDate, type, is_recurring: dueRecurring, recur_months: 1 }
  });

  closeSheet();
  document.getElementById('due-name').value = '';
  document.getElementById('due-amount').value = '';
  document.getElementById('due-date').value = '';
  dueRecurring = true;
  document.getElementById('due-recurring-toggle').classList.add('active');
  await renderAll();
}

async function markDuePaid(dueId) {
  await api(`/api/dues/${dueId}/pay`, { method: 'POST' });
  await renderAll();
}

async function deleteDue(dueId) {
  if (confirm('Delete this payment?')) {
    await api(`/api/dues/${dueId}`, { method: 'DELETE' });
    await renderAll();
  }
}

let emiFilterMode = 'pending';
let allDuesCache = [];

function filterEmis(mode) {
  emiFilterMode = mode;
  document.querySelectorAll('.emi-filter-tabs .month-pill').forEach(b => b.classList.remove('active'));
  document.getElementById('emi-filter-' + mode).classList.add('active');
  renderEmiList(allDuesCache);
}

function renderEmiCard(d) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(d.due_date);
  const diffDays = Math.ceil((due - today) / 86400000);
  let statusClass = 'emi-upcoming';
  let statusLabel = `Due in ${diffDays} day${diffDays !== 1 ? 's' : ''}`;
  if (d.is_paid) { statusClass = 'emi-paid'; statusLabel = 'Paid'; }
  else if (diffDays < 0) { statusClass = 'emi-overdue'; statusLabel = `Overdue by ${Math.abs(diffDays)} day${Math.abs(diffDays) !== 1 ? 's' : ''}`; }
  else if (diffDays === 0) { statusClass = 'emi-today'; statusLabel = 'Due today'; }
  else if (diffDays <= 5) { statusClass = 'emi-warning'; }

  const typeEmoji = d.type === 'emi' ? '\u{1F3E6}' : d.type === 'subscription' ? '\u{1F504}' : '\u{1F4CC}';
  const actions = d.is_paid
    ? `<div class="emi-card-actions"><span style="color:var(--savings);font-weight:600;font-size:0.8125rem">Paid${d.paid_date ? ' on ' + new Date(d.paid_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}</span></div>`
    : `<div class="emi-card-actions">
        <button class="btn btn-sm btn-primary" onclick="markDuePaid(${d.id})">Mark Paid</button>
        <button class="btn btn-sm btn-ghost" onclick="deleteDue(${d.id})" style="color:var(--spending-high)">Remove</button>
      </div>`;

  return `<div class="card emi-card ${statusClass}" style="margin-bottom:12px">
    <div class="emi-card-row">
      <div class="emi-card-left">
        <span class="emi-emoji">${typeEmoji}</span>
        <div>
          <div class="emi-name">${d.name}</div>
          <div class="emi-meta">${capitalize(d.type)}${d.is_recurring ? ' \u00b7 Recurring' : ''}</div>
        </div>
      </div>
      <div class="emi-card-right">
        <div class="emi-amount">${fmt(d.amount)}</div>
        <div class="emi-due-label ${statusClass}">${statusLabel}</div>
      </div>
    </div>
    <div class="emi-card-date">Due: ${due.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' })}</div>
    ${actions}
  </div>`;
}

function renderEmiList(allDues) {
  let emis;
  if (emiFilterMode === 'pending') emis = allDues.filter(d => !d.is_paid);
  else if (emiFilterMode === 'paid') emis = allDues.filter(d => d.is_paid);
  else emis = allDues;

  const list = document.getElementById('emi-screen-list');
  const empty = document.getElementById('emi-empty');

  if (emis.length === 0) {
    list.innerHTML = '';
    empty.style.display = 'block';
    return;
  }

  empty.style.display = 'none';
  list.innerHTML = emis.map(d => renderEmiCard(d)).join('');
}

async function renderEmiSection() {
  allDuesCache = await api('/api/dues');
  renderEmiList(allDuesCache);

  // Also update dashboard EMI section — only show EMIs due within 5 days or overdue
  const header = document.getElementById('emi-section-header');
  const dashList = document.getElementById('emi-list');
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const urgentEmis = allDuesCache.filter(d => {
    if (d.is_paid) return false;
    const dueDate = new Date(d.due_date);
    const diffDays = Math.ceil((dueDate - today) / 86400000);
    return diffDays <= 5;
  });

  if (urgentEmis.length === 0) {
    header.style.display = 'none';
    dashList.innerHTML = '';
    return;
  }

  header.style.display = 'flex';
  dashList.innerHTML = urgentEmis.map(d => renderEmiCard(d)).join('');
}


// ===== SERVICE WORKER & PWA =====
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then(reg => console.log('Penny Buddy SW registered:', reg.scope))
      .catch(err => console.log('SW registration failed:', err));
  });
}

// Install prompt handling
let deferredInstallPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  showInstallBanner();
});

function showInstallBanner() {
  // Create install banner if it doesn't exist
  if (document.getElementById('install-banner')) return;
  const banner = document.createElement('div');
  banner.id = 'install-banner';
  banner.innerHTML = `
    <div style="position:fixed;bottom:80px;left:16px;right:16px;background:var(--primary);color:#fff;padding:16px 20px;border-radius:16px;display:flex;align-items:center;gap:12px;z-index:9999;box-shadow:0 8px 32px rgba(79,70,229,0.35)">
      <div style="flex:1">
        <div style="font-weight:700;font-size:0.9375rem">Install Penny Buddy</div>
        <div style="font-size:0.8125rem;opacity:0.85">Add to home screen for the full app experience</div>
      </div>
      <button onclick="installApp()" style="background:#fff;color:var(--primary);border:none;padding:10px 20px;border-radius:12px;font-weight:700;font-size:0.8125rem;cursor:pointer;white-space:nowrap">Install</button>
      <button onclick="dismissInstallBanner()" style="background:none;border:none;color:#fff;font-size:1.25rem;cursor:pointer;padding:4px">&times;</button>
    </div>`;
  document.body.appendChild(banner);
}

function dismissInstallBanner() {
  const b = document.getElementById('install-banner');
  if (b) b.remove();
}

async function installApp() {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  const result = await deferredInstallPrompt.userChoice;
  console.log('Install prompt result:', result.outcome);
  deferredInstallPrompt = null;
  dismissInstallBanner();
}

window.addEventListener('appinstalled', () => {
  console.log('Penny Buddy installed!');
  dismissInstallBanner();
});

// Handle deep link actions from PWA shortcuts
function handleDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const action = params.get('action');
  if (action === 'add-expense') {
    setTimeout(() => openSheet('add-expense'), 500);
  } else if (action === 'insights') {
    setTimeout(() => navigateTo('insights'), 500);
  }
}

// ===== START =====
initNativeBridge();
init();
handleDeepLink();
