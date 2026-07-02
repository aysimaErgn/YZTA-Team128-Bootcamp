const API_BASE_URL = "http://127.0.0.1:8000/api";
let localStream = null;

// Sayfa yüklendiğinde eğer giriş sayfasındaysak kamerayı yaşlı için otomatik hazırla
window.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('webcam')) {
        initWebcam();
    }
});

// Giriş ekranında sekmeler arası geçiş (Yaşlı vs Aile)
function switchAuthTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    
    if (tabName === 'elderly') {
        document.querySelector("[onclick=\"switchAuthTab('elderly')\"]").classList.add('active');
        document.getElementById('tab-elderly').classList.add('active');
        initWebcam(); // Yaşlı sekmesine dönünce kamerayı aç
    } else {
        document.querySelector("[onclick=\"switchAuthTab('family')\"]").classList.add('active');
        document.getElementById('tab-family').classList.add('active');
        stopWebcam(); // Aile sekmesine geçince kamerayı kapat (performans)
    }
}

// Kamerayı Başlatma
async function initWebcam() {
    const video = document.getElementById('webcam');
    if (!video) return;
    
    try {
        localStream = await navigator.mediaDevices.getUserMedia({ video: { width: 400, height: 300 } });
        video.srcObject = localStream;
    } catch (err) {
        console.error("Kameraya erişilemedi:", err);
        document.getElementById('face-status').innerText = "Kamera izni verilmedi veya kamera bulunamadı!";
        document.getElementById('face-status').style.color = "red";
    }
}

// Kamerayı Kapatma
function stopWebcam() {
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
    }
}

// =====================================================================
// SİMÜLASYON / API: YÜZ TANIMA İLE GİRİŞ YAPMA
// =====================================================================
async function startFaceRecognition() {
    const video = document.getElementById('webcam');
    const statusText = document.getElementById('face-status');
    
    if (!video || !localStream) {
        statusText.innerText = "Kamera aktif değil.";
        return;
    }

    statusText.innerText = "Yüz taranıyor ve analiz ediliyor...";
    statusText.style.color = "var(--brand-color)";

    // Arka planda anlık fotoğraf yakalamak için geçici bir canvas oluşturuyoruz
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    
    // Videodaki o anki kareyi canvas'a çiz
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // Fotoğrafı Base64 formatına çevir (örn: data:image/jpeg;base64,/9j/4AAQSkZJR...)
    const base64Image = canvas.toDataURL('image/jpeg');

    try {
        // Python FastAPI Sunucusuna Gönderiyoruz
        const response = await fetch(`${API_BASE_URL}/auth/face-login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_data: base64Image })
        });
        
        const data = await response.json();

        if (response.ok && data.success) {
            statusText.innerText = `✔️ ${data.message}`;
            statusText.style.color = "green";
            stopWebcam();
            // Giriş başarılı olunca ana sayfaya yönlendir
            setTimeout(() => { window.location.href = "index.html"; }, 1500);
        } else {
            statusText.innerText = data.detail || "Yüz eşleşmedi. Lütfen tekrar deneyin.";
            statusText.style.color = "red";
        }
    } catch (error) {
        console.error("Yüz tanıma sunucu hatası:", error);
        statusText.innerText = "Sistem hatası. Sunucuya bağlanılamadı.";
        statusText.style.color = "red";
    }
}

// =====================================================================
// API: AİLE TELEFON VE ŞİFRE İLE GİRİŞ
// =====================================================================
async function handleFamilyLogin(event) {
    event.preventDefault();
    const phone = document.getElementById('login-phone').value;
    const password = document.getElementById('login-password').value;

    try {
        const response = await fetch(`${API_BASE_URL}/auth/family-login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone, password })
        });
        
        if (response.ok) {
            alert("Giriş Başarılı! Aile paneline yönlendiriliyorsunuz.");
            window.location.href = "index.html";
        } else {
            alert("Hatalı telefon veya şifre!");
        }
    } catch (error) {
        alert("Bağlantı hatası! (Simüle giriş yapılıyor)");
        window.location.href = "index.html";
    }
}

// =====================================================================
// API: HEM YAŞLI HEM AİLE BİLGİLERİNİ TEK SEFERDE KAYDETME (REGISTER)
// =====================================================================
function openRegisterCamera() {
    alert("Yaşlı kullanıcının yüz biyometrisi için kamera referansı alındı! (Simüle Edildi)");
    document.getElementById('reg-camera-status').innerText = "✔️ Yüz verisi başarıyla tarandı.";
    document.getElementById('reg-camera-status').style.color = "green";
}

async function handleRegister(event) {
    event.preventDefault();
    
    // Bilgileri Topla
    const payload = {
        elderly: {
            name: document.getElementById('elderly-name').value,
            age: parseInt(document.getElementById('elderly-age').value),
            face_features_registered: true
        },
        family: {
            name: document.getElementById('family-name').value,
            phone: document.getElementById('family-phone').value,
            password: document.getElementById('family-password').value
        }
    };

    try {
        const response = await fetch(`${API_BASE_URL}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            alert("Kayıt işlemi başarıyla tamamlandı! Giriş ekranına gidiyorsunuz.");
            window.location.href = "login.html";
        } else {
            alert("Kayıt sırasında bir hata oluştu.");
        }
    } catch (error) {
        alert("Kayıt Başarılı (Simüle Edildi). Giriş ekranına yönlendiriliyorsunuz.");
        window.location.href = "login.html";
    }
}