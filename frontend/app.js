/* ═══════════════════════════════════════════════
   B2B Intelligence — Mission Control JS
   API client + UI logic
   ═══════════════════════════════════════════════ */

// ─── Dual Mode: Live API or Static JSON (Netlify) ───
const API_URLS = [
    window.location.origin + '/api/v1',
    'http://localhost:8001/api/v1',
    'http://localhost:8005/api/v1',
];
let API = API_URLS[0];
let STATIC_MODE = false;
let STATIC_DATA = null;
let currentPage = 0;
const PAGE_SIZE = 25;

// Load static data for Netlify fallback
async function loadStaticData() {
    try {
        const res = await fetch('./data/companies.json');
        if (res.ok) {
            STATIC_DATA = await res.json();
            STATIC_MODE = true;
            console.log(`Static mode: ${STATIC_DATA.length} companies loaded`);
            const badge = document.querySelector('.status-badge');
            if (badge) {
                badge.textContent = '● Статические данные';
                badge.className = 'status-badge online';
            }
        }
    } catch (e) { console.log('No static data available'); }
}

// ─── Navigation ───
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        showView(item.dataset.view);
    });
});

function showView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById(`view-${viewName}`).classList.add('active');
    document.querySelector(`[data-view="${viewName}"]`).classList.add('active');

    if (viewName === 'dashboard') loadDashboard();
    if (viewName === 'companies') loadCompanies();
    if (viewName === 'documents') loadDocuments();
    if (viewName === 'crm') loadCrm();
    if (viewName === 'recon') loadReconData();
    if (viewName === 'profile') loadProfile();
}

// ─── API Helpers ───
async function api(path, options = {}) {
    // Try live API first
    for (const base of API_URLS) {
        try {
            const res = await fetch(`${base}${path}`, {...options, signal: AbortSignal.timeout(3000)});
            if (!res.ok) continue;
            API = base;
            const badge = document.querySelector('.status-badge');
            if (badge) {
                badge.textContent = '● API Online';
                badge.className = 'status-badge online';
            }
            return await res.json();
        } catch (err) { continue; }
    }
    
    // Fallback to static data
    if (STATIC_DATA) {
        STATIC_MODE = true;
        return staticApi(path);
    }
    
    console.error('API Error: all endpoints failed');
    const badge = document.querySelector('.status-badge');
    if (badge) {
        badge.textContent = '● API Offline';
        badge.className = 'status-badge offline';
    }
    return null;
}

// ─── Static Data API Simulator ───
function staticApi(path) {
    if (!STATIC_DATA) return null;
    
    // /stats
    if (path === '/stats') {
        const enriched = STATIC_DATA.filter(c => c.enrichment_status === 'enriched').length;
        const hot = STATIC_DATA.filter(c => c.lead_score >= 70).length;
        const withSite = STATIC_DATA.filter(c => c.website).length;
        return { total_companies: STATIC_DATA.length, enriched, hot_leads: hot, with_website: withSite };
    }
    
    // /companies
    if (path.startsWith('/companies')) {
        const params = new URLSearchParams(path.split('?')[1] || '');
        const skip = parseInt(params.get('skip') || '0');
        const limit = parseInt(params.get('limit') || '25');
        const search = (params.get('search') || '').toLowerCase();
        const minScore = parseInt(params.get('min_score') || '0');
        const status = params.get('status') || '';
        
        let filtered = STATIC_DATA;
        if (search) filtered = filtered.filter(c => c.name.toLowerCase().includes(search) || (c.key || '').toLowerCase().includes(search));
        if (minScore) filtered = filtered.filter(c => c.lead_score >= minScore);
        if (status) filtered = filtered.filter(c => c.enrichment_status === status);
        
        // Check if it's a single company request /companies/{id}
        const idMatch = path.match(/^\/companies\/(\d+)/);
        if (idMatch) {
            const id = parseInt(idMatch[1]);
            const c = STATIC_DATA.find(x => x.id === id);
            if (!c) return null;
            return { company: c, contacts: c.contacts || [], persons: c.persons || [], intelligence: null };
        }
        
        return { items: filtered.slice(skip, skip + limit), total: filtered.length };
    }
    
    // /recon/status
    if (path.includes('/recon/status')) {
        const withSite = STATIC_DATA.filter(c => c.website).length;
        const crawled = STATIC_DATA.filter(c => c.enrichment_status === 'enriched' && c.website).length;
        const totalContacts = STATIC_DATA.reduce((s, c) => s + (c.contacts?.length || 0), 0);
        return { companies_with_website: withSite, companies_crawled: crawled, total_contacts_found: totalContacts, remaining: withSite - crawled };
    }
    
    // /recon/contacts
    if (path.includes('/recon/contacts')) {
        const contacts = [];
        for (const c of STATIC_DATA) {
            for (const ct of (c.contacts || [])) {
                contacts.push({ ...ct, company_name: c.name, company_id: c.id });
            }
        }
        return { contacts: contacts.slice(0, 300), total: contacts.length };
    }
    
    // /crm/analytics
    if (path.includes('/crm')) {
        return { error: 'CRM данные доступны только в live-режиме' };
    }
    
    return null;
}

function fmt(n) {
    if (n === null || n === undefined) return '—';
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
    return n.toLocaleString('ru-RU');
}

function fmtRub(n) {
    if (n === null || n === undefined) return '—';
    return n.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 });
}

function statusBadge(st) {
    const map = {
        'new': ['badge-new', 'Новый'],
        'in_progress': ['badge-progress', 'В работе'],
        'enriched': ['badge-enriched', 'Обогащён'],
        'failed': ['badge-new', 'Ошибка'],
    };
    const [cls, label] = map[st] || ['badge-new', st];
    return `<span class="badge ${cls}">${label}</span>`;
}

function mpBadges(wb, ozon) {
    let html = '<div class="mp-badges">';
    if (wb) html += '<span class="badge badge-wb">WB</span>';
    if (ozon) html += '<span class="badge badge-ozon">Ozon</span>';
    if (!wb && !ozon) html += '<span class="text-muted">—</span>';
    html += '</div>';
    return html;
}

// ─── Dashboard ───
async function loadDashboard() {
    const stats = await api('/stats');
    if (!stats) return;

    document.getElementById('statTotal').textContent = stats.total_companies;
    document.getElementById('statEnriched').textContent = stats.enriched;
    document.getElementById('statHot').textContent = stats.hot_leads;
    document.getElementById('statWebsite').textContent = stats.with_website;

    // Load top companies
    const data = await api('/companies?limit=10');
    if (!data) return;

    const tbody = document.getElementById('topCompaniesBody');
    tbody.innerHTML = data.items.map(c => `
        <tr>
            <td><span class="fw-700">${c.name}</span></td>
            <td class="text-muted">${c.legal_form || '—'}</td>
            <td class="fw-700">${fmtRub(c.revenue_total)}</td>
            <td>${fmt(c.sales_total)}</td>
            <td>${c.wb_present ? '<span class="badge badge-wb">WB</span>' : '—'}</td>
            <td>${c.ozon_present ? '<span class="badge badge-ozon">Ozon</span>' : '—'}</td>
            <td>${statusBadge(c.enrichment_status)}</td>
            <td><button class="btn btn-sm" onclick="openDossier(${c.id})">Досье</button></td>
        </tr>
    `).join('');
}

// ─── Companies List ───
async function loadCompanies(page = 0, search = '', status = '') {
    currentPage = page;
    const skip = page * PAGE_SIZE;
    let url = `/companies?skip=${skip}&limit=${PAGE_SIZE}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (status) url += `&status=${status}`;

    const data = await api(url);
    if (!data) return;

    const tbody = document.getElementById('companiesBody');
    tbody.innerHTML = data.items.map((c, i) => `
        <tr>
            <td class="text-muted">${skip + i + 1}</td>
            <td><span class="fw-700">${c.name}</span></td>
            <td class="text-muted">${c.legal_form || '—'}</td>
            <td class="fw-700">${fmtRub(c.revenue_total)}</td>
            <td>${fmt(c.sales_total)}</td>
            <td>${c.revenue_total && c.sales_total ? fmtRub(c.revenue_total / c.sales_total) : '—'}</td>
            <td>${c.wb_present ? '<span class="badge badge-wb">WB</span>' : '—'}</td>
            <td>${c.ozon_present ? '<span class="badge badge-ozon">Ozon</span>' : '—'}</td>
            <td><span class="fw-700 ${c.lead_score >= 80 ? 'text-green' : c.lead_score >= 40 ? 'text-amber' : 'text-muted'}">${c.lead_score}</span></td>
            <td>${statusBadge(c.enrichment_status)}</td>
            <td><button class="btn btn-sm" onclick="openDossier(${c.id})">📋</button></td>
        </tr>
    `).join('');

    // Pagination
    const totalPages = Math.ceil(data.total / PAGE_SIZE);
    const pag = document.getElementById('pagination');
    let html = '';
    html += `<button ${page === 0 ? 'disabled' : ''} onclick="loadCompanies(${page - 1})">← Назад</button>`;
    for (let p = 0; p < Math.min(totalPages, 10); p++) {
        html += `<button class="${p === page ? 'active' : ''}" onclick="loadCompanies(${p})">${p + 1}</button>`;
    }
    html += `<button ${page >= totalPages - 1 ? 'disabled' : ''} onclick="loadCompanies(${page + 1})">Далее →</button>`;
    html += `<span class="text-muted" style="margin-left:12px;font-size:13px">Всего: ${data.total}</span>`;
    pag.innerHTML = html;
}

// ─── Dossier (Modal) ───
async function openDossier(id) {
    const data = await api(`/companies/${id}`);
    if (!data) return;

    const c = data.company;
    document.getElementById('dossierTitle').textContent = `Досье: ${c.name}`;

    let html = '';

    // Company Info
    html += `<div class="dossier-section"><h3>🏢 Основная информация</h3><div class="dossier-grid">`;
    html += field('Название', c.name);
    html += field('Правовая форма', c.legal_form);
    html += field('ИНН', c.inn);
    html += field('Выручка', fmtRub(c.revenue_total));
    html += field('Продажи (шт)', fmt(c.sales_total));
    html += field('Ср. цена', fmtRub(c.avg_price));
    html += field('Wildberries', c.wb_present ? '✅ Присутствует' : '❌');
    html += field('Ozon', c.ozon_present ? '✅ Присутствует' : '❌');
    html += field('Сайт', c.website || 'Не найден');
    html += field('Lead Score', c.lead_score + ' / 100');
    html += field('Статус обогащения', c.enrichment_status);
    html += `</div></div>`;

    // Persons
    if (data.persons && data.persons.length > 0) {
        html += `<div class="dossier-section"><h3>👤 Контактные лица</h3><div class="dossier-grid">`;
        data.persons.forEach(p => {
            html += field(p.role, `${p.name} (${p.source})`);
        });
        html += `</div></div>`;
    }

    // Contacts
    if (data.contacts && data.contacts.length > 0) {
        html += `<div class="dossier-section"><h3>📞 Контакты</h3><div class="dossier-grid">`;
        data.contacts.forEach(ct => {
            const label = ct.label || ct.type;
            const verified = ct.verified ? ' ✅' : '';
            html += field(label + verified, ct.value);
        });
        html += `</div></div>`;
    }

    // Links
    if (c.wb_brand_link || c.ozon_brand_link) {
        html += `<div class="dossier-section"><h3>🔗 Маркетплейсы</h3><div class="dossier-grid">`;
        if (c.wb_brand_link) html += field('Wildberries', `<a href="${c.wb_brand_link}" target="_blank" style="color:var(--accent)">${c.wb_brand_link}</a>`);
        if (c.ozon_brand_link) html += field('Ozon', `<a href="${c.ozon_brand_link}" target="_blank" style="color:var(--accent)">${c.ozon_brand_link}</a>`);
        html += `</div></div>`;
    }

    // Intelligence
    if (data.intelligence) {
        const intel = data.intelligence;
        html += `<div class="dossier-section"><h3>🧠 AI Анализ</h3>`;
        if (intel.pain_points) html += `<div class="dossier-field"><div class="label">Боли клиента</div><div class="value">${JSON.stringify(intel.pain_points)}</div></div>`;
        if (intel.brand_dna) html += `<div class="dossier-field" style="margin-top:8px"><div class="label">Brand DNA</div><div class="value">${JSON.stringify(intel.brand_dna)}</div></div>`;
        if (intel.approach_strategy) html += `<div class="dossier-field" style="margin-top:8px"><div class="label">Стратегия подхода</div><div class="value">${intel.approach_strategy}</div></div>`;
        html += `</div>`;
    }

    document.getElementById('dossierBody').innerHTML = html;
    document.getElementById('dossierModal').classList.add('open');
}

function field(label, value) {
    return `<div class="dossier-field"><div class="label">${label}</div><div class="value">${value || '—'}</div></div>`;
}

function closeDossier() {
    document.getElementById('dossierModal').classList.remove('open');
}

// Close modal on overlay click
document.getElementById('dossierModal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeDossier();
});

// ─── Documents ───
async function loadDocuments() {
    const docs = await api('/documents');
    const container = document.getElementById('documentsList');
    if (!docs || docs.length === 0) {
        container.innerHTML = `<p class="empty-state">Документы ещё не загружены. Перетащите файлы выше ☝️</p>`;
        return;
    }
    container.innerHTML = docs.map(d => {
        const icon = { 'pdf': '📕', 'docx': '📘', 'txt': '📝', 'doc': '📘' }[d.filename.split('.').pop()] || '📄';
        return `<div class="doc-item">
            <div class="doc-info">
                <span class="doc-icon">${icon}</span>
                <div>
                    <div class="doc-name">${d.filename}</div>
                    <div class="doc-meta">${d.doc_type} · ${fmt(d.text_length)} символов · ${new Date(d.uploaded_at).toLocaleDateString('ru-RU')}</div>
                </div>
            </div>
        </div>`;
    }).join('');
}

// Upload handler
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');

uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', () => handleFiles(fileInput.files));

async function handleFiles(files) {
    const docType = document.getElementById('docType').value;
    for (const file of files) {
        const fd = new FormData();
        fd.append('file', file);
        const res = await fetch(`${API}/documents/upload?doc_type=${docType}`, { method: 'POST', body: fd });
        const data = await res.json();
        console.log('Uploaded:', data);
    }
    loadDocuments();
}

// ─── Profile ───
async function loadProfile() {
    const data = await api('/profile');
    if (!data) return;
    document.getElementById('profileJson').textContent = JSON.stringify(data, null, 2);
}

// ─── Search ───
let searchTimeout;
document.getElementById('globalSearch').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        showView('companies');
        loadCompanies(0, e.target.value);
    }, 300);
});

document.getElementById('searchCompany')?.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        loadCompanies(0, e.target.value, document.getElementById('filterStatus').value);
    }, 300);
});

document.getElementById('filterStatus')?.addEventListener('change', () => {
    const search = document.getElementById('searchCompany').value;
    const status = document.getElementById('filterStatus').value;
    loadCompanies(0, search, status);
});

document.getElementById('refreshBtn').addEventListener('click', () => {
    loadDashboard();
});

// ─── CRM Analytics ───
async function loadCrm() {
    const stats = await api('/crm/analytics');

    // Default values if no stats yet
    const data = stats && !stats.error ? stats : {
        total_leads: 0,
        active_deals: 0,
        lost_leads: 0,
        total_calls: 0,
        funnel: {
            NEW: 0,
            PREPARATION: 0,
            PREPAYMENT_INVOICE: 0,
            EXECUTING: 0,
            FINAL_INVOICE: 0,
            WON: 0,
            LOSE: 0
        },
        calls: {
            total_duration: 0,
            avg_duration: 0
        }
    };

    // Update Stats
    document.getElementById('crmLeadsTotal').textContent = fmt(data.total_leads);
    document.getElementById('crmDealsTotal').textContent = fmt(data.active_deals);
    document.getElementById('crmLostLeads').textContent = fmt(data.lost_leads);
    document.getElementById('crmCallsTotal').textContent = fmt(data.total_calls);

    // Call Stats
    document.getElementById('callTotal').textContent = fmt(data.total_calls);
    document.getElementById('callAvgDuration').textContent = Math.round(data.calls?.avg_duration || 0) + ' сек';
    document.getElementById('callTotalHours').textContent = ((data.calls?.total_duration || 0) / 3600).toFixed(1) + ' ч';

    // Funnel Chart
    renderFunnel(data.funnel || {});

    // Lost Leads Table
    loadLostLeads();
}

function renderFunnel(funnel) {
    const container = document.getElementById('funnelContainer');
    if (!container) return;

    // Normalize max value for simple bar scaling
    const max = Math.max(...Object.values(funnel)) || 1;

    const stages = [
        { key: 'NEW', label: 'Новый лид', color: '#3b82f6' },
        { key: 'PREPARATION', label: 'Подготовка кп', color: '#6366f1' },
        { key: 'PREPAYMENT_INVOICE', label: 'Счёт (предоплата)', color: '#8b5cf6' },
        { key: 'EXECUTING', label: 'В работе', color: '#ec4899' },
        { key: 'FINAL_INVOICE', label: 'Финальный счёт', color: '#f43f5e' },
        { key: 'WON', label: 'Сделка успешна', color: '#10b981' },
        { key: 'LOSE', label: 'Сделка провалена', color: '#64748b' }
    ];

    container.innerHTML = stages.map(s => {
        const val = funnel[s.key] || 0;
        const width = Math.max((val / max) * 100, 1); // Min 1% width
        return `
            <div class="funnel-stage" style="margin-bottom:8px">
                <div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:13px">
                    <span>${s.label}</span>
                    <span class="fw-700">${val}</span>
                </div>
                <div style="background:#e2e8f0;border-radius:4px;height:8px;overflow:hidden">
                    <div style="width:${width}%;background:${s.color};height:100%"></div>
                </div>
            </div>
        `;
    }).join('');
}

async function loadLostLeads() {
    const data = await api('/crm/leads/lost?days=30&limit=10');
    if (!data || !data.items) return;

    document.getElementById('lostLeadsCount').textContent = data.items.length;

    const tbody = document.getElementById('lostLeadsBody');
    if (!tbody) return;

    if (data.items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">Потерянных лидов нет! 🎉</td></tr>';
        return;
    }

    tbody.innerHTML = data.items.map(l => `
        <tr>
            <td class="text-muted"><small>${l.id}</small></td>
            <td class="fw-600">${l.title || 'Без названия'}</td>
            <td>${l.company_title || '—'}</td>
            <td>${l.phone || '—'}</td>
            <td><span class="badge badge-new">${l.status_id}</span></td>
            <td>${Math.floor((Date.now() - new Date(l.date_modify)) / (1000 * 60 * 60 * 24))} дн.</td>
            <td><button class="btn btn-sm btn-primary">Вернуть</button></td>
        </tr>
    `).join('');
}

document.getElementById('btnSyncCrm')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnSyncCrm');
    btn.disabled = true;
    btn.textContent = '⏳ Запуск...';
    await api('/crm/sync', { method: 'POST' });
    alert('Синхронизация запущена в фоне! Обновите страницу через пару минут.');
    btn.textContent = '🔄 Синхронизация Bitrix24';
    btn.disabled = false;
});

// ─── Recon — Полноценный UI разведки ───
const TYPE_ICONS = {
    email: '📧', phone: '📞', vk: '🔵', telegram: '✈️',
    instagram: '📷', youtube: '🔴', whatsapp: '💬',
    ok: '🟠', facebook: '🔵', twitter: '🐦', tiktok: '🎵'
};

const TYPE_LABELS = {
    email: 'Email', phone: 'Телефон', vk: 'VKontakte', telegram: 'Telegram',
    instagram: 'Instagram', youtube: 'YouTube', whatsapp: 'WhatsApp',
    ok: 'Одноклассники', facebook: 'Facebook', twitter: 'Twitter/X', tiktok: 'TikTok'
};

async function loadReconData() {
    // Load stats
    const status = await api('/recon/status');
    if (status && !status.error) {
        document.getElementById('reconTotalSites').textContent = status.companies_with_website || 0;
        document.getElementById('reconCrawled').textContent = status.companies_crawled || 0;
        document.getElementById('reconContacts').textContent = status.total_contacts_found || 0;
        document.getElementById('reconRemaining').textContent = status.remaining || 0;

        // Progress bar
        const total = status.companies_with_website || 1;
        const done = status.companies_crawled || 0;
        const pct = Math.round((done / total) * 100);
        document.getElementById('reconProgressBar').style.width = pct + '%';
        document.getElementById('reconProgressPct').textContent = pct + '%';

        if (done >= total) {
            document.getElementById('reconProgressText').textContent = `✅ Парсинг завершён: ${done} из ${total} компаний обработано`;
            document.getElementById('reconProgressBar').style.background = 'linear-gradient(90deg,#10b981,#34d399)';
        } else if (done > 0) {
            document.getElementById('reconProgressText').textContent = `⏳ В процессе: обработано ${done} из ${total} компаний...`;
            document.getElementById('reconProgressBar').style.background = 'linear-gradient(90deg,#3b82f6,#60a5fa)';
        } else {
            document.getElementById('reconProgressText').textContent = 'Нажмите «Запустить парсинг» чтобы начать сбор данных';
        }
    }

    // Load contacts
    const data = await api('/recon/contacts?limit=300');
    if (data && data.contacts && data.contacts.length > 0) {
        document.getElementById('reconContactsCount').textContent = data.total;
        const tbody = document.getElementById('reconContactsBody');
        tbody.innerHTML = '';

        for (const c of data.contacts) {
            const icon = TYPE_ICONS[c.type] || '🔗';
            const label = TYPE_LABELS[c.type] || c.type;
            let valueHtml = c.value;

            // Make links clickable
            if (c.type === 'email') {
                valueHtml = `<a href="mailto:${c.value}" style="color:var(--accent)">${c.value}</a>`;
            } else if (c.type === 'phone') {
                valueHtml = `<a href="tel:${c.value}" style="color:var(--accent)">${c.value}</a>`;
            } else if (c.value.startsWith('http')) {
                valueHtml = `<a href="${c.value}" target="_blank" style="color:var(--accent)">${c.value}</a>`;
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${c.company_name}</strong></td>
                <td>${icon} ${label}</td>
                <td>${valueHtml}</td>
                <td><span class="badge badge-warm">${c.source}</span></td>
            `;
            tbody.appendChild(tr);
        }
    }
}

// Start recon button
document.getElementById('btnStartRecon')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnStartRecon');
    const status = await api('/recon/status');
    const remaining = status?.remaining || 0;

    if (remaining === 0) {
        alert('🎉 Все компании с сайтами уже спарсены!');
        return;
    }

    if (confirm(`📊 Осталось ${remaining} компаний для парсинга.\n\nЗапустить?`)) {
        btn.disabled = true;
        btn.textContent = '⏳ Парсинг запущен...';
        await api('/recon/crawl?limit=50', { method: 'POST' });

        // Auto-refresh every 10 seconds while parsing
        let refreshCount = 0;
        const autoRefresh = setInterval(async () => {
            await loadReconData();
            refreshCount++;
            if (refreshCount > 60) clearInterval(autoRefresh); // Stop after 10 minutes
            const s = await api('/recon/status');
            if (s && s.remaining === 0) {
                clearInterval(autoRefresh);
                btn.textContent = '🚀 Запустить парсинг';
                btn.disabled = false;
            }
        }, 10000);

        btn.textContent = '🔄 Парсинг идёт...';
    }
});

// Refresh button
document.getElementById('btnRefreshRecon')?.addEventListener('click', () => loadReconData());

// Also keep old dashboard button working
document.getElementById('btnReconCrawl')?.addEventListener('click', () => {
    // Navigate to recon view
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelector('[data-view="recon"]')?.classList.add('active');
    document.getElementById('view-recon')?.classList.add('active');
    loadReconData();
});

// ─── Init ───
loadStaticData().then(() => loadDashboard());
