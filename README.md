# novel2comic

将中文小说 txt 全自动生成「动态漫画/动态分镜」长视频的流水线。

- **主体**：静态图 + 轻动效（Ken Burns/视差/震屏）
- **旁白**：TTS（SiliconFlow CosyVoice2，默认）
- **字幕**：Align-Lite 按 shot 时长与 segment 比例生成 ASS/SRT
- **输出**：MP4 视频 + 剪映/CapCut 工程（可编辑交付）
---

## 环境要求

- Python ≥ 3.10
- **ffmpeg**：TTS（MP3→WAV 转换）、Render（preview.mp4）必需
- （可选）uchardet：用于自动检测 txt 编码
- （可选）SiliconFlow API Key：LLM 语义分镜、SpeechPlan、TTS
---

## 安装

### 1.1 项目标准方式

```bash
pip install -e ".[dev]"
```

适用场景：
- 本地开发
- 需要 `pytest`
- 希望直接以 editable 方式安装 `novel2comic`

### 1.2 运行依赖快速安装

```bash
pip install -r requirements.txt
```

适用场景：
- 只想快速安装运行依赖
- 不需要开发依赖

### 1.3 系统依赖

- **ffmpeg**：Render 阶段生成 `preview.mp4`；TTS 阶段把 MP3 转为 WAV
- 建议通过 conda 或系统包管理器安装，并保证 `ffmpeg` 在 PATH 中可用

---
## 快速开始

### 1. 预处理（脚本）

```bash
# 编码转 UTF-8（若源文件非 UTF-8）
python scripts/normalize_to_utf8.py --in_path /path/to/novel.txt --out_dir output/my_novel/utf8

# 按章节切分
python scripts/split_novel_to_chapters.py --in_path output/my_novel/utf8/novel.txt --out_dir output --novel_id my_novel

# 缩进规范化（可选）
python scripts/normalize_chapter_indent.py --dir output/my_novel/chapters --inplace
```

### 2. 创建 ChapterPack 并运行 Pipeline

```bash
# 从 chapters 批量创建 ChapterPack
novel2comic prepare --chapters_dir output/my_novel/chapters

# 运行到 segment 阶段（分镜切分）
novel2comic run --chapter_dir output/my_novel/ch_0001 --until segment
```

### 3. 运行完整音频流水线（TTS → 字幕 → 预览）

在项目根目录创建 `.env`：

```
SILICONFLOW_API_KEY=你的API密钥
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2

# TTS 默认 CosyVoice2，可切换说话人
SILICONFLOW_TTS_MODEL=FunAudioLLM/CosyVoice2-0.5B
SILICONFLOW_TTS_VOICE_NARRATOR=FunAudioLLM/CosyVoice2-0.5B:claire
SILICONFLOW_TTS_VOICE_MALE=FunAudioLLM/CosyVoice2-0.5B:benjamin
SILICONFLOW_TTS_VOICE_FEMALE=FunAudioLLM/CosyVoice2-0.5B:anna
NOVEL2COMIC_PROJECT_ROOT=/path/to/novel2comic
NOVEL2COMIC_ENV_FILE=/path/to/novel2comic/.env
```

运行到 render 阶段（需已完成 segment + plan）：

```bash
novel2comic run --chapter_dir output/my_novel/ch_0001 --until render
```

```bash
novel2comic run --chapter_dir output/my_novel/ch_0001 --from_stage image --until render
```

产出：`audio/chapter.wav`、`subtitles/chapter.ass`、`subtitles/chapter.srt`、`video/preview.mp4`。

冒烟测试（仅处理前 3 个 shots）：

```bash
python scripts/smoke_full_chain.py --chapter_dir output/my_novel/ch_0001 --limit_shots 3
```

---

## 命令说明

| 命令 | 说明 |
|------|------|
| `novel2comic init --chapter_dir <path>` | 创建空的 ChapterPack 目录骨架 |
| `novel2comic prepare --chapters_dir <path> [--chapter ch_0001]` | 从 chapters 批量创建 ChapterPack |
| `novel2comic run --chapter_dir <path> [--novel_id <id>] --until <stage>` | 运行 pipeline 到指定阶段 |

**Pipeline 阶段**：`ingest -> segment -> plan -> director_review -> anchors -> image -> tts -> align -> render -> export`

当前已实现：`ingest`, `segment`, `plan`, `director_review`, `anchors`, `image`, `tts`, `align`, `render`.
---

## 项目结构

```text
novel2comic/
├── pyproject.toml
├── requirements.txt
├── README.md
├── .env                       # 本地密钥文件（不提交）
├── configs/
├── docs/
├── scripts/
├── src/novel2comic/
└── tests/
```
---

## 输出目录约定

```text
output/<novel_id>/
  chapters/
  <chapter_id>/
```

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
---

## 配置体系概览

可变参数按阶段 / 服务分类到 `configs/*.yaml`，由 `core/config_loader.py` 统一加载。优先级：

**环境变量 > YAML > 代码默认**

| 文件 | 说明 |
|------|------|
| `siliconflow.yaml` | base_url、timeout_s、llm / tts / image / vlm 默认模型 |
| `stage_segment.yaml` | baseline split 与 refine 参数 |
| `stage_director_review.yaml` | 导演审阅开关与模型参数 |
| `stage_anchors.yaml` | 角色锚点 / 风格锚点参数 |
| `stage_image.yaml` | 图像生成参数与 VLM review 开关 |
| `stage_tts.yaml` | TTS 风格提示与 instruction 长度限制 |

密钥（如 `SILICONFLOW_API_KEY`）必须放在 `.env` 或系统环境变量中，不写进 YAML。

---

## 项目根目录与 .env 解析

这是本次可移植化改造的关键规则。

### 3.1 项目根目录自动解析

`core/io.find_project_root()` 会按以下顺序解析项目根目录：
1. `NOVEL2COMIC_PROJECT_ROOT`
2. 调用方显式传入的起点路径
3. 当前模块位置
4. 当前工作目录

识别项目根目录的标记：
- `pyproject.toml`
- `.git`
- `src/novel2comic/`

这意味着：
- 运行时不再依赖某个硬编码磁盘路径
- 也不再依赖“.env 一定存在”才能找到项目根目录

### 3.2 .env 解析

`core/io.find_env_file()` 规则：
- 优先 `NOVEL2COMIC_ENV_FILE`
- 否则使用 `<project_root>/.env`

### 3.3 建议写法

本地默认：

```bash
NOVEL2COMIC_PROJECT_ROOT=E:\novel2comic
NOVEL2COMIC_ENV_FILE=E:\novel2comic\.env
```

服务器默认：

```bash
NOVEL2COMIC_PROJECT_ROOT=/home/yourname/novel2comic
NOVEL2COMIC_ENV_FILE=/home/yourname/novel2comic/.env
```

通常不必显式设置；只有在以下场景建议使用：
- 从仓库外部目录调用脚本
- 同一台机器上维护多个 checkout
- 本地与服务器使用不同的密钥文件路径

---

## .env 示例

```dotenv
# 必需
SILICONFLOW_API_KEY=api-key

# 可选服务覆盖
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_TIMEOUT_S=120
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2
SILICONFLOW_TTS_MODEL=FunAudioLLM/CosyVoice2-0.5B
SILICONFLOW_TTS_VOICE_NARRATOR=FunAudioLLM/CosyVoice2-0.5B:claire
SILICONFLOW_TTS_VOICE_MALE=FunAudioLLM/CosyVoice2-0.5B:benjamin
SILICONFLOW_TTS_VOICE_FEMALE=FunAudioLLM/CosyVoice2-0.5B:anna
VLM_MODEL=Qwen/Qwen2.5-VL-32B-Instruct

# 阶段级覆盖
DIRECTOR_REVIEW_ENABLED=1
DIRECTOR_REVIEW_TEMPERATURE=0.2
TTS_USE_STYLE_PROMPT=endofprompt
IMAGE_MODE=draft
IMAGE_SIZE=1664x928
ANCHORS_ENABLED=1

# 路径覆盖（通常不需要）
NOVEL2COMIC_PROJECT_ROOT=E:\novel2comic
NOVEL2COMIC_ENV_FILE=E:\novel2comic\.env
```

说明：
- 大多数 dotenv 解析器支持 `KEY=value`
- `.env` 不应提交到 git

---

## 测试

```bash
pytest tests/ -v
```
---

## 文档

- [架构文档](docs/ARCHITECTURE.md)
- [配置参考](docs/CONFIG_REFERENCE.md)
- [命名约定](docs/NAMING_CONVENTIONS.md)
- [代码结构](docs/CODE_STRUCTURE.md)
- [变更日志](docs/CHANGELOG.md)
- [项目状态与推进计划](docs/PROJECT_STATUS.md)

---

## 开发状态

| 阶段 | 状态 |
|------|------|
| ingest / segment / plan / director_review / anchors / image / tts / align / render | ✅ 已实现 |
| export | 🚧 待实现 |
---

## License

MIT
