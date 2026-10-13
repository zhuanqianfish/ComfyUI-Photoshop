# ComfyUI-PhotoCraft 中文文档

> [中文] | [English](README.md)

> 英文版见 [README.md](README.md)。两者内容对应，以实现为准；如有出入，以代码和 `docs/FUNCTION_MAP.md` 为准。

## 这是什么

ComfyUI-PhotoCraft 是一个原创桥接插件：让 PhotoCraft 用户在**不修改 PhotoCraft 源码**的前提下，用本地 ComfyUI 做 AI 生成 / 修复（inpaint）/ 重绘，并把结果接回 PhotoCraft。

它参考的只是公开的架构思路（面板 + ComfyUI 节点 + WebSocket + 本地文件交换），没有复制任何现有仓库的源码。

## 它不是什么

先把边界说清，避免按错方向用：

- PhotoCraft 目前没有 Photoshop 式的 UXP 面板，没有 ExtendScript 远程连接，暂无插件兼容（PhotoCraft README 自述）。所以本插件**不会在 PhotoCraft 内部嵌一个面板**。
- 本插件的形态是：**ComfyUI 自定义节点 + Python 桥接后端 + 独立本地 Web 侧边面板（在浏览器里打开，和 PhotoCraft 并排用）+ PhotoCraft 适配层（文件模式 + Live 控制通道模式）**。
- PhotoCraft 的 WASM 插件是沙箱滤镜插件、没有网络能力，所以面板做不成 WASM 插件，只能是外部 HTML/JS 面板。这是设计上的取舍，不是缺漏。

## 架构一览

```text
PhotoCraft（桌面 App / photocraft-cli）
  ↕ 文件交换（PC_canvas.png / PC_mask.png / config.json）
  ↕ Live 模式：JSON 控制通道（127.0.0.1 TCP，先 auth，再 engine.execute 等）
        │
        ▼
PhotoCraft 适配层 py/photocraft_adapter.py
  - file 模式：调 photocraft-cli convert / info / run
  - live 模式：TCP JSON-lines，auth → engine.execute / ui.inspect / ui.screenshot
        │
        ▼
桥接后端 py/backend.py（/pc/*，只绑 127.0.0.1，要求 Bearer token）
  ↕ WebSocket /pc/ws（platform=pc / cm 分开记录）
        │
        ▼
ComfyUI：PhotoCraftToComfyUI → 你的生成工作流 → ComfyUIToPhotoCraft
        │
        ▼
侧边面板 photocraft_panel/（浏览器打开：Ai Panel / Settings / ComfyUI Web）
```

典型一次往返：

1. 在 PhotoCraft 里准备好画布 / 选区，导出为 `data/pc_inputs/PC_canvas.png`、`PC_mask.png`，并写好 `config.json`（正/负提示词、种子、Slider）。
2. 在 ComfyUI 里跑工作流：`PhotoCraftToComfyUI` → 生成节点 → `ComfyUIToPhotoCraft`。
3. 点面板里的「应用回 PhotoCraft」，或调适配层的 `import_result(...)`，把结果作为新图层 / 新文档接回。

## 环境要求

| 要求 | 说明 |
|---|---|
| PhotoCraft | 桌面 App 或 `photocraft-cli`。Live 模式需要以 `--control` 启动（见下）。 |
| ComfyUI | 本地可用的 ComfyUI 安装，及你自己的模型。 |
| GPU | 建议本地 GPU（SD1.5 建议 ≥ 6GB 显存）；纯 CPU 也能跑，但很慢。 |
| Python | 3.10+。插件只用标准库 + ComfyUI 自带的东西。 |
| aiohttp | 仅在启动 `py/backend.py` 时需要，ComfyUI 通常已自带。 |

**不需要 API Key。** 所有模型都在本地跑。

## 安装

```bash
# 1. 复制 / 链接到 ComfyUI（不提权、不做 git 操作、不做 pip 安装）
python3 install.py --comfyui-root /path/to/ComfyUI \
  --photocraft-cli photocraft-cli \
  --control-token-file /private/path/photocraft-control.token \
  --backend-token-file /private/path/pc-bridge.token \
  --automation-read-root /path/to/work \
  --automation-write-root /path/to/work \
  --mode file

# 2. 启动桥接后端（只绑回环地址）
python3 -m py.backend --host 127.0.0.1 --port 8190

# 3. 在浏览器里打开侧边面板
#    photocraft_panel/index.html（在 Settings 里填入桥接 token）

# 4. 重启 ComfyUI，让节点加载生效。
```

卸载：

```bash
python3 uninstall.py --comfyui-root /path/to/ComfyUI [--remove-config]
```

> 注意：`--control-token-file` / `--backend-token-file` 填的是**存放 token 的私有文件路径**，不是 token 值本身。不要把真实 token 写进命令行历史、配置文件或聊天记录里。

## 两种模式

### 文件模式（默认，`mode=file`）

最稳、最先推荐的模式，不需要 PhotoCraft 保持运行：

1. 把文档导出为 `data/pc_inputs/PC_canvas.png`（画布），把选区/蒙版导出为 `PC_mask.png`，再写好 `config.json`（提示词 / 种子 / Slider）。可以用面板做，也可以用适配层：`adapter.export_canvas_mask("doc.psd")`。
2. 在 ComfyUI 里跑工作流：`PhotoCraftToComfyUI` → `ComfyUIToPhotoCraft`。
3. 用 `adapter.import_result(...)` 或面板里的「应用回 PhotoCraft」按钮，把暂存的渲染结果接回。

### Live 模式（`mode=live`）

需要你**自己**先以控制通道方式启动 PhotoCraft，插件不会代你启动它：

```bash
photocraft --control 7878 \
  --control-token-file /private/path/photocraft-control.token \
  --automation-read-root /path/to/work \
  --automation-write-root /path/to/work
```

之后可以用 `PhotoCraftControl` 节点（走 `engine.execute`）或 `POST /pc/command` 执行 `layer.new.layer`、`doc.info`、`ui.inspect`、`ui.screenshot` 这类命令。

**只有 Live 模式能执行引擎命令；文件模式只做文件暂存。** 在文件模式下调 `execute_command` 会被明确拒绝。

## 配置

`config.json` 由 `install.py` 生成；token 相关项只存**文件路径**，不存 token 值：

| 键 | 含义 |
|---|---|
| `photocraft_cli` | `photocraft-cli` 的路径 / 命令名 |
| `control_host` / `control_port` | PhotoCraft 控制通道，必须保持 `127.0.0.1` |
| `control_token_file` | 存放 PhotoCraft 控制 token 的私有文件 |
| `automation_read_root` / `automation_write_root` | PhotoCraft 允许读 / 写的目录 |
| `comfyui_host` / `comfyui_port` | ComfyUI 地址（回环） |
| `backend_host` / `backend_port` | 本桥接后端地址，必须保持 `127.0.0.1` |
| `backend_token_file` | 存放本桥接后端 token 的私有文件 |
| `inputs_dir` / `outputs_dir` | `data/pc_inputs` / `data/pc_outputs` |
| `mode` | `file` 或 `live` |

## 节点说明

| 节点 | 作用 |
|---|---|
| `PhotoCraftToComfyUI` | 读 `PC_canvas.png` / `PC_mask.png` / `config.json`；输出 `(IMAGE, MASK, FLOAT, INT, STRING, STRING, INT, INT, STRING, STRING)`，依次是画布、蒙版、Slider、种子、正提示词、负提示词、宽、高、图层名、选区范围。`IS_CHANGED` 用三个输入文件的 MD5 判断变化。 |
| `ComfyUIToPhotoCraft` | 类 SaveImage 的保存逻辑 + `GET /pc/renderdone?filename=…` 通知 + `last_render.json` 兜底文件。 |
| `ClipPass` / `ModelPass` | 原样透传 CLIP / MODEL，不做改动。 |
| `PhotoCraftControl` | 在 Live 模式下经控制通道执行 PhotoCraft 的 `engine.execute` 命令。不用 ExtendScript。 |

## 工作流（`data/workflows/`）

| 文件 | 用途 |
|---|---|
| `pc_sd15_txt2img.json` | SD1.5 文生图 |
| `pc_sd15_inpaint.json` | SD1.5 修复（画布 + 蒙版，去噪强度 = Slider） |
| `pc_sd15_controlnet.json` | SD1.5 ControlNet 线稿（强度 = Slider） |
| `pc_sd15_upscale.json` | SD1.5 4× 放大 |
| `pc_sdxl_txt2img.json` | SDXL 文生图 |

每个工作流都引用了 `PhotoCraftToComfyUI` / `ComfyUIToPhotoCraft`，其余只用标准 ComfyUI 节点类型（`CheckpointLoaderSimple`、`CLIPTextEncode`、`KSampler`、`VAEDecode`、`ControlNetLoader`、`UpscaleModelLoader` 等）。各文件的 `_meta` 里有 `en-US / zh-CN / zh-TW / ja-JP / ko-KR` 五种语言的提示词占位。

使用前把 `ckpt_name` / `control_net_name` / `model_name` 换成你自己已有的模型文件名。

## 侧边面板用法

打开 `photocraft_panel/index.html`，有三个入口：Ai Panel / Settings / ComfyUI Web。

- **Ai Panel**：填正/负提示词、种子、Slider；选选区模式（new / add / subtract / intersect）；勾选裁剪到选区、保留选区、按通道播放、边距；选工作流，点队列，查看进度条和结果预览。
- **Settings**：填桥接地址、端口、token、PhotoCraft 控制通道地址、自动化读写根目录。
- **ComfyUI Web**：快速跳转到 ComfyUI 的 Web 界面。
- 生成完成后点「应用回 PhotoCraft」，走 `POST /pc/command`（`import_result`）把结果接回。

## 安全说明

这些是针对参考 Photoshop 桥接插件已知问题做的有意修复，不是默认行为：

- `/pc/*` 只绑 `127.0.0.1`，且每个路由都要求 Bearer token（从私有 token 文件读）。**没有默认密码**，缺 token 文件时拒绝启动服务。
- 没有 `git reset --hard`，没有自动 `pip install`，安装器不请求管理员权限，不从字符串生成代码。
- 所有文件路径都用 `commonpath` 校验，读写限定在配置的自动化根目录 / 输入 / 输出目录内。
- 前端只在回环地址用 `ws://`，且附带 token。
- 客户端用 `pc_clients` / `cm_clients` 两个 dict 分开记录，不用“最后一个连接的客户端”这种易错路由。
- 本仓库没有不透明的二进制插件包（例如 `.ccx`），面板就是 plain HTML/JS/CSS，可直接审计。

**使用底线：桥接后端保持在回环地址。** 不要在没有加 TLS + 自己鉴权的情况下把它放到公网反向代理后面。

## 测试

```bash
python3 -m unittest discover -s tests -v
# 如果有 pytest：
python3 -m pytest tests/ -q
```

测试覆盖：导入（用 stub 模拟 ComfyUI 环境）、协议消息构造、路径穿越防护、token 校验、控制通道 auth + `engine.execute` 回包（用 fake TCP 服务器）。

功能逐项对照见 [docs/FUNCTION_MAP.md](docs/FUNCTION_MAP.md)，共 28 项，从参考 Photoshop 桥接到本插件都有对应实现位置或明确的等价实现 / 有意省略说明。

## 目录结构

```text
├── __init__.py              # ComfyUI 入口，WEB_DIRECTORY="js"，注册节点
├── py/
│   ├── backend.py           # /pc/* 桥接后端
│   ├── nodes.py             # 5 个节点
│   ├── photocraft_adapter.py# PhotoCraft 适配层（file + live）
│   └── config.py            # 配置、token 文件读取、路径校验
├── js/
│   ├── connection.js        # WS 客户端（5 秒重连，附 token）
│   └── manager.js           # 工作流加载、队列/进度转发、渲染模式切换
├── photocraft_panel/        # 独立本地 Web 侧边面板
├── data/
│   ├── workflows/           # 5 个工作流
│   └── pc_inputs/           # 运行时交换文件：PC_canvas.png / PC_mask.png / config.json
├── install.py / uninstall.py
├── README.md / README-zh.md # 英 / 中文档
├── LICENSE                  # 标准 MIT，无附加条款
├── pyproject.toml           # 零运行时依赖声明
└── tests/                   # unittest 测试
```

## 限制与已知事项

- **无内嵌面板**：PhotoCraft 无 UXP / 插件兼容，面板只能是外部侧边栏，与 PhotoCraft 并排使用。
- **Live 模式需手动启动 PhotoCraft**：见上文命令，插件不代启动。
- **未做真机端到端验证**：没有在真实 PhotoCraft / ComfyUI 环境跑通 PSD → 生成 → 回写全链路。`import_result` 中 `photocraft-cli run --place` 的调用形态是按 CLI 约定假设的，实机使用前请对照本地 `photocraft-cli --help` 核对。
- **有意未移植**：Photopea（Photoshop 专属）、ComfyUI Cloud（原版未核实且需账号，本插件坚持本地-only）。
- PhotoCraft 本身处于 early alpha，PSD 往返不是字节相同，重要文件请先备份、导出后用目标应用实测打开。

## 常见问题

**Q：为什么面板不在 PhotoCraft 里面？**
A：PhotoCraft 没有提供这种面板宿主，WASM 插件又无网络能力。外部侧边栏是目前唯一不改源码又能用的方式。

**Q：先用哪种模式？**
A：先用文件模式。它不依赖 PhotoCraft 保持运行，出问题也最容易定位：先看 `data/pc_inputs/` 三个文件是否正确，再看 ComfyUI 工作流是否跑通，最后看 `import_result` 是否接回。

**Q：报 token / 鉴权错误怎么办？**
A：先确认两个 token 文件都存在且内容正确：一个是 PhotoCraft 控制通道的，一个是桥接后端的。两者不要混用，也不要把 token 值写进 `config.json`。

**Q：Live 模式连不上？**
A：确认 PhotoCraft 是你手动以 `--control` 启动的，端口、token 文件、自动化读写根目录与 `config.json` 一致，且都在 `127.0.0.1` 回环内。

## 许可证

MIT，见 [LICENSE](LICENSE)。本仓库用标准 MIT，无附加条款。
