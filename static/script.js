/**
 * rpi-youtube-stream - Frontend Controller
 * ========================================
 * Panel de control para transmisiones en vivo a YouTube.
 *
 * Modulos:
 *   - Status polling: actualizacion periodica del estado
 *   - UI update: sincronizacion de elementos visuales
 *   - Auth redirect: lleva a /auth (Device Flow) cuando no hay sesion
 *   - Logs panel: visualizacion de logs del sistema
 *
 * Autor: Andres Mercado
 */

// ==============================================================================
// SECCION 0: CONSTANTES
// ==============================================================================

const POLL_INTERVAL = 3000;           // ms - intervalo de polling de estado
const LOG_POLL_INTERVAL = 2000;        // ms - intervalo de polling de logs
const AUTH_PAGE_PATH = "/auth";
const DEFAULT_TITLE = "Transmisión en vivo";

const STATUS_LABELS = {
    idle: "Sin transmision",
    preparing: "Preparando...",
    starting: "Iniciando...",
    streaming: "EN VIVO",
    stopping: "Deteniendo...",
    error: "Error",
};

// ==============================================================================
// SECCION 1: REFERENCIAS DOM
// ==============================================================================

const dom = {
    // Header
    statusPill: document.getElementById("status-pill"),
    statusText: document.getElementById("status-text"),

    // Controles principales
    btnStart: document.getElementById("btn-start"),
    btnStop: document.getElementById("btn-stop"),
    titleInput: document.getElementById("title-input"),
    privacySelect: document.getElementById("privacy-select"),

    // Warnings
    authWarning: document.getElementById("auth-warning"),
    authWarningText: document.getElementById("auth-warning-text"),
    micWarning: document.getElementById("mic-warning"),
    micWarningText: document.getElementById("mic-warning-text"),

    // Share
    shareCard: document.getElementById("share-card"),
    shareUrlWatch: document.getElementById("share-url-watch"),
    shareUrlDirect: document.getElementById("share-url-direct"),
    shareLink: document.getElementById("share-link"),
    btnCopyWatch: document.getElementById("btn-copy-watch"),
    copyTextWatch: document.getElementById("copy-text-watch"),
    btnCopyDirect: document.getElementById("btn-copy-direct"),
    copyTextDirect: document.getElementById("copy-text-direct"),

    // Error
    errorCard: document.getElementById("error-card"),
    errorText: document.getElementById("error-text"),

    // Preparing
    preparingCard: document.getElementById("preparing-card"),
    preparingTitle: document.getElementById("preparing-title"),
    preparingSub: document.getElementById("preparing-sub"),
    stepBroadcast: document.querySelector("#step-broadcast .step-icon"),
    stepYoutube: document.querySelector("#step-youtube .step-icon"),
    stepStream: document.querySelector("#step-stream .step-icon"),

    // Logs
    btnLogsToggle: document.getElementById("btn-logs-toggle"),
    btnClearLogs: document.getElementById("btn-clear-logs"),
    logsPanel: document.getElementById("logs-panel"),
    logsContent: document.getElementById("logs-content"),
    logsScroll: document.querySelector(".logs-scroll"),
    logsCount: document.getElementById("logs-count"),

    // Emergency
    btnEmergency: document.getElementById("btn-emergency"),
    btnAuth: document.getElementById("btn-auth"),

    // Visitors
    visitorsCard: document.getElementById("visitors-card"),
    visitorsList: document.getElementById("visitors-list"),
    visitorsCount: document.getElementById("visitors-count"),
    btnClearVisitors: document.getElementById("btn-clear-visitors"),

    // Conexion
    connIndicator: document.getElementById("conn-indicator"),
    connIcon: document.getElementById("conn-icon"),
    connLabel: document.getElementById("conn-label"),

    // Opciones avanzadas
    btnAdvancedToggle: document.getElementById("btn-advanced-toggle"),
    advancedPanel: document.getElementById("advanced-panel"),
    toggleNoMic: document.getElementById("toggle-no-mic"),
    wifiCurrent: document.getElementById("wifi-current"),
    btnWifiScan: document.getElementById("btn-wifi-scan"),
    wifiSsid: document.getElementById("wifi-ssid"),
    wifiPassword: document.getElementById("wifi-password"),
    btnWifiConnect: document.getElementById("btn-wifi-connect"),
    wifiMessage: document.getElementById("wifi-message"),
    channelName: document.getElementById("channel-name"),
    btnUnlink: document.getElementById("btn-unlink"),
};

// Variable global para broadcast_id actual
let currentBroadcastId = null;

// ==============================================================================
// SECCION 2: ESTADO
// ==============================================================================

let currentState = "idle";
let logsVisible = false;
let logsInterval = null;
let visitorsInterval = null;
let advInitialized = false;
let channelFetched = false;

// ==============================================================================
// SECCION 3: AVISO DE VINCULACION
// ==============================================================================
// Nota: ya NO redirige automaticamente a /auth (eso causaba un bucle al pulsar
// "Volver al panel principal"). Solo muestra el aviso con el boton para vincular.

function showAuthWarning() {
    dom.authWarning.classList.remove("hidden");
    dom.authWarningText.textContent = "YouTube no vinculado";
}

function hideAuthWarning() {
    dom.authWarning.classList.add("hidden");
}

// ==============================================================================
// SECCION 4: UI UPDATE
// ==============================================================================

function updateUI(data) {
    const state = data.state || "idle";
    const authorized = data.authorized !== false;
    const micConnected = data.microphone_connected !== false;
    const allowNoMic = data.allow_no_mic === true;
    currentState = state;

    // Status pill
    dom.statusPill.className = "status-pill " + state;
    dom.statusText.textContent = STATUS_LABELS[state] || state;

    // Botones principales
    const canStart = state === "idle" || state === "error";
    const canStop = state === "streaming" || state === "starting";

    dom.btnStart.classList.toggle("hidden", !canStart);
    dom.btnStop.classList.toggle("hidden", !canStop);
    dom.btnStart.disabled = !canStart || !authorized || !(micConnected || allowNoMic);
    dom.btnStop.disabled = !canStop;

    // Controles de titulo/privacidad
    dom.titleInput.disabled = !canStart;
    dom.privacySelect.disabled = !canStart;

    // Card main visibility
    const cardMain = document.querySelector(".card-main");
    cardMain.classList.toggle("hidden", state === "preparing" || state === "starting");

    // Preparing card
    if (state === "preparing" || state === "starting") {
        dom.preparingCard.classList.remove("hidden");
        updatePreparingSteps(state);
    } else {
        dom.preparingCard.classList.add("hidden");
    }

    // Auth warning
    if (!authorized) {
        showAuthWarning();
        dom.btnStart.disabled = true;
        channelFetched = false;
        dom.channelName.textContent = "Canal vinculado: (sin vincular)";
    } else {
        hideAuthWarning();
        if (!channelFetched) {
            channelFetched = true;
            fetchChannel();
        }
    }

    // Microphone warning (se omite si "transmitir sin microfono" esta activo)
    if (!micConnected && !allowNoMic) {
        dom.micWarning.classList.remove("hidden");
        dom.micWarningText.textContent = data.microphone_message || "Por favor, conecta el microfono.";
        dom.btnStart.disabled = true;
    } else {
        dom.micWarning.classList.add("hidden");
    }

    // Indicador de conexion (cable / wifi / sin internet)
    if (data.connection) {
        updateConnIndicator(data.connection);
    }

    // Reflejar el ajuste "sin microfono" en el toggle (solo la primera vez)
    if (data.allow_no_mic !== undefined && !advInitialized) {
        dom.toggleNoMic.checked = allowNoMic;
        advInitialized = true;
    }

    // Share URL - generar link intermedio
    if (data.share_url) {
        dom.shareCard.classList.remove("hidden");
        const videoIdMatch = data.share_url.match(/(?:youtu\.be\/|v=)([a-zA-Z0-9_-]+)/);
        const videoId = videoIdMatch ? videoIdMatch[1] : null;

        if (videoId) {
            currentBroadcastId = videoId;
            const watchUrl = `${window.location.origin}/watch/${videoId}`;
            dom.shareUrlWatch.value = watchUrl;
            dom.shareUrlDirect.value = data.share_url;
            dom.shareLink.href = data.share_url;
        } else {
            dom.shareUrlWatch.value = data.share_url;
            dom.shareUrlDirect.value = data.share_url;
            dom.shareLink.href = data.share_url;
        }

        if (videoId) {
            dom.visitorsCard.classList.remove("hidden");
            if (!visitorsInterval) {
                fetchVisitors();
                visitorsInterval = setInterval(fetchVisitors, 5000);
            }
        }
    } else {
        dom.shareCard.classList.add("hidden");
        dom.visitorsCard.classList.add("hidden");
        currentBroadcastId = null;
        if (visitorsInterval) {
            clearInterval(visitorsInterval);
            visitorsInterval = null;
        }
    }

    // Error
    if (data.error && state === "error") {
        dom.errorCard.classList.remove("hidden");
        dom.errorText.textContent = data.error;
    } else {
        dom.errorCard.classList.add("hidden");
    }

    // Sync titulo desde servidor
    if (data.title && state !== "idle") {
        dom.titleInput.value = data.title;
    }
}

function updatePreparingSteps(state) {
    if (state === "preparing") {
        dom.stepBroadcast.className = "step-icon active";
        dom.stepYoutube.className = "step-icon";
        dom.stepStream.className = "step-icon";
        dom.preparingTitle.textContent = "Preparando transmision...";
        dom.preparingSub.textContent = "Creando broadcast en YouTube";
    } else if (state === "starting") {
        dom.stepBroadcast.className = "step-icon done";
        dom.stepYoutube.className = "step-icon done";
        dom.stepStream.className = "step-icon active";
        dom.preparingTitle.textContent = "Casi listo...";
        dom.preparingSub.textContent = "Iniciando pipeline de video";
    }
}

function advancePreparingFromLogs(logs) {
    if (currentState !== "preparing") return;

    const text = logs.join("\n");

    if (text.includes("Esperando a YouTube")) {
        dom.stepBroadcast.className = "step-icon done";
        dom.stepYoutube.className = "step-icon active";
        dom.preparingSub.textContent = "Esperando a YouTube (~10s)";
    } else if (text.includes("Broadcast creado")) {
        dom.stepBroadcast.className = "step-icon active";
        dom.preparingSub.textContent = "Broadcast creado, conectando...";
    }
}

// ==============================================================================
// SECCION 5: API CALLS
// ==============================================================================

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        updateUI(data);
    } catch {
        // Network error, mantener estado actual
    }
}

async function fetchLogs() {
    try {
        const res = await fetch("/api/logs");
        const data = await res.json();
        const logs = data.logs || [];

        const isNearBottom = dom.logsScroll && (
            dom.logsScroll.scrollTop + dom.logsScroll.clientHeight >=
            dom.logsScroll.scrollHeight - 50
        );

        dom.logsContent.textContent = logs.join("\n") || "Sin logs aun...";
        dom.logsCount.textContent = `${logs.length} lineas`;

        if (isNearBottom && dom.logsScroll) {
            dom.logsScroll.scrollTop = dom.logsScroll.scrollHeight;
        }

        advancePreparingFromLogs(logs);
    } catch {
        // ignore
    }
}

// ==============================================================================
// SECCION 6: EVENT HANDLERS
// ==============================================================================

// ---- Start ----
dom.btnStart.addEventListener("click", async () => {
    dom.btnStart.disabled = true;
    dom.titleInput.disabled = true;
    dom.privacySelect.disabled = true;
    updateUI({ state: "preparing", authorized: true });

    try {
        const res = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                title: dom.titleInput.value || DEFAULT_TITLE,
                privacy: dom.privacySelect.value,
            }),
        });
        const data = await res.json();

        if (!res.ok) {
            if (res.status === 401 || data.auth_required) {
                updateUI({ state: "idle", authorized: false });
                return;
            }

            if (data.microphone_required) {
                updateUI({
                    state: "idle",
                    error: null,
                    authorized: true,
                    microphone_connected: false,
                    microphone_message: data.error,
                });
                return;
            }

            updateUI({ state: "error", error: data.error, authorized: true });
        }
    } catch (err) {
        updateUI({ state: "error", error: "Error de conexion: " + err.message, authorized: true });
    }
});

// ---- Stop ----
dom.btnStop.addEventListener("click", async () => {
    if (!confirm("⚠️ ¿Estás seguro que deseas TERMINAR la transmisión? Esto cortará el video en vivo para todos los espectadores.")) {
        return;
    }

    dom.btnStop.disabled = true;
    dom.statusPill.className = "status-pill stopping";
    dom.statusText.textContent = "Deteniendo...";

    // Mostrar resumen de visitantes antes de limpiar
    if (currentBroadcastId) {
        try {
            const res = await fetch(`/api/visitors?broadcast_id=${currentBroadcastId}`);
            const data = await res.json();
            const visitors = data.visitors || [];

            if (visitors.length > 0) {
                const names = visitors.map(v => v.nombre || "Anónimo").join(", ");
                alert(`¡Transmisión finalizada!\n\nAsistieron ${visitors.length} personas:\n${names}`);
            } else {
                alert("Transmisión finalizada. No hubo espectadores registrados a través de la app.");
            }
        } catch {
            // ignore
        }
    }

    try {
        const res = await fetch("/api/stop", { method: "POST" });
        const data = await res.json();

        if (!res.ok) {
            updateUI({ state: "error", error: data.error, authorized: true });
            return;
        }

        updateUI({ state: data.state, authorized: true });
    } catch (err) {
        updateUI({ state: "error", error: "Error de conexion: " + err.message, authorized: true });
    }
});

// ---- Emergency ----
dom.btnEmergency.addEventListener("click", async () => {
    if (!confirm("Esto matara todos los procesos de streaming y reiniciara el estado. Continuar?")) {
        return;
    }

    dom.btnEmergency.disabled = true;
    dom.statusPill.className = "status-pill stopping";
    dom.statusText.textContent = "Reiniciando...";

    try {
        const res = await fetch("/api/emergency", { method: "POST" });
        const data = await res.json();
        updateUI(data);
    } catch (err) {
        updateUI({ state: "error", error: "Error en reinicio: " + err.message, authorized: true });
    }

    dom.btnEmergency.disabled = false;
});

// ---- Auth ----
dom.btnAuth.addEventListener("click", () => {
    window.location.href = AUTH_PAGE_PATH;
});

// ---- Copy (link con registro) ----
dom.btnCopyWatch.addEventListener("click", () => {
    navigator.clipboard.writeText(dom.shareUrlWatch.value).then(() => {
        dom.copyTextWatch.textContent = "Copiado!";
        setTimeout(() => { dom.copyTextWatch.textContent = "Copiar"; }, 2000);
    }).catch(() => {
        dom.shareUrlWatch.select();
        document.execCommand("copy");
        dom.copyTextWatch.textContent = "Copiado!";
        setTimeout(() => { dom.copyTextWatch.textContent = "Copiar"; }, 2000);
    });
});

// ---- Copy (link directo) ----
dom.btnCopyDirect.addEventListener("click", () => {
    navigator.clipboard.writeText(dom.shareUrlDirect.value).then(() => {
        dom.copyTextDirect.textContent = "Copiado!";
        setTimeout(() => { dom.copyTextDirect.textContent = "Copiar"; }, 2000);
    }).catch(() => {
        dom.shareUrlDirect.select();
        document.execCommand("copy");
        dom.copyTextDirect.textContent = "Copiado!";
        setTimeout(() => { dom.copyTextDirect.textContent = "Copiar"; }, 2000);
    });
});

// ---- Logs panel ----
dom.btnLogsToggle.addEventListener("click", () => {
    logsVisible = !logsVisible;
    dom.logsPanel.classList.toggle("hidden", !logsVisible);
    dom.btnLogsToggle.classList.toggle("open", logsVisible);

    if (logsVisible) {
        fetchLogs();
        logsInterval = setInterval(fetchLogs, LOG_POLL_INTERVAL);
    } else {
        clearInterval(logsInterval);
        logsInterval = null;
    }
});

dom.btnClearLogs.addEventListener("click", async () => {
    if (!confirm("¿Borrar todos los logs?")) return;

    try {
        await fetch("/api/logs/clear", { method: "POST" });
        dom.logsContent.textContent = "";
        dom.logsCount.textContent = "0 lineas";
    } catch {}
});

// ---- Visitors ----
async function fetchVisitors() {
    if (!currentBroadcastId) return;

    try {
        const res = await fetch(`/api/visitors?broadcast_id=${currentBroadcastId}`);
        const data = await res.json();
        renderVisitors(data.visitors || []);
    } catch {
        // ignore
    }
}

function renderVisitors(visitors) {
    dom.visitorsCount.textContent = visitors.length;

    if (visitors.length === 0) {
        dom.visitorsList.innerHTML = '<p class="visitors-empty">Aún no hay visitantes</p>';
        return;
    }

    const html = visitors.map(v => {
        const timeStr = v.timestamp ? v.timestamp.split(' ')[1].substring(0, 5) : "";
        const nombre = v.nombre || "Anónimo";
        const location = v.city && v.city !== "?" ? `${v.city}, ${v.country}` : "Ubicación oculta";

        return `
        <div class="visitor-item">
            <div class="visitor-info">
                <span class="visitor-name">${nombre}</span>
                <span class="visitor-location">${location}</span>
            </div>
            <span class="visitor-time">${timeStr}</span>
        </div>
        `;
    }).join("");

    dom.visitorsList.innerHTML = html;
}

dom.btnClearVisitors.addEventListener("click", async () => {
    if (!confirm("¿Borrar el registro de visitantes?")) return;

    try {
        await fetch("/api/visitors/clear", { method: "POST" });
        dom.visitorsList.innerHTML = '<p class="visitors-empty">Registro limpiado</p>';
        dom.visitorsCount.textContent = "0";
    } catch {}
});

// ==============================================================================
// SECCION 6B: CONEXION + OPCIONES AVANZADAS
// ==============================================================================

const CONN_ICONS = {
    ethernet: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="9" width="18" height="11" rx="2"></rect><path d="M7 9V6h10v3"></path><path d="M9 20v-3M12 20v-3M15 20v-3"></path></svg>',
    wifi: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.55a11 11 0 0114.08 0"></path><path d="M1.42 9a16 16 0 0121.16 0"></path><path d="M8.53 16.11a6 6 0 016.95 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line></svg>',
    none: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="1" y1="1" x2="23" y2="23"></line><path d="M16.72 11.06A10.94 10.94 0 0119 12.55"></path><path d="M5 12.55a10.94 10.94 0 015.17-2.39"></path><path d="M10.71 5.05A16 16 0 0122.58 9"></path><path d="M1.42 9a15.91 15.91 0 014.7-2.88"></path><path d="M8.53 16.11a6 6 0 016.95 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line></svg>',
};

function updateConnIndicator(conn) {
    const type = conn.type || "none";
    dom.connIcon.innerHTML = CONN_ICONS[type] || CONN_ICONS.none;
    dom.connIndicator.className = "conn-indicator conn-" + type;

    if (type === "ethernet") {
        dom.connLabel.textContent = "Cable";
        dom.connIndicator.title = "Conectado por cable";
        dom.wifiCurrent.textContent = "Conexión actual: cable (Ethernet)";
    } else if (type === "wifi") {
        dom.connLabel.textContent = "WiFi";
        dom.connIndicator.title = conn.ssid ? `WiFi: ${conn.ssid}` : "Conectado por WiFi";
        dom.wifiCurrent.textContent = conn.ssid
            ? `Conexión actual: WiFi (${conn.ssid})`
            : "Conexión actual: WiFi";
    } else {
        dom.connLabel.textContent = "Sin internet";
        dom.connIndicator.title = "Sin conexión a internet";
        dom.wifiCurrent.textContent = "Conexión actual: sin internet";
    }
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, c => (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
}

function showWifiMessage(text, ok) {
    dom.wifiMessage.textContent = text;
    dom.wifiMessage.classList.remove("hidden");
    dom.wifiMessage.classList.toggle("adv-msg-ok", ok);
    dom.wifiMessage.classList.toggle("adv-msg-err", !ok);
}

function hideWifiMessage() {
    dom.wifiMessage.classList.add("hidden");
}

// ---- Mostrar/ocultar panel avanzado ----
dom.btnAdvancedToggle.addEventListener("click", () => {
    const isHidden = dom.advancedPanel.classList.toggle("hidden");
    dom.btnAdvancedToggle.classList.toggle("open", !isHidden);
});

// ---- Toggle "transmitir sin microfono" ----
dom.toggleNoMic.addEventListener("change", async () => {
    const value = dom.toggleNoMic.checked;
    dom.toggleNoMic.disabled = true;
    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ allow_no_mic: value }),
        });
        if (!res.ok) throw new Error("settings");
        fetchStatus();
    } catch {
        dom.toggleNoMic.checked = !value; // revertir si falla
    } finally {
        dom.toggleNoMic.disabled = false;
    }
});

// ---- WiFi: buscar redes ----
dom.btnWifiScan.addEventListener("click", async () => {
    dom.btnWifiScan.disabled = true;
    dom.btnWifiScan.textContent = "Buscando...";
    hideWifiMessage();
    try {
        const res = await fetch("/api/network/wifi/scan");
        const data = await res.json();
        const nets = data.networks || [];

        if (data.error) {
            showWifiMessage(data.error, false);
        } else if (nets.length === 0) {
            showWifiMessage("No se encontraron redes WiFi.", false);
        }

        dom.wifiSsid.innerHTML = nets.length
            ? nets.map(n =>
                `<option value="${escapeHtml(n.ssid)}">${escapeHtml(n.ssid)}${n.secure ? " 🔒" : ""} (${n.signal}%)</option>`
              ).join("")
            : '<option value="">Sin redes</option>';
    } catch {
        showWifiMessage("Error al escanear redes.", false);
    } finally {
        dom.btnWifiScan.disabled = false;
        dom.btnWifiScan.textContent = "Buscar redes";
    }
});

// ---- WiFi: conectar ----
dom.btnWifiConnect.addEventListener("click", async () => {
    const ssid = dom.wifiSsid.value;
    const password = dom.wifiPassword.value;

    if (!ssid) {
        showWifiMessage("Elige una red primero.", false);
        return;
    }

    dom.btnWifiConnect.disabled = true;
    dom.btnWifiConnect.textContent = "Conectando...";
    hideWifiMessage();
    try {
        const res = await fetch("/api/network/wifi/connect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ssid, password }),
        });
        const data = await res.json();
        showWifiMessage(data.message || (data.ok ? "Conectado." : "No se pudo conectar."), data.ok);
        if (data.ok) {
            dom.wifiPassword.value = "";
            fetchStatus();
        }
    } catch {
        showWifiMessage("Error de conexión al intentar conectar.", false);
    } finally {
        dom.btnWifiConnect.disabled = false;
        dom.btnWifiConnect.textContent = "Conectar a WiFi";
    }
});

// ---- Cuenta: mostrar canal vinculado ----
async function fetchChannel() {
    try {
        const res = await fetch("/api/channel");
        const data = await res.json();
        if (res.ok && data.title) {
            dom.channelName.textContent = `Canal vinculado: ${data.title}`;
        } else {
            dom.channelName.textContent = "Canal vinculado: no disponible";
        }
    } catch {
        dom.channelName.textContent = "Canal vinculado: no disponible";
    }
}

// ---- Cuenta: desvincular y volver a vincular ----
dom.btnUnlink.addEventListener("click", async () => {
    if (!confirm("Esto desvincula la cuenta actual. Tendrás que iniciar sesión de nuevo y elegir el canal. ¿Continuar?")) {
        return;
    }
    dom.btnUnlink.disabled = true;
    try {
        await fetch("/api/auth/unlink", { method: "POST" });
        window.location.href = "/auth";
    } catch {
        dom.btnUnlink.disabled = false;
        alert("No se pudo desvincular. Intenta de nuevo.");
    }
});

// ==============================================================================
// SECCION 7: INICIALIZACION
// ==============================================================================

fetchStatus();
setInterval(fetchStatus, POLL_INTERVAL);
