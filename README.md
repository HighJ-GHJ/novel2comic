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

```bash
git clone https://github.com/HighJ-GHJ/novel2comic.git
cd novel2comic
pip install -e .
```

开发模式（含 pytest）：

```bash
pip install -e ".[dev]"
```

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
```

运行到 render 阶段（需已完成 segment + plan）：

```bash
novel2comic run --chapter_dir output/my_novel/ch_0001 --until render
```

产出：`audio/chapter.wav`、`subtitles/chapter.ass`、`subtitles/chapter.srt`、`video/preview.mp4`。

冒烟测试（仅处理前 3 个 shots）：

```bash
python scripts/smoke_audio_pipeline.py --chapter_dir output/my_novel/ch_0001 --limit_shots 3
```

---

## 命令说明

| 命令 | 说明 |
|------|------|
| `novel2comic init --chapter_dir <path>` | 创建空的 ChapterPack 目录骨架 |
| `novel2comic prepare --chapters_dir <path> [--chapter ch_0001]` | 从 chapters 批量创建 ChapterPack |
| `novel2comic run --chapter_dir <path> [--novel_id <id>] --until <stage>` | 运行 pipeline 到指定阶段 |

**Pipeline 阶段**：`ingest` → `segment` → `plan` → `director_review` → `tts` → `align` → `image` → `render` → `export`

当前已实现：`ingest`、`segment`、`plan`、`director_review`、`tts`、`align`、`render`。

---

## 项目结构

```
novel2comic/
├── configs/          # 配置（预留）
├── docs/             # 文档
│   ├── ARCHITECTURE.md    # 架构说明
│   ├── CONFIG_REFERENCE.md
│   ├── NAMING_CONVENTIONS.md
│   └── CHANGELOG.md      # 变更记录
├── scripts/          # 预处理脚本
├── src/novel2comic/  # 核心包
│   ├── core/         # 数据结构、quote_splitter、speech_schema、audio_utils
│   ├── providers/    # LLM、TTS（SiliconFlow）
│   ├── pipeline/     # orchestrator
│   ├── director_review/  # 导演审阅（节奏、转场）
│   ├── stages/       # ingest、segment、plan、director_review、tts、align、render
│   └── skills/       # refine_shot_split、speech_plan
└── tests/
```

---

## 输出目录约定

```
output/<novel_id>/
├── chapters/           # 章节切分输出
│   ├── ch_0001.txt
│   └── chapters_index.json
├── ch_0001/            # ChapterPack（单章）
│   ├── manifest.json
│   ├── shotscript.json
│   ├── shotscript.directed.json   # Director Review 产出
│   ├── director/director_review.json
│   ├── text/chapter_clean.txt
│   ├── audio/
│   │   ├── chapter.wav       # 整章拼接音频
│   │   └── shots/<shot_id>.wav
│   ├── subtitles/chapter.ass, chapter.srt
│   └── video/preview.mp4
└── ch_0002/
    └── ...
```

详见 [docs/NAMING_CONVENTIONS.md](docs/NAMING_CONVENTIONS.md)。

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

---

## 开发状态

| 阶段 | 状态 |
|------|------|
| ingest / segment / plan / director_review / tts / align / render | ✅ 已实现 |
| image / export | 🚧 待实现 |

---

## License

MIT
