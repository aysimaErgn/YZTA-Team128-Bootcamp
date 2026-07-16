// dashboard.js — aile paneli + PR-3a gerçek zamanlı uyarı

const API_BASE_URL = (window.CONFIG && CONFIG.API_BASE_URL) || "http://127.0.0.1:8000/api";
const WS_BASE_URL = (window.CONFIG && CONFIG.WS_BASE_URL) || "ws://127.0.0.1:8000";
const ALERT_POLL_MS = 30000;

let familyWs = null;
let familyWsReconnectTimer = null;
let alertPollTimer = null;
let lastSeenAlertKey = null;
let criticalAudioCtx = null;

document.addEventListener('DOMContentLoaded', () => {
    const role = localStorage.getItem('user_role');
    if (role !== 'family') {
        alert("Bu panele erişim yetkiniz yok. Lütfen Aile Girişi yapın.");
        window.location.href = "login.html";
        return;
    }

    const familyName = localStorage.getItem('family_name') || "Değerli Refakatçimiz";
    const elderlyName = localStorage.getItem('elderly_name') || "Yakınınız";

    document.getElementById('welcome-family').innerText = `Hoş geldiniz, ${familyName}`;
    document.getElementById('elderly-title').innerText = `Takip Edilen: ${elderlyName}`;

    const dismissBtn = document.getElementById('critical-alert-dismiss');
    if (dismissBtn) {
        dismissBtn.addEventListener('click', hideCriticalAlert);
    }

    fetchDashboardData().then(() => {
        startFamilyRealtime();
    });
});

function setLiveConnectionStatus(isOnline) {
    const el = document.getElementById('live-connection');
    if (!el) return;
    el.classList.toggle('ws-offline', !isOnline);
    el.innerHTML = isOnline
        ? '<i class="fas fa-circle" style="font-size: 8px; color: #22C55E; margin-right: 5px;"></i> Canlı'
        : '<i class="fas fa-circle" style="font-size: 8px; color: #F59E0B; margin-right: 5px;"></i> Yeniden bağlanıyor';
}

function playCriticalBeep() {
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        if (!criticalAudioCtx) criticalAudioCtx = new AudioContext();
        const ctx = criticalAudioCtx;
        if (ctx.state === 'suspended') ctx.resume();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'square';
        osc.frequency.value = 880;
        gain.gain.value = 0.08;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        setTimeout(() => {
            osc.stop();
            osc.disconnect();
            gain.disconnect();
        }, 320);
    } catch (error) {
        console.warn('Uyarı sesi çalınamadı:', error);
    }
}

function showCriticalAlert(description, meta = {}) {
    const banner = document.getElementById('critical-alert-banner');
    const text = document.getElementById('critical-alert-description');
    if (!banner || !text) return;

    const detail = description || 'Yakınınız için kritik bir sağlık olayı bildirildi.';
    text.textContent = detail;
    banner.hidden = false;
    playCriticalBeep();

    const health = document.getElementById('health-status');
    if (health) health.innerText = 'Acil dikkat';

    if (meta.prependToList !== false) {
        prependLiveAlertToList({
            alert_type: meta.alert_type || 'conversation_risk',
            severity: meta.severity || 'high',
            description: detail,
            created_at: new Date().toISOString(),
        });
    }
}

function hideCriticalAlert() {
    const banner = document.getElementById('critical-alert-banner');
    if (banner) banner.hidden = true;
}

function prependLiveAlertToList(alert) {
    const panel = document.getElementById('med-alerts-panel');
    const list = document.getElementById('med-alerts-list');
    if (!panel || !list) return;
    panel.style.display = 'block';
    const existing = list.innerHTML;
    list.innerHTML = buildAlertCard(alert) + existing;
}

function alertTypeLabel(alertType) {
    if (alertType === 'medication_missed') return 'İlaç Kaçırıldı';
    if (alertType === 'wrong_medication' || alertType === 'medication_wrong') return 'Yanlış İlaç';
    if (alertType === 'conversation_risk') return 'Sağlık Riski';
    return 'Uyarı';
}

function buildAlertCard(alert) {
    const time = alert.created_at
        ? new Date(alert.created_at).toLocaleString('tr-TR')
        : '';
    const severityColor = alert.severity === 'high' ? '#EF4444' : '#F59E0B';
    return `
        <div style="padding:12px; margin-bottom:8px; background:#FEF2F2; border-radius:8px; border-left:3px solid ${severityColor};">
            <strong style="color:${severityColor};">${alertTypeLabel(alert.alert_type)}</strong>
            <p style="margin:4px 0 0; font-size:14px; color:var(--text-main);">${alert.description || ''}</p>
            <small style="color:var(--text-muted);">${time}</small>
        </div>
    `;
}

function handleCriticalWsEvent(payload) {
    if (!payload || payload.type !== 'CRITICAL_HEALTH_EVENT') return;
    const key = `${payload.alert_type}|${payload.description}|${payload.elder_id || ''}`;
    if (key === lastSeenAlertKey) return;
    lastSeenAlertKey = key;
    showCriticalAlert(payload.description, {
        alert_type: payload.alert_type,
        severity: payload.severity,
    });
}

function connectFamilyWebSocket(elderProfileId) {
    if (!elderProfileId) return;
    if (familyWs && (familyWs.readyState === WebSocket.OPEN || familyWs.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const wsUrl = `${WS_BASE_URL}/ws/client/${elderProfileId}?role=family`;
    try {
        familyWs = new WebSocket(wsUrl);
    } catch (error) {
        console.error('Aile WS açılamadı:', error);
        setLiveConnectionStatus(false);
        scheduleWsReconnect(elderProfileId);
        return;
    }

    familyWs.onopen = () => {
        setLiveConnectionStatus(true);
        if (familyWsReconnectTimer) {
            clearTimeout(familyWsReconnectTimer);
            familyWsReconnectTimer = null;
        }
    };

    familyWs.onmessage = (event) => {
        try {
            const payload = JSON.parse(event.data);
            handleCriticalWsEvent(payload);
        } catch (error) {
            console.warn('WS mesajı parse edilemedi:', error);
        }
    };

    familyWs.onclose = () => {
        setLiveConnectionStatus(false);
        scheduleWsReconnect(elderProfileId);
    };

    familyWs.onerror = () => {
        setLiveConnectionStatus(false);
        try { familyWs.close(); } catch (_) { /* ignore */ }
    };
}

function scheduleWsReconnect(elderProfileId) {
    if (familyWsReconnectTimer) return;
    familyWsReconnectTimer = setTimeout(() => {
        familyWsReconnectTimer = null;
        connectFamilyWebSocket(elderProfileId);
    }, 4000);
}

async function pollAlertsFallback(elderProfileId) {
    if (!elderProfileId) return;
    try {
        const alertsRes = await fetch(`${API_BASE_URL}/medication/alerts/${elderProfileId}`);
        const alertsData = await alertsRes.json();
        if (!alertsRes.ok || !alertsData.alerts?.length) return;

        renderMedicationAlerts(alertsData.alerts);

        const newest = alertsData.alerts[0];
        const key = `${newest.alert_type}|${newest.description}|${newest.id || newest.created_at}`;
        const isHigh = newest.severity === 'high';
        const isCriticalType = newest.alert_type === 'conversation_risk'
            || newest.alert_type === 'medication_missed';

        if (isHigh && isCriticalType && key !== lastSeenAlertKey) {
            const wsOpen = familyWs && familyWs.readyState === WebSocket.OPEN;
            if (!wsOpen) {
                lastSeenAlertKey = key;
                showCriticalAlert(newest.description, {
                    alert_type: newest.alert_type,
                    severity: newest.severity,
                    prependToList: false,
                });
            } else {
                lastSeenAlertKey = key;
            }
        }
    } catch (error) {
        console.warn('Alert poll hatası:', error);
    }
}

function startAlertPolling(elderProfileId) {
    if (alertPollTimer) clearInterval(alertPollTimer);
    pollAlertsFallback(elderProfileId);
    alertPollTimer = setInterval(() => pollAlertsFallback(elderProfileId), ALERT_POLL_MS);
}

async function startFamilyRealtime() {
    const elderProfileId = localStorage.getItem('elder_id') || await syncElderForFamily();
    if (!elderProfileId) {
        console.warn('elder_id yok; aile WS başlatılamadı.');
        return;
    }
    connectFamilyWebSocket(elderProfileId);
    startAlertPolling(elderProfileId);
}

async function syncElderForFamily() {
    const elderlyId = localStorage.getItem('elderly_id');
    const elderlyName = localStorage.getItem('elderly_name') || 'Yakınınız';
    if (!elderlyId) return null;

    try {
        const response = await fetch(`${API_BASE_URL}/medications/sync-elder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: elderlyId, user_name: elderlyName }),
        });
        const data = await response.json();
        if (response.ok && data.elder?.id) {
            localStorage.setItem('elder_id', data.elder.id);
            return data.elder.id;
        }
    } catch (error) {
        console.error('Yaşlı profili eşleştirilemedi:', error);
    }
    return localStorage.getItem('elder_id');
}

async function initFamilyMedications() {
    if (typeof MedicationDefinitions === 'undefined') return;

    const elderlyId = localStorage.getItem('elderly_id');
    const elderlyName = localStorage.getItem('elderly_name') || 'Yakınınız';

    await MedicationDefinitions.init({
        mode: 'family',
        apiBaseUrl: API_BASE_URL,
        todayOnly: false,
        userId: elderlyId,
        userName: elderlyName,
    });
}

function renderWeeklyTrend(weeklyTrend) {
    const container = document.getElementById('weekly-trend-chart');
    if (!container) return;

    if (!weeklyTrend || weeklyTrend.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); font-size: 14px;">Henüz yeterli ilaç kaydı yok.</p>';
        return;
    }

    container.innerHTML = weeklyTrend.map((day) => {
        const total = (day.taken || 0) + (day.missed || 0) + (day.wrong_medication || 0);
        const rate = total > 0 ? Math.round((day.taken / total) * 100) : 0;
        const dateLabel = new Date(day.date).toLocaleDateString('tr-TR', { weekday: 'short', day: 'numeric', month: 'short' });
        return `
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                <span style="width:90px; font-size:13px; color:var(--text-muted);">${dateLabel}</span>
                <div style="flex:1; background:#E2E8F0; border-radius:6px; height:12px; overflow:hidden;">
                    <div style="width:${rate}%; background:#10B981; height:100%; border-radius:6px;"></div>
                </div>
                <span style="width:50px; font-size:13px; font-weight:600;">%${rate}</span>
            </div>
        `;
    }).join('');
}

function renderMedicationAlerts(alerts) {
    const panel = document.getElementById('med-alerts-panel');
    const list = document.getElementById('med-alerts-list');
    if (!panel || !list) return;

    if (!alerts || alerts.length === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';
    list.innerHTML = alerts.map((alert) => buildAlertCard(alert)).join('');
}

function statusBadgeClass(status) {
    if (status === 'Başarılı') return 'status-good';
    if (status === 'Tehlike') return 'status-bad';
    return 'status-warn';
}

async function loadEventHistory(elderProfileId) {
    const tbody = document.getElementById('history-table-body');
    if (!tbody || !elderProfileId) return;

    try {
        const response = await fetch(`${API_BASE_URL}/medication/history/${elderProfileId}`);
        const data = await response.json();

        if (!response.ok || !data.events?.length) {
            tbody.innerHTML = '<tr><td colspan="4">Henüz kayıt bulunmuyor.</td></tr>';
            return;
        }

        tbody.innerHTML = data.events.map((event) => {
            const time = event.timestamp
                ? new Date(event.timestamp).toLocaleString('tr-TR')
                : '-';
            const badgeClass = statusBadgeClass(event.status);
            return `
                <tr>
                    <td>${time}</td>
                    <td>${event.category}</td>
                    <td><span class="status-badge ${badgeClass}">${event.status}</span></td>
                    <td>${event.description}</td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error('Geçmiş yüklenemedi:', error);
        tbody.innerHTML = '<tr><td colspan="4">Geçmiş yüklenirken hata oluştu.</td></tr>';
    }
}

async function fetchDashboardData() {
    const elderlyId = localStorage.getItem('elderly_id');
    const elderProfileId = await syncElderForFamily();

    try {
        const response = await fetch(`${API_BASE_URL}/family/dashboard-summary/${elderlyId}`);
        const data = await response.json();

        if (response.ok && data.success) {
            document.getElementById('health-status').innerText = translateMood(data.latest_mood);
            document.getElementById('activity-status').innerText = data.activity_status;

            if (data.medication_status) {
                document.getElementById('pill-status').innerText = data.medication_status;
            }

            if (data.medication_stats?.weekly_trend) {
                renderWeeklyTrend(data.medication_stats.weekly_trend);
            }

            if (data.recent_alerts) {
                renderMedicationAlerts(data.recent_alerts);
            }
        }

        if (elderProfileId) {
            const statsRes = await fetch(`${API_BASE_URL}/medication/stats/${elderProfileId}`);
            const stats = await statsRes.json();
            if (statsRes.ok) {
                const rate = stats.adherence_rate ?? 0;
                document.getElementById('pill-status').innerText =
                    stats.total_logs > 0 ? `%${rate} Uyum` : 'Henüz kayıt yok';
                renderWeeklyTrend(stats.weekly_trend);

                const alertsRes = await fetch(`${API_BASE_URL}/medication/alerts/${elderProfileId}`);
                const alertsData = await alertsRes.json();
                if (alertsRes.ok) {
                    renderMedicationAlerts(alertsData.alerts);
                }
            }

            await loadEventHistory(elderProfileId);
        }

        const aiBox = document.getElementById('ai-summary');
        aiBox.innerHTML = `<em><i class="fas fa-spinner fa-spin"></i> Yapay Zeka konuşmaları analiz ediyor ve özet hazırlıyor...</em>`;

        const aiResponse = await fetch(`${API_BASE_URL}/family/generate-ai-summary`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ conversation_id: elderlyId })
        });

        const aiData = await aiResponse.json();
        if (aiResponse.ok && aiData.success) {
            aiBox.innerText = aiData.summary;
        } else {
            aiBox.innerText = "Bugünkü sohbet analizi yüklenirken bir sorun oluştu.";
        }

    } catch (error) {
        console.error("Dashboard verisi veya AI özeti çekilirken hata:", error);
    }
}

function translateMood(mood) {
    const moods = {
        'good': 'Harika 😊',
        'bad': 'Biraz Halsiz 😔',
        'normal': 'Normal 🙂',
        'tired': 'Yorgun 🥱',
        'Harika!': 'Harika 😊',
        'Biraz halsizim': 'Biraz Halsiz 😔',
    };
    return moods[mood] || mood;
}

function switchDashboardTab(tabName) {
    document.querySelectorAll('.dashboard-section').forEach(sec => sec.style.display = 'none');
    document.querySelectorAll('.sidebar-menu li').forEach(li => li.classList.remove('active'));

    if (tabName === 'summary') {
        document.getElementById('sec-summary').style.display = 'block';
    } else if (tabName === 'history') {
        document.getElementById('sec-history').style.display = 'block';
        syncElderForFamily().then((id) => { if (id) loadEventHistory(id); });
    } else if (tabName === 'medications') {
        document.getElementById('sec-medications').style.display = 'block';
        initFamilyMedications();
    } else if (tabName === 'settings') {
        document.getElementById('sec-settings').style.display = 'block';
    }
    event.currentTarget.classList.add('active');
}

function handleLogout() {
    if (familyWs) {
        try { familyWs.close(); } catch (_) { /* ignore */ }
    }
    if (alertPollTimer) clearInterval(alertPollTimer);
    if (familyWsReconnectTimer) clearTimeout(familyWsReconnectTimer);
    localStorage.clear();
    alert("Oturum kapatıldı.");
    window.location.href = "login.html";
}
