/**
 * Yanımda Al — ortam bilincili API / WebSocket yapılandırması (PR-3c).
 *
 * Yerel: http://127.0.0.1:8000
 * Canlı: PRODUCTION_API_ORIGIN (aşağıda) veya:
 *   - <meta name="yanimda-api" content="https://....onrender.com">
 *   - window.YANIMDA_API_ORIGIN = "https://...." (config.js öncesi)
 *   - ?api=https://....onrender.com sorgu parametresi
 */
(function (global) {
    const PRODUCTION_API_ORIGIN = "https://yanimda-al-backend.onrender.com";

    function isLocalHost(hostname) {
        return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "[::1]";
    }

    function trimSlash(url) {
        return String(url || "").replace(/\/+$/, "");
    }

    function toWsBase(httpOrigin) {
        const origin = trimSlash(httpOrigin);
        if (origin.startsWith("https://")) return "wss://" + origin.slice("https://".length);
        if (origin.startsWith("http://")) return "ws://" + origin.slice("http://".length);
        if (origin.startsWith("wss://") || origin.startsWith("ws://")) return origin;
        return origin;
    }

    function resolveApiOrigin() {
        try {
            const params = new URLSearchParams(global.location.search);
            const fromQuery = params.get("api");
            if (fromQuery) return trimSlash(fromQuery);
        } catch (_) { /* ignore */ }

        if (global.YANIMDA_API_ORIGIN) {
            return trimSlash(global.YANIMDA_API_ORIGIN);
        }

        const meta = global.document && global.document.querySelector('meta[name="yanimda-api"]');
        if (meta && meta.content) {
            return trimSlash(meta.content);
        }

        const host = (global.location && global.location.hostname) || "localhost";
        if (isLocalHost(host)) {
            return "http://127.0.0.1:8000";
        }

        return trimSlash(PRODUCTION_API_ORIGIN);
    }

    const apiOrigin = resolveApiOrigin();

    global.CONFIG = {
        API_ORIGIN: apiOrigin,
        API_BASE_URL: apiOrigin + "/api",
        WS_BASE_URL: toWsBase(apiOrigin),
        IS_LOCAL: isLocalHost((global.location && global.location.hostname) || ""),
    };
})(window);
