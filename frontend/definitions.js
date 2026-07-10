/**
 * İlaç tanımlama modülü — medications + medication_schedules CRUD
 * Kullanım: MedicationDefinitions.init({ mode: "kiosk" | "family" })
 */
window.MedicationDefinitions = (() => {
    const DAY_LABELS = [
        { value: 1, label: "Pzt" },
        { value: 2, label: "Sal" },
        { value: 3, label: "Çar" },
        { value: 4, label: "Per" },
        { value: 5, label: "Cum" },
        { value: 6, label: "Cmt" },
        { value: 7, label: "Paz" },
    ];

    const state = {
        apiBaseUrl: "http://127.0.0.1:8000/api",
        elderId: null,
        userId: null,
        userName: "",
        mode: "kiosk",
        todayOnly: true,
        medications: [],
    };

    function getEls(mode) {
        if (mode === "family") {
            return {
                formRoot: document.getElementById("familyMedFormRoot"),
                listRoot: document.getElementById("familyMedListRoot"),
                toolbar: null,
            };
        }
        return {
            formRoot: document.getElementById("medAddFormRoot"),
            listRoot: document.getElementById("medicationList"),
            toolbar: document.getElementById("medicationToolbar"),
        };
    }

    function formatTimeLabel(timeValue) {
        const hour = parseInt(String(timeValue).slice(0, 2), 10);
        const part = hour < 12 ? "Sabah" : "Akşam";
        return `${part} • ${String(timeValue).slice(0, 5)}`;
    }

    function formatDays(days) {
        if (!days || days.length === 7) return "Her gün";
        return days
            .map((day) => DAY_LABELS.find((item) => item.value === day)?.label || day)
            .join(", ");
    }

    function readSelectedDays(formRoot) {
        return Array.from(formRoot.querySelectorAll(".med-def-day input:checked")).map((input) =>
            parseInt(input.value, 10)
        );
    }

    function renderForm(formRoot, options = {}) {
        if (!formRoot) return;
        if (formRoot.dataset.rendered === "true" && !options.force) return;

        const formTitle =
            state.mode === "kiosk" ? "➕ Yeni İlaç Ekle" : "➕ Yeni İlaç Tanımla";
        const showCancel = state.mode === "kiosk";

        formRoot.innerHTML = `
            <div class="med-def-panel">
                <h3>${formTitle}</h3>
                <div class="med-def-grid">
                    <input type="text" id="medDefName" placeholder="İlaç adı (ör. Tansiyon İlacı)" />
                    <input type="text" id="medDefDosage" placeholder="Doz (ör. 1 tablet)" />
                    <select id="medDefForm">
                        <option value="tablet">Tablet</option>
                        <option value="kapsül">Kapsül</option>
                        <option value="şurup">Şurup</option>
                        <option value="damla">Damla</option>
                    </select>
                    <input type="time" id="medDefTime" value="09:00" />
                    <textarea id="medDefNotes" placeholder="Not (opsiyonel)"></textarea>
                </div>
                <p style="font-size:16px; color:#64748B; margin-bottom:8px;">Hangi günler?</p>
                <div class="med-def-days">
                    ${DAY_LABELS.map(
                        (day) => `
                        <label class="med-def-day">
                            <input type="checkbox" value="${day.value}" checked />
                            ${day.label}
                        </label>`
                    ).join("")}
                </div>
                <div class="med-def-actions">
                    <button type="button" class="btn btn-success" id="medDefSaveBtn">İlacı Kaydet</button>
                    ${showCancel ? '<button type="button" class="btn btn-neutral" id="medDefCancelBtn">İptal</button>' : ""}
                </div>
            </div>
        `;

        formRoot.querySelector("#medDefSaveBtn").addEventListener("click", () => createMedication(formRoot));
        const cancelBtn = formRoot.querySelector("#medDefCancelBtn");
        if (cancelBtn) {
            cancelBtn.addEventListener("click", closeAddModal);
        }
        formRoot.dataset.rendered = "true";
    }

    function renderKioskToolbar(toolbar) {
        if (!toolbar) return;
        toolbar.innerHTML = `
            <button type="button" class="btn btn-success" style="width:100%; font-size:18px; padding:14px; margin-bottom:16px;"
                onclick="MedicationDefinitions.openAddModal()">
                ➕ İlaç Ekle
            </button>
        `;
    }

    function openAddModal() {
        const modal = document.getElementById("medAddModal");
        const formRoot = document.getElementById("medAddFormRoot");
        if (formRoot) {
            formRoot.dataset.rendered = "false";
            renderForm(formRoot, { force: true });
        }
        if (modal) {
            modal.classList.add("active");
        }
    }

    function closeAddModal() {
        const modal = document.getElementById("medAddModal");
        if (modal) {
            modal.classList.remove("active");
        }
    }

    async function syncElder() {
        const response = await fetch(`${state.apiBaseUrl}/medications/sync-elder`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: state.userId,
                user_name: state.userName,
            }),
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Yaşlı profili eşleştirilemedi.");
        }

        state.elderId = data.elder.id;
        localStorage.setItem("elder_id", state.elderId);
        return data.elder;
    }

    async function ensureElder() {
        if (state.elderId) return state.elderId;

        const storedElderId = localStorage.getItem("elder_id");
        if (storedElderId) {
            state.elderId = storedElderId;
            return state.elderId;
        }

        await syncElder();
        return state.elderId;
    }

    async function loadMedications() {
        await ensureElder();
        const query = state.todayOnly ? "?today_only=true" : "";
        const response = await fetch(`${state.apiBaseUrl}/medications/elder/${state.elderId}${query}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "İlaç listesi alınamadı.");
        }

        state.medications = data.medications || [];
        return state.medications;
    }

    function emptyListMessage() {
        if (state.mode === "family") {
            return "Henüz tanımlı ilaç yok. Yukarıdaki formdan ekleyebilirsiniz.";
        }
        return "Bugün için planlanmış ilaç yok. İlaç Ekle butonuna basarak yeni ilaç ekleyebilirsiniz.";
    }

    function renderList(listRoot) {
        if (!listRoot) return;

        if (state.medications.length === 0) {
            listRoot.innerHTML = `<p class="med-def-empty">${emptyListMessage()}</p>`;
            return;
        }

        listRoot.innerHTML = state.medications
            .map((med) => {
                const schedules = med.medication_schedules || [];
                const scheduleHtml = schedules.length
                    ? schedules
                          .map(
                              (schedule) => `
                        <div class="med-def-schedule-item">
                            <span>${formatTimeLabel(schedule.time_of_day)} • ${formatDays(schedule.days_of_week)}</span>
                            ${
                                state.mode === "family"
                                    ? `<button type="button" class="med-def-danger" onclick="MedicationDefinitions.removeSchedule('${schedule.id}')">Saati Sil</button>`
                                    : ""
                            }
                        </div>`
                          )
                          .join("")
                    : '<p class="med-def-empty">Saat tanımlı değil.</p>';

                const kioskActions = schedules
                    .map(
                        (schedule) => `
                            <button type="button" class="btn btn-success" style="width:auto; padding:10px 16px; font-size:16px;"
                                onclick="MedicationDefinitions.markTaken('${med.id}', '${schedule.id}', '${med.name.replace(/'/g, "\\'")}')">
                                ${formatTimeLabel(schedule.time_of_day)} — İçtim
                            </button>
                            <button type="button" class="btn btn-neutral" style="width:auto; padding:10px 16px; font-size:16px;"
                                onclick="MedicationRecognition.open('${med.id}', '${med.name.replace(/'/g, "\\'")}', '${schedule.id}')">
                                ${formatTimeLabel(schedule.time_of_day)} — Kamerayla Doğrula
                            </button>`
                    )
                    .join("");

                const familyActions =
                    state.mode === "family"
                        ? `<button type="button" class="med-def-danger" onclick="MedicationDefinitions.deactivateMedication('${med.id}')">Pasifleştir</button>`
                        : "";

                const kioskActionRow =
                    state.mode === "kiosk"
                        ? `<div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px;">${kioskActions}</div>`
                        : "";

                return `
                    <div class="med-def-card" id="med-card-${med.id}" data-med-name="${med.name}">
                        <div class="med-def-card-head">
                            <div>
                                <div class="med-def-card-title">💊 ${med.name}</div>
                                <div class="med-def-meta">${med.dosage || "Doz belirtilmedi"}${med.form ? ` • ${med.form}` : ""}</div>
                                ${med.notes ? `<div class="med-def-meta">${med.notes}</div>` : ""}
                            </div>
                            ${familyActions}
                        </div>
                        <div class="med-def-schedule-list">${scheduleHtml}</div>
                        ${kioskActionRow}
                    </div>
                `;
            })
            .join("");
    }

    async function refresh() {
        const { formRoot, listRoot, toolbar } = getEls(state.mode);

        if (state.mode === "kiosk") {
            renderKioskToolbar(toolbar);
        } else {
            renderForm(formRoot);
        }

        try {
            await loadMedications();
            renderList(listRoot);
        } catch (error) {
            console.error(error);
            if (listRoot) {
                listRoot.innerHTML = `<p class="med-def-empty">İlaç listesi yüklenemedi: ${error.message}</p>`;
            }
        }
    }

    async function createMedication(formRoot) {
        const name = formRoot.querySelector("#medDefName")?.value.trim();
        const dosage = formRoot.querySelector("#medDefDosage")?.value.trim();
        const form = formRoot.querySelector("#medDefForm")?.value;
        const timeValue = formRoot.querySelector("#medDefTime")?.value;
        const notes = formRoot.querySelector("#medDefNotes")?.value.trim();
        const days = readSelectedDays(formRoot);

        if (!name || !timeValue) {
            alert("İlaç adı ve saat zorunludur.");
            return;
        }
        if (days.length === 0) {
            alert("En az bir gün seçmelisiniz.");
            return;
        }

        try {
            await ensureElder();
            const response = await fetch(`${state.apiBaseUrl}/medications`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    elder_id: state.elderId,
                    name,
                    dosage: dosage || null,
                    form,
                    notes: notes || null,
                    schedules: [{ time_of_day: timeValue, days_of_week: days }],
                }),
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || "İlaç kaydedilemedi.");
            }

            formRoot.querySelector("#medDefName").value = "";
            formRoot.querySelector("#medDefDosage").value = "";
            formRoot.querySelector("#medDefNotes").value = "";
            if (state.mode === "kiosk") {
                closeAddModal();
            }
            await refresh();
            alert("İlaç başarıyla tanımlandı.");
        } catch (error) {
            alert(error.message || "İlaç kaydedilirken hata oluştu.");
        }
    }

    async function deactivateMedication(medicationId) {
        if (!confirm("Bu ilacı pasifleştirmek istediğinize emin misiniz?")) return;

        try {
            const response = await fetch(`${state.apiBaseUrl}/medications/${medicationId}`, {
                method: "DELETE",
            });
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || "İlaç pasifleştirilemedi.");
            }
            await refresh();
        } catch (error) {
            alert(error.message);
        }
    }

    async function removeSchedule(scheduleId) {
        if (!confirm("Bu ilaç saatini silmek istiyor musunuz?")) return;

        try {
            const response = await fetch(`${state.apiBaseUrl}/medications/schedules/${scheduleId}`, {
                method: "DELETE",
            });
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || "Saat silinemedi.");
            }
            await refresh();
        } catch (error) {
            alert(error.message);
        }
    }

    async function markTaken(medicationId, scheduleId, medicationName, confirmedMethod = "manual") {
        try {
            await ensureElder();
            const formData = new FormData();
            formData.append("medication_id", medicationId);
            formData.append("status", "taken");
            formData.append("confirmed_method", confirmedMethod);
            if (scheduleId) {
                formData.append("schedule_id", scheduleId);
            }

            const response = await fetch(`${state.apiBaseUrl}/medication/log`, {
                method: "POST",
                body: formData,
            });

            if (!response.ok) {
                throw new Error("İlaç kaydı oluşturulamadı.");
            }

            const card = document.getElementById(`med-card-${medicationId}`);
            if (card) {
                card.style.opacity = "0.65";
                card.insertAdjacentHTML(
                    "beforeend",
                    `<p style="color:#047857; font-weight:700; margin-top:10px;">✓ ${medicationName} alındı olarak kaydedildi.</p>`
                );
            }

            if (typeof appendMessageToUI === "function") {
                appendMessageToUI(`${medicationName} ilacı alındı olarak kaydedildi.`, "system");
            }
        } catch (error) {
            alert(error.message || "Bağlantı hatası.");
        }
    }

    function resolveUserContext(mode) {
        if (mode === "family") {
            return {
                userId: localStorage.getItem("elderly_id"),
                userName: localStorage.getItem("elderly_name") || "Yakınınız",
            };
        }

        const userId =
            localStorage.getItem("user_id") ||
            localStorage.getItem("elder_profile_id_fallback") ||
            `guest-${Date.now()}`;
        const userName =
            localStorage.getItem("user_name") ||
            localStorage.getItem("elderly_name") ||
            "Ahmet Amca";

        return { userId, userName };
    }

    async function init(options = {}) {
        state.mode = options.mode || "kiosk";
        state.todayOnly = options.todayOnly ?? state.mode === "kiosk";
        state.apiBaseUrl = options.apiBaseUrl || state.apiBaseUrl;

        const ctx = resolveUserContext(state.mode);
        state.userId = options.userId || ctx.userId;
        state.userName = options.userName || ctx.userName;
        state.elderId = options.elderId || localStorage.getItem("elder_id") || null;

        try {
            await ensureElder();
        } catch (error) {
            console.error("Yaşlı profili eşleştirilemedi:", error);
        }

        await refresh();
    }

    return {
        init,
        refresh,
        markTaken,
        deactivateMedication,
        removeSchedule,
        openAddModal,
        closeAddModal,
        getElderId: () => state.elderId,
    };
})();
