const API_BASE_URL = "http://127.0.0.1:8000/api";
let localStream = null;
let registerStream = null;
let registeredBase64Image = null; // Kayıt esnasında çekilen fotoğrafı burada saklayacağız

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

// =====================================================================
// 1. YAŞLI YÜZ TANIMA GİRİŞ FONKSİYONLARI
// =====================================================================

async function initWebcam() {
    const video = document.getElementById('webcam');
    if (!video) return;
    
    try {
        localStream = await navigator.mediaDevices.getUserMedia({ video: { width: 400, height: 300 } });
        video.srcObject = localStream;
        document.getElementById('face-status').innerText = "Kamera hazır. Giriş yapmak için lütfen butona basın.";
        document.getElementById('face-status').style.color = "var(--text-muted)";
    } catch (err) {
        console.error("Kameraya erişilemedi:", err);
        document.getElementById('face-status').innerText = "Kamera izni verilmedi veya kamera bulunamadı!";
        document.getElementById('face-status').style.color = "red";
    }
}

function stopWebcam() {
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
    }
}

// Kameradan anlık fotoğrafı yakalayıp yüz tanıma endpoint'ine gönderen fonksiyon
async function startFaceRecognition() {
    const video = document.getElementById('webcam');
    const statusText = document.getElementById('face-status');
    
    if (!video || !localStream) {
        if (statusText) statusText.innerText = "Kamera aktif değil.";
        return;
    }

    if (statusText) {
        statusText.innerText = "Yüzünüz taranıyor ve analiz ediliyor, lütfen bekleyin...";
        statusText.style.color = "orange";
    }

    // Kare yakalamak için canvas oluşturuyoruz (Boyutları sabitledik)
    const canvas = document.createElement('canvas');
    canvas.width = 400;
    canvas.height = 300;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    const base64Image = canvas.toDataURL('image/jpeg');

    try {
        const response = await fetch(`${API_BASE_URL}/auth/face-login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_data: base64Image })
        });
        
        const data = await response.json();

        if (response.ok && data.success) {
            if (statusText) {
                statusText.innerText = `✔️ Giriş başarılı! Hoş geldiniz, ${data.name}`;
                statusText.style.color = "green";
            }
            stopWebcam();
            localStorage.setItem('user_id', data.user_id);
            localStorage.setItem('user_name', data.name);
            setTimeout(() => { window.location.href = "index.html"; }, 1200);
        } else {
            if (statusText) {
                statusText.innerText = data.detail || "Yüz eşleşmedi. Lütfen tekrar deneyin.";
                statusText.style.color = "red";
            }
        }
    } catch (error) {
        console.error("Giriş hatası:", error);
        if (statusText) statusText.innerText = "Sistem hatası. Sunucuya bağlanılamadı.";
    }
}

// =====================================================================
// B PLANI: BİLGİLERLE (AD-SOYAD VE YAŞ) GİRİŞ YAPMA FONKSİYONU
// =====================================================================
async function loginWithCredentials() {
    const nameInput = document.getElementById('elderly-login-name').value.trim();
    const ageInput = document.getElementById('elderly-login-age').value.trim();
    const statusText = document.getElementById('face-status');

    if (!nameInput || !ageInput) {
        alert("Lütfen adınızı, soyadınızı ve yaşınızı eksiksiz girin!");
        return;
    }

    if (statusText) {
        statusText.innerText = "Bilgileriniz doğrulanıyor, lütfen bekleyin...";
        statusText.style.color = "orange";
    }

    try {
        // Doğrudan localhost portuna yönlendirerek yönlendirme hatalarını bypass ediyoruz
        const response = await fetch(`http://127.0.0.1:8000/api/auth/credentials-login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: nameInput,
                age: parseInt(ageInput)
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            if (statusText) {
                statusText.innerText = `✔️ Giriş başarılı! Hoş geldiniz, ${data.name}`;
                statusText.style.color = "green";
            }
            stopWebcam(); // Kamerayı kapat
            
            localStorage.setItem('user_id', data.user_id);
            localStorage.setItem('user_name', data.name);
            alert(`Giriş Başarılı! Ana sayfaya yönlendiriliyorsunuz.`);
            window.location.href = "index.html";
        } else {
            if (statusText) {
                statusText.innerText = data.detail || "Giriş başarısız.";
                statusText.style.color = "red";
            }
            alert(data.detail || "Giriş başarısız. Bilgilerinizi kontrol edin.");
        }
    } catch (error) {
        console.error("Yazılı giriş hatası:", error);
        alert("Sunucu bağlantı hatası oluştu.");
    }
}

// =====================================================================
// 2. AİLE / REFAKATÇİ GİRİŞ FONKSİYONU
// =====================================================================
async function handleFamilyLogin(event) {
    event.preventDefault();
    const phone = document.getElementById('login-phone').value.trim();
    const password = document.getElementById('login-password').value;

    try {
        const response = await fetch(`${API_BASE_URL}/auth/family-login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert("Giriş Başarılı!");
            window.location.href = "index.html";
        } else {
            alert(data.detail || "Hatalı telefon numarası veya şifre!");
        }
    } catch (error) {
        console.error(error);
        alert("Bağlantı hatası!");
    }
}

// =====================================================================
// 3. KAYIT OLMA (REGISTER) FONKSİYONLARI
// =====================================================================

async function openRegisterCamera() {
    const video = document.getElementById('reg-webcam');
    const statusText = document.getElementById('reg-camera-status');
    if (!video) return;

    try {
        registerStream = await navigator.mediaDevices.getUserMedia({ video: { width: 400, height: 300 } });
        video.srcObject = registerStream;
        statusText.innerText = "📷 Kamera aktif. 'Fotoğrafı Yakala' butonuna basın.";
        statusText.style.color = "var(--brand-color)";
    } catch (err) {
        statusText.innerText = "❌ Kamera izni verilmedi veya kamera bulunamadı.";
        statusText.style.color = "red";
    }
}

function captureRegisterFace() {
    const video = document.getElementById('reg-webcam');
    const statusText = document.getElementById('reg-camera-status');
    if (!video || !registerStream) return;

    const canvas = document.createElement('canvas');
    canvas.width = 400;
    canvas.height = 300;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    registeredBase64Image = canvas.toDataURL('image/jpeg');
    statusText.innerText = "✔️ Yüz fotoğrafınız hafızaya alındı.";
    statusText.style.color = "green";

    // Kamerayı durdurarak sistemi rahatlatıyoruz
    if (registerStream) {
        registerStream.getTracks().forEach(track => track.stop());
    }
}

async function handleRegister(event) {
    event.preventDefault();
    const statusText = document.getElementById('reg-camera-status');
    
    if (!registeredBase64Image) {
        alert("Lütfen önce yüzünüzü kameradan taratın!");
        return;
    }

    try {
        // A. Önce DeepFace'e yüz fotoğrafını yollayıp vektör alıyoruz
        const faceResponse = await fetch(`${API_BASE_URL}/auth/register-face`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_data: registeredBase64Image })
        });

        const faceData = await faceResponse.json();
        if (!faceResponse.ok || !faceData.success) {
            alert("Yüz analizi başarısız oldu. Lütfen tekrar fotoğraf çekilin.");
            return;
        }

        const faceVector = faceData.face_vector;

        // B. Şimdi tüm form verilerini ve vektörü paketleyip ana kayıt endpoint'ine atıyoruz
        const payload = {
            elderly: {
                name: document.getElementById('elderly-name').value.trim(),
                age: parseInt(document.getElementById('elderly-age').value) || 0,
                face_vector: faceVector
            },
            family: {
                name: document.getElementById('family-name').value.trim(),
                phone: document.getElementById('family-phone').value.trim(),
                password: document.getElementById('family-password').value
            }
        };

        const response = await fetch(`${API_BASE_URL}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const resultData = await response.json();

        if (response.ok) {
            alert("Kayıt işlemi başarıyla tamamlandı! Giriş ekranına yönlendiriliyorsunuz.");
            window.location.href = "login.html";
        } else {
            alert("Kayıt hatası: " + (resultData.detail || "Hata oluştu."));
        }
    } catch (error) {
        console.error("Kayıt hatası:", error);
        alert("Sunucu bağlantısı kurulamadı.");
    }
}