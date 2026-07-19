# 👵🤖 Yanımda AI

> Siz yanlarında olamadığınızda, biz oradayız.

## Takım İsmi

**Takım 128**

---

## Takım Rolleri

| Rol           | İsim           |
| ------------- | -------------- |
| Product Owner | Ayşenur Eşsiz |
| Scrum Master  | Aysima Ergen |
| Developer     | Mehmet Vural |
| Developer     | Ali Osman Kestane |
| Developer     | Fatih Akçay |

---

## Ürün İsmi

**Yanımda AI**

---

## Ürün Açıklaması

Yanımda AI, yalnız yaşayan yaşlı bireylerin günlük yaşamlarında onlara eşlik eden, sağlık rutinlerini takip eden ve gerektiğinde aile bireylerini bilgilendiren yapay zekâ destekli çok ajanlı bir dijital refakat sistemidir.

Sistem, yaşlı bireyle doğal sohbetler gerçekleştirerek yalnızlık hissini azaltmayı hedeflerken aynı zamanda ilaç kullanımını ve günlük durumunu takip eder. Olası risk durumlarında veya olağandışı davranışlar tespit edildiğinde aile üyelerine erken uyarı gönderir.

Yanımda AI herhangi bir tıbbi teşhis veya tedavi önerisi sunmaz. Sistem yalnızca refakat, rutin takibi ve erken uyarı mekanizması olarak çalışır.

---

## Problem Tanımı

Türkiye'de yaşlı nüfus her geçen yıl artmaktadır. Birçok yaşlı birey yalnız yaşamakta veya çocuklarından farklı şehirlerde bulunmaktadır.

Mevcut çözümler genellikle:

* Pasif acil çağrı sistemleri
* Sürekli kamera takibi gerektiren çözümler
* Sadece ilaç hatırlatma uygulamaları

şeklindedir.

Yanımda AI ise kullanıcıyla aktif iletişim kuran, onu tanıyan ve yalnızca gerektiğinde aileyi bilgilendiren daha insancıl bir yaklaşım sunmaktadır.

---

## Ürün Özellikleri

### 🗣️ Refakat Ajanı

* Günlük sesli ve yazılı sohbet
* Kullanıcının ilgi alanlarını öğrenme
* Geçmiş konuşmaları hatırlama
* Proaktif sohbet başlatabilme
* Yalnızlık hissini azaltmaya yönelik etkileşim

### 💊 Sağlık Ajanı

* İlaç saatlerini takip etme
* İlaç hatırlatmaları oluşturma
* Fotoğraf üzerinden ilaç tanıma
* Günlük sağlık durumu kontrolü
* Ruh hali ve semptom takibi

### 🚨 Eskalasyon Ajanı

* Check-in eksikliği tespiti
* Riskli ifadelerin analizi
* Olağan dışı durumların belirlenmesi
* Aile üyelerine otomatik bildirim gönderimi

### 🧠 Hafıza Katmanı

* Uzun süreli kullanıcı hafızası
* İlgi alanlarının saklanması
* Geçmiş konuşmaların analiz edilmesi
* Kişiselleştirilmiş deneyim sunulması

### 👨‍👩‍👧‍👦 Aile Paneli

* Haftalık durum özetleri
* Kullanıcı aktivite takibi
* İlaç uyumluluğu raporları
* Acil durum bildirimleri
* Trend ve analiz ekranları

---

## Hedef Kitle

### Birincil Kullanıcı

* 65 yaş üstü bireyler
* Yalnız yaşayan yaşlılar
* Temel teknoloji kullanım becerisine sahip kullanıcılar

### İkincil Kullanıcı (Müşteri)

* Ebeveynleri farklı şehirlerde yaşayan yetişkinler
* Yaşlı yakınlarının durumunu takip etmek isteyen aile bireyleri

### Kurumsal Kullanıcılar

* Belediyeler
* Huzurevleri
* Evde bakım hizmetleri
* Sağlık sigortası şirketleri

---

## Sistem Mimarisi

<img width="1187" height="770" alt="56f54d21-ce5b-422a-97e9-06dd667aa55d" src="https://github.com/user-attachments/assets/cbdbc147-6bb5-4b8c-b5b5-21fdeb335f17" />


## Teknoloji Yığını

### Frontend
- HTML5
- CSS3
- Vanilla JavaScript
- MediaRecorder API
- Web Audio API

### Backend
- FastAPI
- Python

### Yapay Zeka
- Groq
- Whisper (Speech-to-Text)
- LangGraph

### Veri Katmanı
- PostgreSQL
- Supabase

### DevOps
- GitHub
- Trello

# Product Backlog
Tüm süreç Trello ile yönetilmektedir. Scrum Board'a aşağıdaki linkten erişebilirsiniz.

https://trello.com/invite/b/6a3d3aede057f19cb52a71e2/ATTIc79c0a42c416fbe1b7ca320160a990fc6C95709F/bootcamp

## Sprint 1 - Temel MVP

* [ ] GitHub Repository Kurulumu
* [ ] FastAPI Backend Kurulumu
* [ ] Frontend Kurulumu
* [ ] LLM Entegrasyonu
* [ ] Temel Sohbet Sistemi
* [ ] Kullanıcı Profili Modeli
* [ ] Supabase Kurulumu
* [ ] Hafıza Sistemi
* [ ] Temel Chat Arayüzü
* [ ] Aile Paneli
---

## Sprint 2 - Sağlık ve Aile Paneli

* [ ] İlaç Hatırlatma Sistemi
* [ ] İlaç Tanıma Modülü
* [ ] Agent Orkestrasyonu
* [ ] Haftalık Özetler
* [ ] Kullanıcı Durum Takibi

---

## Sprint 3 - Eskalasyon ve Yayınlama

* [ ] Anomali Tespiti
* [ ] Risk Analizi
* [ ] Bildirim Sistemi
* [ ] UI/UX İyileştirmeleri
* [ ] Test Süreçleri
* [ ] Demo Videosu
* [ ] Sunum Hazırlığı

---

## Proje Hedefi

Yanımda AI ile yalnız yaşayan yaşlı bireylerin yaşam kalitesini artırmak, ailelerin içini rahatlatmak ve teknolojiyi insan odaklı bir refakat deneyimine dönüştürmek amaçlanmaktadır.

**"Siz yanlarında olamadığınızda, biz oradayız."**


# Sprint 1

## Backlog Dağıtma Mantığı

Proje başlangıç aşamasında olduğundan ekibin geçmiş deneyimleri ve ilgi alanları göz önünde bulundurularak backlog dağıtımı yapılmıştır.

## Daily Scrum Notları
Görüşmeler Whatsapp üzerinden yapılmıştır. Görseller linkteki klasörde yer almaktadır.

https://drive.google.com/drive/folders/1RujrkABXAeZNB_iCODFCfIC18ArKqjYd?usp=sharing

### Sprint Board Durumu
<img width="1515" height="692" alt="image" src="https://github.com/user-attachments/assets/af4cc7e6-3f8c-489b-a65f-4dfa3cebd6ae" />


### Ürün Durumu

#### Yaşlı Paneli Güncel Durum
<img width="1917" height="962" alt="image" src="https://github.com/user-attachments/assets/645768b1-d927-4a05-aeb7-b63847659dc0" />

#### Aile Paneli Güncel Durum
<img width="1917" height="952" alt="image" src="https://github.com/user-attachments/assets/07b02f8c-e913-4656-9a2b-711c7c522cad" />

#### Sprint Review

Bu sprintte projenin temel MVP'si üretilmiştir.
- Kullanıcı Girişi ve Aile Girişi Ekranları Arayüzleri
- Yaşlılar için Yüz Tanıma ile Giriş
- Chat Arayüzü Oluşturulması
- Hem Yazılı Hem Sesle Sohbet Edebilme
- Veritabanı Kurulumu
- Backend Kurulumu
- LLM Entegrasyonu
- Sohbet Geçmişinin Tutulması
- Günlük Kontrol (Check-In) Yapılması
- Aile Paneli Frontend Kurulumu
- Aile Paneli Authentication
- Aile Paneli LLM Kurulumu (Yapay Zeka Özeti)
Görevleri yerine getirilmiştir. Proje şuan ayağa kaldırılabilir durumdadır. Projenin güncel durumu tüm takım tarafından değerlendirilmiştir.

### Sprint Retrospective

İlk sprint boyunca ekip arası iletişim sağlanmıştır. Proje ekibinde teknik altyapısı güçlü olmayan kişilerin öğrenme ve adaptasyon süreci olmuştur. Ayrıca ilk sprintin kapsamı geniş olduğundan görevler bazen beklenenden uzun sürede tamamlanmış, belirli sorunlarla karşılaşılmış ve bunlar ekip yardımlaşmasıyla çözüme kavuşturulmuştur. Karşılaşılan zorluklar göz önünde bulundurulduğunda ilk sprint oldukça başarılı bir şekilde bitmiştir. Bu süreç için belirlenen hedeflerin hepsi tamamlanmıştır. Bir sonraki sprintte hedef, geliştirme sürecinin daha verimli ve daha koordine bir şekilde ilerlemesini sağlamaktır. 

# Sprint 2

## Backlog Dağıtma Mantığı

Bu sprintte backlog dağıtımı takım müsaitliğine göre planlanmıştır.

## Daily Scrum Notları

Bu süreçte bir kere meet üzerinden ekip üyesine projenin güncel hali gösterilmiştir. Geri kalan tüm görüşmeler Whatsapp üzerinden yapılmıştır. Görseller aşağıdaki linkte yer almaktadır.

https://drive.google.com/drive/folders/1Cz2Vt9SwE865E1GU4VaxOa3o5MgYwCnc?usp=sharing


### Sprint Board Durumu

<img width="1502" height="727" alt="image" src="https://github.com/user-attachments/assets/612c3567-de60-4d1e-a529-d74390f70dd5" />

### Ürün Durumu

#### Yaşlı Paneli İlaç Sekmesi

<img width="1917" height="1017" alt="image" src="https://github.com/user-attachments/assets/f485591c-17ca-48dc-828a-6e942d9db658" />

#### Aile Paneli İlaç Sekmesi

<img width="1912" height="1012" alt="image" src="https://github.com/user-attachments/assets/4b3d62fc-ad6c-496b-bc0b-35f9a24bf06d" />

#### Sprint Review

Bu sprintte agent yapısı oluşturulmuştur. Ayrıca İlaç Sekmesi çalışır hale getirilmiştir.

- İlaç Hatırlatma Sistemi
- İlaç Tanıma Modülü
- Agent Orchestrasyonu

Görevleri yerine getirilmiştir. Bu sprint için yapılması planlanan fakat tamamamlanamayan iki görev 3. sprinte aktarılmıştır.

### Sprint Retrospective

Bu sprintte proje, planlanan ilerleme hızına tam olarak ulaşamamıştır. Buna rağmen 2. sprint için planlanan görevlerin çoğunluğu tamamlanmıştır. Tamamlanamayan 2 task bir sonraki sprinte aktarılmıştır. Sonraki sprint bootcamp sürecinin son sprinti olup projenin nihayete erdirilmesi kararlaştırılmıştır.


