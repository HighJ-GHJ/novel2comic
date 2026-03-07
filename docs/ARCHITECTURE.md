# novel2comic 架构文档（ARCHITECTURE）

> 重大变更记录见 [CHANGELOG.md](./CHANGELOG.md)。

## 1. 项目目标

将中文小说 txt 自动转换为“动态漫画 / 动态分镜”长视频：
- 主体是静态图 + 轻动效（Ken Burns、视差、震屏等）
- 旁白由 TTS 生成（默认 SiliconFlow CosyVoice2）
- 字幕由 Align-Lite 基于真实音频时长生成 ASS/SRT
- 输出至少包含预览 MP4；后续可扩展剪映 / CapCut Draft 工程

MVP 非目标：
- 逐帧动画
- 复杂角色骨骼动画
- 长镜头高一致性 I2V

---

## 2. 当前实际流水线

当前代码以 `pipeline/orchestrator.STAGE_ORDER` 为准，阶段顺序是：

`ingest -> segment -> plan -> director_review -> anchors -> image -> tts -> align -> render -> export`

对应概念流水线如下：

输入：整本小说 txt（任意编码）
↓
(0) Normalize 输入编码 -> UTF-8
↓
(1) Split：整本 -> chapters（按“第…章/回/节”切分）
↓
(2) Prepare：为每个章节创建 ChapterPack 目录骨架并写入 `text/chapter_clean.txt`
↓
(3) Ingest：创建 / 更新 manifest，确认 ChapterPack 基础状态
↓
(4) Segment：baseline split + `refine_shot_split` -> `shotscript.json`
↓
(5) Plan：引号切分 + `speech_plan` -> 为每个 shot 补齐 `speech`
↓
(6) Director Review：patch-only 导演审阅 -> `shotscript.directed.json`
↓
(7) Anchors：生成角色锚点 / 风格锚点（供 Image 阶段复用）
↓
(8) Image：Qwen-Image / Qwen-Image-Edit 出图
↓
(9) TTS：按 segment 合成 shot wav，再拼接 `chapter.wav`
↓
(10) Align-Lite：按 shot 时长与 segment 比例生成 `chapter.ass` / `chapter.srt`
↓
(11) Render：ffmpeg 合成 `video/preview.mp4`
↓
(12) Export：待实现

说明：
- `image` 当前在 `tts` 之前执行，这是代码中的真实顺序。
- TTS / Align / Render 会优先读取 `shotscript.directed.json`，否则回退到 `shotscript.json`。

---

## 3. 关键中间表示

### 3.1 ChapterPack

每章一个目录，作为断点续跑和产物归档的最小工作单元。典型结构：

```text
output/<novel_id>/<chapter_id>/
  manifest.json
  shotscript.json
  shotscript.directed.json
  text/
    chapter_clean.txt
  director/
    director_review.json
  audio/
    chapter.wav
    shots/
  subtitles/
    chapter.ass
    chapter.srt
    align/
  images/
    anchors/
    shots/
    layers/
  video/
    preview.mp4
  draft/
  logs/
```

### 3.2 ShotScript / effective_shotscript

`shotscript.json` 是上游结构化镜头脚本；`shotscript.directed.json` 是导演审阅后的有效版本。

关键约定：
- `shot_id` 必须稳定
- `raw_text` / `tts_text` / `subtitle_text` 必须分离
- 时间轴以真实音频时长为准（`tts_driven`）

`core/io.py` 通过 `ChapterPaths.effective_shotscript()` 统一选择有效脚本，后续阶段不需要自行判断 directed 文件是否存在。

### 3.3 manifest.json

`manifest.json` 记录：
- 当前阶段与已完成阶段
- warnings / failed stage
- 时长统计
- providers / artifacts
- `shots_index`、`images_index`

用途：
- 断点续跑
- 局部重做
- 失败恢复
- 复现同 seed / 同 prompt 的结果

---

## 4. 路径与配置解析规则

这是本次本地 / 服务器可移植化改造的核心。

### 4.1 项目根目录解析

项目根目录不再依赖“某台机器上的固定绝对路径”，也不再依赖“.env 必须先存在”。

`core/io.find_project_root()` 的解析顺序：
1. `NOVEL2COMIC_PROJECT_ROOT`
2. 显式传入的起点路径
3. 当前模块所在目录
4. 当前工作目录

识别项目根目录的标记为：
- `pyproject.toml`
- `.git`
- `src/novel2comic/`

### 4.2 .env 解析

`core/io.find_env_file()` 统一返回应使用的 env 文件路径：
- 优先 `NOVEL2COMIC_ENV_FILE`
- 否则使用 `<project_root>/.env`

### 4.3 哪些模块依赖这套规则

以下模块已统一切到新的路径解析逻辑：
- `core/config_loader.py`
- `providers/llm/siliconflow_client.py`
- `providers/tts/siliconflow_tts.py`
- `providers/image/image_qwen.py`
- `providers/image/image_flux.py`
- `providers/vlm/siliconflow_vlm.py`
- `scripts/smoke_full_chain.py`

效果：
- 从任意工作目录启动 CLI / 脚本都能正确找到项目根
- 本地 Windows 和云服务器可以共用同一套代码
- 只需通过环境变量覆盖，就能切换不同机器上的 `.env`

---

## 5. 模块职责

| 模块 | 职责 |
|------|------|
| `core/io.py` | ChapterPack 路径约定、`find_project_root()`、`find_env_file()`、`effective_shotscript()` |
| `core/config_loader.py` | 加载 `configs/*.yaml`，并叠加环境变量覆盖 |
| `core/manifest.py` | manifest 读写、阶段状态维护、warning 记录 |
| `stages/segment.py` | baseline split + refine，生成 `shotscript.json` |
| `stages/plan.py` | 补齐 `speech` 字段 |
| `stages/director_review.py` | 合并导演审阅 patch，生成 `shotscript.directed.json` |
| `stages/anchors_generate.py` | 生成角色锚点 / 风格锚点 |
| `stages/image_generate.py` | 生成 shot 图像并记录 metadata |
| `stages/tts.py` | 合成 shot 级音频与整章音频 |
| `stages/align.py` | 基于真实音频生成 ASS/SRT |
| `stages/render.py` | 生成 `video/preview.mp4` |
| `providers/llm` | SiliconFlow LLM 封装 |
| `providers/tts` | SiliconFlow TTS 封装 |
| `providers/image` | Qwen / FLUX 图像生成能力 |
| `providers/vlm` | 严格图像 QA / recheck |
| `skills/refine_shot_split` | 语义分镜修正 |
| `skills/speech_plan` | 朗读参数 patch |

---

## 6. 调用链路

### 6.1 运行链路

`cli.py` / 脚本入口
-> `pipeline/orchestrator.run_until()`
-> 各 stage `run(paths, ctx)`
-> `core` / `providers` / `skills` / `director_review`

### 6.2 配置与路径链路

入口或 provider
-> `core/io.find_project_root()` / `core/io.find_env_file()`
-> `core/config_loader`
-> `configs/*.yaml` + `.env` + 环境变量

### 6.3 产物流转链路

`chapter_clean.txt`
-> `shotscript.json`
-> `shotscript.directed.json`
-> `images/*` / `audio/*`
-> `subtitles/*`
-> `video/preview.mp4`

---

## 7. 当前实现状态（截至 2026-03-07）

### 已实现

| 模块 | 状态 |
|------|------|
| ingest | 已实现 |
| segment | 已实现 |
| plan | 已实现 |
| director_review | 已实现 |
| anchors | 已实现 |
| image | 已实现 |
| tts | 已实现 |
| align | 已实现 |
| render | 已实现 |
| export | 待实现 |

### 本次已完成的工程化改造

- 项目根目录自动解析，不再依赖硬编码路径
- `.env` 路径统一解析，不再依赖当前工作目录
- provider / config loader / smoke 脚本统一使用同一套根目录规则
- 新增 `requirements.txt`，方便本地快速安装运行依赖
- 文档与真实阶段顺序重新对齐（补入 `anchors`，修正本地 / 服务器运行方式）

---

## 8. 关键工程约定

- 内部文本统一 UTF-8
- `shot_id` 必须稳定
- `raw_text` / `tts_text` / `subtitle_text` 必须分离
- 时间轴以真实音频为准
- ChapterPack 内路径必须可迁移，不写死机器绝对路径
- 配置优先级始终为：环境变量 > YAML > 代码默认

---

*最后更新：2026-03-07*