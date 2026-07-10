// dashboard.js dosyasının güncel hali

const API_BASE_URL = "http://127.0.0.1:8000/api";

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

    fetchDashboardData();
});

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
    list.innerHTML = alerts.map((alert) => {
        const time = alert.created_at
            ? new Date(alert.created_at).toLocaleString('tr-TR')
            : '';
        const severityColor = alert.severity === 'high' ? '#EF4444' : '#F59E0B';
        return `
            <div style="padding:12px; margin-bottom:8px; background:#FEF2F2; border-radius:8px; border-left:3px solid ${severityColor};">
                <strong style="color:${severityColor};">${alert.alert_type === 'medication_missed' ? 'İlaç Kaçırıldı' : 'Yanlış İlaç'}</strong>
                <p style="margin:4px 0 0; font-size:14px; color:var(--text-main);">${alert.description || ''}</p>
                <small style="color:var(--text-muted);">${time}</small>
            </div>
        `;
    }).join('');
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
    localStorage.clear();
    alert("Oturum kapatıldı.");
    window.location.href = "login.html";
}
