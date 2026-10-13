// ComfyUI-PhotoCraft side panel app (original code).
// Connects to the loopback bridge backend. No token is hard-coded; the
// token comes from the Settings field (paste from your private file).
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  let connection = null;
  let manager = null;
  let lastRenderFilename = "";

  function currentSettings() {
    return {
      backendHost: $("backendHost").value.trim() || "127.0.0.1",
      backendPort: parseInt($("backendPort").value, 10) || 8190,
      token: $("token").value,
      comfyHost: $("comfyHost").value.trim() || "127.0.0.1",
      comfyPort: parseInt($("comfyPort").value, 10) || 8188,
      controlPort: parseInt($("controlPort").value, 10) || 7878,
    };
  }

  function currentPromptConfig() {
    return {
      positive: $("positive").value,
      negative: $("negative").value,
      seed: parseInt($("seed").value, 10) || 0,
      slider: parseFloat($("slider").value) || 0.7,
      layer_name: $("layerName").value,
      selection_bounds: $("selectionBounds").value,
      selection_mode: $("selectionMode").value,
      crop_to_selection: $("cropToSelection").checked,
      preserve_selection: $("preserveSelection").checked,
      margin: parseInt($("margin").value, 10) || 0,
      play_on_channels: $("channels").value,
      workflow: $("workflow").value,
    };
  }

  function setStatus(text) { $("status").textContent = text; }

  function connect() {
    const s = currentSettings();
    if (connection) connection.disconnect();
    connection = new PhotoCraftConnection({
      host: s.backendHost, port: s.backendPort, token: s.token, platform: "pc",
      onMessage: (msg) => manager && manager.handleMessage(msg),
      onStatus: setStatus,
    });
    manager = new PhotoCraftManager({
      connection, backendHost: s.backendHost, backendPort: s.backendPort, token: s.token,
      onProgress: (msg) => {
        const pct = Math.round(((msg.value || 0) / Math.max(1, msg.max || 1)) * 100);
        $("progress").value = pct;
        $("progressText").textContent = `step ${msg.value || 0}/${msg.max || 0}`;
      },
      onRender: (msg) => {
        if (msg.imageBase64) {
          $("resultPreview").src = "data:image/png;base64," + msg.imageBase64;
          $("resultInfo").textContent = `render: ${msg.filename || ""}`;
          lastRenderFilename = msg.filename || "";
        }
      },
      onAlert: (text) => { $("progressText").textContent = text; },
    });
    manager.setOptions({
      crop_to_selection: $("cropToSelection").checked,
      preserve_selection: $("preserveSelection").checked,
      play_on_channels: $("channels").value,
      margin: parseInt($("margin").value, 10) || 0,
    });
    connection.connect();
    $("comfyLink").href = `http://${s.comfyHost}:${s.comfyPort}`;
    $("comfyLink").textContent = $("comfyLink").href;
  }

  function previewFile(inputEl, canvasEl) {
    const file = inputEl.files && inputEl.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const ctx = canvasEl.getContext("2d");
        ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
        ctx.drawImage(img, 0, 0, canvasEl.width, canvasEl.height);
        // Forward the canvas/mask to ComfyUI via the bridge.
        const dataUrl = canvasEl.toDataURL("image/png");
        const b64 = dataUrl.split(",")[1] || "";
        if (connection && canvasEl.id === "canvasPreview") connection.sendCanvas(b64);
        if (connection && canvasEl.id === "maskPreview") connection.sendMask(b64);
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  }

  async function queue() {
    const s = currentSettings();
    const cfg = currentPromptConfig();
    if (connection) connection.sendConfig(cfg);
    try {
      const { workflow } = await manager.loadWorkflow(cfg.workflow);
      manager.setRenderMode(cfg.workflow.includes("inpaint") ? "inpaint" : cfg.workflow.includes("controlnet") ? "controlnet" : cfg.workflow.includes("upscale") ? "upscale" : "txt2img");
      manager.queuePrompt(workflow, cfg);
      $("progressText").textContent = "queued";
    } catch (err) {
      $("progressText").textContent = `queue failed: ${err.message}`;
    }
  }

  async function applyBack() {
    const s = currentSettings();
    const cfg = currentPromptConfig();
    if (!lastRenderFilename) {
      $("progressText").textContent = "no render yet: queue and wait for a result first";
      return;
    }
    // Ask the bridge to import the staged render into PhotoCraft.
    // File mode stages it; live mode executes the placement command.
    const resp = await fetch(`http://${s.backendHost}:${s.backendPort}/pc/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${s.token}` },
      body: JSON.stringify({ command: "import_result", params: { filename: lastRenderFilename, layer_name: cfg.layer_name } }),
    });
    const data = await resp.json().catch(() => ({}));
    $("progressText").textContent = resp.ok ? `apply: ${JSON.stringify(data)}` : `apply failed: ${data.error || resp.status}`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
      });
    });
    $("slider").addEventListener("input", (e) => { $("sliderVal").textContent = Number(e.target.value).toFixed(2); });
    $("connectBtn").addEventListener("click", connect);
    $("disconnectBtn").addEventListener("click", () => { if (connection) connection.disconnect(); });
    $("queueBtn").addEventListener("click", queue);
    $("applyBtn").addEventListener("click", applyBack);
    $("canvasFile").addEventListener("change", () => previewFile($("canvasFile"), $("canvasPreview")));
    $("maskFile").addEventListener("change", () => previewFile($("maskFile"), $("maskPreview")));
  });
})();
