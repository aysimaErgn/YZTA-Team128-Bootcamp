let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let stream = null;

// Her oturum açıldığında yeni bir conversation_id oluşturur (Eğer eskilerden biri seçilmediyse)
let activeChatId = "chat_" + Date.now();

const voiceBtn = document.getElementById('voiceBtn');
const btnText = document.getElementById('btnText');
const chatBox = document.getElementById('chatBox');
const chatScroll = document.getElementById('chatScroll');
const userInput = document.getElementById('userInput');
const historySidebar = document.getElementById('historySidebar');
const historyTodayList = document.getElementById('history-today');

const API_BASE_URL = "http://127.0.0.1:8000/api";

// Sayfa ilk yüklendiğinde Supabase'deki geçmiş sohbetleri getirir

window.addEventListener('DOMContentLoaded', async () => {
    // 1. Önce sol menüdeki geçmiş başlıklarını Supabase'den çek
    await loadConversationsFromSupabase();
    
    // 2. Eğer Supabase'de daha önce yapılmış EN AZ BİR sohbet varsa:
    const firstChatElement = historyTodayList.querySelector('.history-item');
    if (firstChatElement) {
        // En son konuşulan sohbetin elementinden ID'sini çek ve otomatik yükle
        // (Böylece sayfa açılır açılmaz bugünkü veya en son mesajlar ekrana gelir)
        firstChatElement.click(); 
    } else {
        // Eğer veritabanı tamamen bossa, backend'deki GECERLI_UUID'yi veya yeni ID'yi kullan
        // Şimdilik backend ile eşleşmesi için test UUID'sini aktif edebilirsin:
        activeChatId = "890f8eb3-2734-47d8-864a-df1a33f9a161"; 
        chatBox.innerHTML = `<div class="chat-msg msg-ai">Merhaba Ahmet Amca, bugün henüz konuşmadık. Sesini duymak çok güzel, nasılsın?</div>`;
    }
});

function switchPage(pageId) {
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`page-${pageId}`).classList.add('active');
    document.getElementById(`nav-${pageId}`).classList.add('active');
    
    if (pageId === 'sohbet') {
        historySidebar.style.display = 'flex';
    } else {
        historySidebar.style.display = 'none';
    }

    if (pageId === 'durum') {
        loadCheckinHistory();
    }
}

// Günlük check-in geçmişini backend'den çekip listeler
async function loadCheckinHistory() {
    const historyBox = document.getElementById('checkinHistory');
    try {
        const response = await fetch(`${API_BASE_URL}/checkin/history`);
        const data = await response.json();
        const history = data.history || [];

        if (history.length === 0) {
            historyBox.innerHTML = `<p style="color: var(--text-muted); font-size: 16px;">Henüz kayıt yok.</p>`;
            return;
        }

        historyBox.innerHTML = history.map(item => {
            const date = new Date(item.created_at);
            const dateStr = date.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' });
            const timeStr = date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
            return `
                <div class="routine-item">
                    <div>
                        <strong style="display:block; font-size:18px;">${item.mood}</strong>
                        <span style="font-size: 14px; color: var(--text-muted);">${dateStr} • ${timeStr}</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error(error);
        historyBox.innerHTML = `<p style="color: var(--warning-color); font-size: 16px;">Kayıtlar yüklenemedi.</p>`;
    }
}

// 1. Supabase'den Konuşma Başlıklarını Çeken Fonksiyon
async function loadConversationsFromSupabase() {
    if (!historyTodayList) return;
    historyTodayList.innerHTML = "";

    try {
        const response = await fetch(`${API_BASE_URL}/conversations`);
        const conversations = await response.json();

        conversations.forEach(conv => {
            const item = document.createElement('div');
            // Aktif sohbeti vurgulamak için sınıf kontrolü
            item.className = `history-item ${conv.conversation_id === activeChatId ? 'active-chat' : ''}`;
            
            // Burada artık mesaj içeriği değil, backend'den gelen tarih yazacak
            item.innerText = conv.title; 
            
            item.setAttribute('data-id', conv.conversation_id); 
            item.onclick = () => loadSpecificChatFromServer(conv.conversation_id);
            historyTodayList.appendChild(item);
        });
    } catch (error) {
        console.error("Geçmiş yüklenirken hata oluştu:", error);
    }
}


// Geçmişteki bir sohbete tıklandığında mesajları Supabase'den getirir
async function loadSpecificChatFromServer(id) {
    activeChatId = id; // Aktif sohbet ID'sini güncelliyoruz
    chatBox.innerHTML = ""; // Ekranı temizle
    
    try {
        const response = await fetch(`${API_BASE_URL}/conversations/${id}`);
        const messages = await response.json();

        if (!messages || messages.length === 0) {
            chatBox.innerHTML = `<div class="chat-msg msg-ai">Bu sohbet boş görünüyor Ahmet Amca.</div>`;
            return;
        }

        // Mesajları sırayla ekrana bas
        messages.forEach(msg => {
            appendMessageToUI(msg.content, msg.role);
        });
        
        chatScroll.scrollTop = chatScroll.scrollHeight;
        
        // Sol menüdeki görsel 'active-chat' sınıfını hemen güncelle
        document.querySelectorAll('.history-item').forEach(el => {
            if (el.getAttribute('data-id') === id) {
                el.classList.add('active-chat');
            } else {
                el.classList.remove('active-chat');
            }
        });

    } catch (error) {
        console.error("Mesaj geçmişi getirilemedi:", error);
        chatBox.innerHTML = `<div class="chat-msg msg-ai">Mesajlar yüklenirken bir hata oluştu.</div>`;
    }
}

// Yazılı Mesaj Gönderme
async function sendTextMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    // Önce ekrana basıyoruz
    appendMessageToUI(text, "user");
    userInput.value = "";

    try {
        const response = await fetch(`${API_BASE_URL}/text-chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                conversation_id: activeChatId, // conversation_id'yi backend'e gönderiyoruz
                message: text 
            })
        });
        const data = await response.json();
        appendMessageToUI(data.ai_response, "ai");
        
        // Sol menüyü yenile ki yeni açılan sohbet başlığı hemen listeye eklensin
        loadConversationsFromSupabase();
    } catch (error) {
        console.error(error);
        appendMessageToUI("Bağlantı hatası oluştu Ahmet Amca.", "ai");
    }
}

function handleKeyPress(event) {
    if (event.key === "Enter") {
        sendTextMessage();
    }
}

// Arayüze mesaj basan akıllı yardımcı fonksiyon
function appendMessageToUI(text, sender) {
    const msgDiv = document.createElement('div');
    
    // Güvenli rol eşleştirmesi: Supabase'den ne gelirse gelsin doğru sınıfa eşle
    let styleClass = 'user';
    if (sender === 'assistant' || sender === 'ai' || sender === 'system') {
        styleClass = 'ai';
    }
    
    msgDiv.className = `chat-msg msg-${styleClass}`;
    msgDiv.innerText = text;
    chatBox.appendChild(msgDiv);
    chatScroll.scrollTop = chatScroll.scrollHeight;
}

// Ses Kayıt ve Gönderme Mantığı (İleride ses için de conversation_id gönderecek şekilde güncellenmeli)
async function toggleVoice() {
    if (!isRecording) {
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) audioChunks.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
                if (audioBlob.size < 1000) {
                    appendMessageToUI("Ses kaydedilemedi.", "ai");
                    return;
                }

                const formData = new FormData();
                formData.append("file", audioBlob, "audio.webm");
                formData.append("conversation_id", activeChatId); // Sesi de o sohbete bağlamak için

                try {
                    const response = await fetch(`${API_BASE_URL}/voice-chat`, { method: "POST", body: formData });
                    const data = await response.json();
                    appendMessageToUI(data.user_transcription, "user");
                    appendMessageToUI(data.ai_response, "ai");
                    loadConversationsFromSupabase();
                } catch (err) {
                    console.error(err);
                    appendMessageToUI("Sunucuya bağlanılamadı.", "ai");
                }
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            isRecording = true;
            voiceBtn.classList.add("recording");
            btnText.innerText = "Dinliyorum...";
        } catch (err) {
            console.error(err);
            alert("Mikrofona erişim izni verilmedi.");
        }
    } else {
        isRecording = false;
        voiceBtn.classList.remove("recording");
        btnText.innerText = "Konuşmak İçin Basın";
        mediaRecorder.stop();
    }
}

// Sağlık kontrolü durum bildirimi
async function completeCheckin(mood) {
    try {
        await fetch(`${API_BASE_URL}/checkin`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mood: mood })
        });
        document.getElementById('checkinCard').innerHTML = `
            <span style="font-size: 64px;">✔️</span>
            <h2 style="color: var(--success-color); font-size: 30px; font-weight: 800;">Durumunuz Bildirildi</h2>
            <p style="font-size: 20px; color: var(--text-muted); margin-top: 8px;">Aileniz harika olduğunuzu biliyor!</p>
        `;
        appendMessageToUI(`Günlük sağlık kontrolü yapıldı: ${mood}`, "user");
        loadCheckinHistory();
    } catch (error) { alert("Bağlantı hatası."); }
}

// İlaç onay mekanizması
async function takeMed(id) {
    try {
        await fetch(`${API_BASE_URL}/medication`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ med_id: id })
        });
        const item = document.getElementById(id);
        item.classList.add('done');
        item.querySelectorAll('button').forEach(btn => btn.style.display = 'none');
        const checkMark = document.createElement('span');
        checkMark.innerText = "✓ Tamamlandı";
        checkMark.style.color = "var(--success-color)";
        checkMark.style.fontWeight = "700";
        item.appendChild(checkMark);
    } catch (error) { alert("Bağlantı hatası."); }
}

// Kamera doğrulama simülasyonu
async function simulatePhoto() {
    const formData = new FormData();
    formData.append("file", new Blob(), "photo.jpg");
    try {
        const response = await fetch(`${API_BASE_URL}/medication/recognize`, { method: "POST", body: formData });
        const data = await response.json();
        alert(`📷 ${data.recognized_med} kutusu başarıyla doğrulandı!`);
        takeMed('med2');
    } catch (error) { alert("Bağlantı hatası."); }
}