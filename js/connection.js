// ComfyUI-PhotoCraft WebSocket client (original code).
// Loopback only (ws://127.0.0.1). Every connection carries a Bearer token
// from the private token file (entered once in Settings, never hard-coded).
// Auto-reconnects after 5s. No git / pip / admin behaviour here.
(function (global) {
  "use strict";

  class PhotoCraftConnection {
    constructor({ host = "127.0.0.1", port = 8190, token = "", platform = "pc", onMessage = null, onStatus = null } = {}) {
      this.host = host;
      this.port = port;
      this.token = token;
      this.platform = platform; // "pc" (panel) or "cm" (ComfyUI front-end)
      this.onMessage = onMessage;
      this.onStatus = onStatus;
      this.ws = null;
      this.reconnectTimer = null;
      this.shouldReconnect = true;
      this.reconnectDelayMs = 5000;
    }

    url() {
      const token = encodeURIComponent(this.token || "");
      return `ws://${this.host}:${this.port}/pc/ws?platform=${encodeURIComponent(this.platform)}&token=${token}`;
    }

    connect() {
      if (!this.token) {
        this._status("missing token: set it in Settings first");
        return;
      }
      if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
      this.shouldReconnect = true;
      const ws = new WebSocket(this.url());
      this.ws = ws;
      ws.onopen = () => this._status("connected");
      ws.onmessage = (ev) => {
        let msg = null;
        try { msg = JSON.parse(ev.data); } catch { return; }
        if (typeof this.onMessage === "function") this.onMessage(msg);
      };
      ws.onclose = () => {
        this._status("disconnected");
        this._scheduleReconnect();
      };
      ws.onerror = () => {
        try { ws.close(); } catch {}
      };
    }

    disconnect() {
      this.shouldReconnect = false;
      if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
      if (this.ws) { try { this.ws.close(); } catch {} }
      this.ws = null;
    }

    send(obj) {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
      this.ws.send(JSON.stringify(obj));
      return true;
    }

    sendCanvas(base64Png) { return this.send({ type: "canvasBase64", imageBase64: base64Png }); }
    sendMask(base64Png) { return this.send({ type: "maskBase64", imageBase64: base64Png }); }
    sendConfig(config) { return this.send({ type: "configdata", ...config }); }
    sendWorkspace(payload) { return this.send({ type: "workspace", ...payload }); }
    sendQueue(payload) { return this.send({ type: "queue", ...payload }); }

    _status(text) { if (typeof this.onStatus === "function") this.onStatus(text); }

    _scheduleReconnect() {
      if (!this.shouldReconnect) return;
      if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
      this.reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelayMs);
    }
  }

  global.PhotoCraftConnection = PhotoCraftConnection;
})(typeof window !== "undefined" ? window : globalThis);
