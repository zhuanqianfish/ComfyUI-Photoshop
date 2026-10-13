// ComfyUI-PhotoCraft front-end manager (original code).
// Handles workflow loading, queue forwarding, progress forwarding,
// render-mode switching and the selection-equivalent options
// (crop_to_selection / preserve_selection / play_on_channels / margin).
// Works against the loopback bridge backend; never touches git/pip/admin.
(function (global) {
  "use strict";

  const WORKFLOWS = [
    { id: "pc_sd15_txt2img", label: "SD1.5 Text to Image" },
    { id: "pc_sd15_inpaint", label: "SD1.5 Inpaint" },
    { id: "pc_sd15_controlnet", label: "SD1.5 ControlNet" },
    { id: "pc_sd15_upscale", label: "SD1.5 Upscale" },
    { id: "pc_sdxl_txt2img", label: "SDXL Text to Image" },
  ];

  class PhotoCraftManager {
    constructor({ connection = null, backendHost = "127.0.0.1", backendPort = 8190, token = "", onProgress = null, onRender = null, onAlert = null } = {}) {
      this.connection = connection;
      this.backendHost = backendHost;
      this.backendPort = backendPort;
      this.token = token;
      this.onProgress = onProgress;
      this.onRender = onRender;
      this.onAlert = onAlert;
      this.currentWorkflow = "pc_sd15_txt2img";
      this.renderMode = "txt2img"; // txt2img | inpaint | controlnet | upscale
      this.options = {
        crop_to_selection: false,
        preserve_selection: true,
        play_on_channels: "all", // all | red | green | blue | alpha
        margin: 0,
      };
    }

    static workflows() { return WORKFLOWS.slice(); }

    setOptions(patch) {
      Object.assign(this.options, patch || {});
      return { ...this.options };
    }

    setRenderMode(mode) {
      const allowed = ["txt2img", "inpaint", "controlnet", "upscale"];
      if (!allowed.includes(mode)) throw new Error(`unknown render mode: ${mode}`);
      this.renderMode = mode;
      return mode;
    }

    async loadWorkflow(name, { locale = "en-US" } = {}) {
      const id = name || this.currentWorkflow;
      this.currentWorkflow = id;
      const url = `http://${this.backendHost}:${this.backendPort}/pc/workflows/${encodeURIComponent(id)}.json`;
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${this.token}` } });
      if (!resp.ok) throw new Error(`load workflow failed: ${resp.status}`);
      const workflow = await resp.json();
      // The caller (ComfyUI front-end or panel) decides how to apply the
      // workflow JSON; the manager only fetches + annotates it.
      return { workflow, locale, options: { ...this.options }, renderMode: this.renderMode };
    }

    queuePrompt(workflow, promptInputs = {}) {
      const payload = {
        workflow,
        inputs: { ...promptInputs, options: { ...this.options }, renderMode: this.renderMode },
      };
      const ok = this.connection ? this.connection.sendQueue(payload) : false;
      if (!ok && typeof this.onAlert === "function") this.onAlert("not connected: queue was not sent");
      return ok;
    }

    handleMessage(msg) {
      if (!msg || typeof msg !== "object") return;
      if (msg.type === "progress" && typeof this.onProgress === "function") {
        this.onProgress(msg);
      } else if (msg.type === "render" && typeof this.onRender === "function") {
        this.onRender(msg);
      } else if (msg.type === "alert" && typeof this.onAlert === "function") {
        this.onAlert(msg.message || "alert");
      }
    }

    // Selection helpers (panel-side equivalents of the Photoshop actions).
    // They operate on plain {x, y, w, h} bounds, not on Photoshop APIs.
    cropBoundsToSelection(bounds, selection) {
      if (!this.options.crop_to_selection || !selection) return bounds;
      const m = Math.max(0, this.options.margin | 0);
      return {
        x: Math.max(bounds.x, selection.x - m),
        y: Math.max(bounds.y, selection.y - m),
        w: Math.min(bounds.w, selection.w + 2 * m),
        h: Math.min(bounds.h, selection.h + 2 * m),
      };
    }
  }

  global.PhotoCraftManager = PhotoCraftManager;
  global.PhotoCraftWorkflows = WORKFLOWS;
})(typeof window !== "undefined" ? window : globalThis);
