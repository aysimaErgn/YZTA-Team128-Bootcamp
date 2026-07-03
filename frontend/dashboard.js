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

    // Canlı verileri backend'den çekiyoruz
    fetchDashboardData();
});

async function fetchDashboardData() {
    const elderlyId = localStorage.getItem('elderly_id') || "varsayilan-oturum-id"; 

    try {
        // [Mevcut verileri çekme istekleriniz burada kalıyor...]
        const response = await fetch(`${API_BASE_URL}/family/dashboard-summary/${elderlyId}`);
        const data = await response.json();
        
        if (response.ok && data.success) {
            document.getElementById('health-status').innerText = translateMood(data.latest_mood);
            document.getElementById('pill-status').innerText = data.medication_status;
            document.getElementById('activity-status').innerText = data.activity_status;
            // [Tablo doldurma mantığı...]
        }

        // ==========================================
        // YENİ: YAPAY ZEKA GÜNLÜK ÖZETİNİ TETİKLEME
        // ==========================================
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

// Mood değerlerini Türkçe ve anlaşılır yapma fonksiyonu
function translateMood(mood) {
    const moods = {
        'good': 'Harika 😊',
        'bad': 'Biraz Halsiz 😔',
        'normal': 'Normal 🙂',
        'tired': 'Yorgun 🥱'
    };
    return moods[mood] || mood;
}

// Sekme Geçiş Mantığı
function switchDashboardTab(tabName) {
    document.querySelectorAll('.dashboard-section').forEach(sec => sec.style.display = 'none');
    document.querySelectorAll('.sidebar-menu li').forEach(li => li.classList.remove('active'));

    if (tabName === 'summary') {
        document.getElementById('sec-summary').style.display = 'block';
    } else if (tabName === 'history') {
        document.getElementById('sec-history').style.display = 'block';
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