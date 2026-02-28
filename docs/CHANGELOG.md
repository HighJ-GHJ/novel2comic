# novel2comic 变更日志（CHANGELOG）

本文档记录项目的重大变更，便于版本控制与思路演进追溯。每次大改动请在此追加条目。

---

## 变更记录格式说明

每次变更请按以下结构书写：

```markdown
## [日期] 变更标题

### 背景 / 动机
（为何要做这次变更）

### 变更内容
（具体改了哪些文件、逻辑）

### 影响范围
（对现有功能、下游模块的影响）

### 后续待办
（如有）
```

---

## [2026-03-01] 文档与优化更新

### 背景 / 动机

- 项目文档需与当前实现状态同步
- 性能优化：TTS manifest 频繁写入、重复 project_root 查找

### 变更内容

| 模块 | 变更 |
|------|------|
| **README.md** | 补充 director_review、CosyVoice2 默认、TTS 说话人配置、CODE_STRUCTURE 链接 |
| **docs/ARCHITECTURE.md** | TTS 默认 CosyVoice2、说话人配置说明 |
| **docs/CONFIG_REFERENCE.md** | TTS 说话人切换说明 |
| **docs/CODE_STRUCTURE.md** | 新增代码结构树形图（Mermaid + ASCII） |
| **stages/tts.py** | save_manifest 每 5 个 shot 落盘一次，减少 I/O |
| **core/io.py** | 新增 find_project_root() |
| **stages/** | segment/plan/director_review/tts 统一使用 find_project_root |
| **director_review** | 合并双循环 |

---

## [2026-03-01] Director Review 阶段：节奏与转场审阅（patch-only）

### 背景 / 动机

- shot 间停顿固定 120ms，缺乏节奏变化
- 需在 TTS 前由 LLM 以导演视角审阅，输出 patch-only 的 `gap_after_ms` 等

### 变更内容

| 模块 | 变更 |
|------|------|
| **director_review/** | 新增 schema、prompt、client、apply、fallback |
| **stages/director_review.py** | 新 stage，位置 plan 之后、TTS 之前 |
| **stages/tts.py** | 读取 effective_shotscript，按 per-shot gap_after_ms 拼接 |
| **stages/align.py** | 读取 effective_shotscript，时间轴加入 gap |
| **core/io.py** | 新增 director_dir、director_review_json、shotscript_directed、effective_shotscript() |
| **core/manifest.py** | 新增 directed 阶段 |

### 影响范围

- TTS/Align 优先读取 `shotscript.directed.json`（不存在则回退 `shotscript.json`）
- 配置：`DIRECTOR_REVIEW_ENABLED`、`DIRECTOR_REVIEW_MODEL`、`DIRECTOR_REVIEW_APPLY_PATCH`
- LLM 失败时 fallback 规则：句末 250ms、省略号 600ms、block 边界 1200ms、默认 200ms

---

## [2026-02-28] 架构重构：依赖修正、CLI 增强、Segment 接入

### 背景 / 动机

架构审查发现若干问题：
1. **依赖方向错误**：`core/split_baseline.py` 依赖 `skills/refine_shot_split/schema.Shot`，基础层依赖业务层，违反依赖倒置
2. **CLI 硬编码**：`novel_id` 固定为 `"novel_001"`，多书场景不便
3. **流水线断裂**：`split_novel_to_chapters` 输出与 ChapterPack 之间无自动化衔接，需手动复制
4. **Refine 约束过严**：短章（如 1700 字）baseline 仅 15–20 shot，无法满足 min_shots=60，导致 refine 必然回退
5. **Segment 占位**：只写出空 shots，未接入 baseline + refine
6. **依赖缺失**：`python-dotenv` 未在 pyproject.toml 声明

### 变更内容

| 模块 | 变更 |
|------|------|
| **core/schemas/** | 新建 `core/schemas/shot.py`，定义 `Shot` 数据结构；core 定义，skills 使用 |
| **core/split_baseline.py** | 改为 `from novel2comic.core.schemas import Shot`，移除对 skills 的依赖 |
| **skills/refine_shot_split/schema.py** | `Shot` 改为从 `novel2comic.core.schemas` 导入；保留 `Constraints`、`Patch` |
| **skills/refine_shot_split/validator.py** | `validate_count_range` 新增 `effective_min`、`effective_max` 参数，支持短章放宽约束 |
| **skills/refine_shot_split/skill.py** | 计算 `effective_min = min(c.min_shots, len(base_shots))`，传入 validator |
| **pyproject.toml** | 添加 `python-dotenv>=1.0`；新增 `[project.optional-dependencies] dev = ["pytest>=7.0"]` |
| **cli.py** | `run` 增加 `--novel_id`，缺省从 `chapter_dir` 父目录推断；新增 `prepare` 子命令 |
| **stages/segment.py** | 接入 `split_baseline` + `RefineShotSplitSkill`；LLM 不可用时回退 baseline；输出真实 shots 到 shotscript.json |
| **tests/** | 新建 `test_core.py`、`test_skills.py`、`test_pipeline.py`，共 10 个用例 |

### 影响范围

- **向后兼容**：`skills` 内 `from .schema import Shot` 仍可用（schema 重新导出）
- **debug_refine_split.py**：无需修改，继续使用 `schema.Shot`、`schema.Constraints`
- **新增命令**：`novel2comic prepare --chapters_dir ... [--chapter ch_0001]` 可从 chapters 批量创建 ChapterPack

### 后续待办

- plan / tts / align / image / render / export 各阶段实现
- 考虑为 LLM Provider 定义 Protocol 抽象

---

## [历史] 项目初始化与前期实现

（根据 `docs/ARCHITECTURE.md` 第 7 节「当前实现状态」整理）

### 已完成

- 项目目录架构、CLI（init/run）、pipeline 框架
- 输入编码：GB18030 → UTF-8
- 章节切分：`split_novel_to_chapters.py`，按章节号命名 ch_0001.txt 等
- 章节缩进规范化：`normalize_chapter_indent.py`
- baseline split + refine_shot_split skill（含 SiliconFlow LLM 接入）
- IngestStage、SegmentStage（Segment 已接入 baseline+refine）

### 脚本与输出

- `scripts/normalize_to_utf8.py`：任意编码 → UTF-8
- `scripts/split_novel_to_chapters.py`：整本 → chapters
- `scripts/normalize_chapter_indent.py`：段首缩进统一
- `scripts/debug_refine_split.py`：调试 baseline + refine
- 输出：`output/<novel_id>/chapters/ch_*.txt`、`chapters_index.json`

---

---

## [2026-02-28] 目录与命名约定统一

### 背景 / 动机

架构审查发现 data/output、book_id/novel_id 混用，文档与实现不一致。

### 变更内容

| 项目 | 变更 |
|------|------|
| **configs/** | 新建目录，README 说明预留用途 |
| **scripts/split_novel_to_chapters.py** | `--book_id` 改为 `--novel_id`，默认 `novel_demo` |
| **docs/NAMING_CONVENTIONS.md** | 新建，统一目录结构、标识符、路径约定 |
| **docs/CONFIG_REFERENCE.md** | 统一 output/<novel_id>/ 路径；normalize_to_utf8 示例更新 |
| **scripts/normalize_to_utf8.py** | 示例路径改为 output/<novel_id>/utf8 |
| **tests/test_scripts.py** | 新增 split_novel_to_chapters --novel_id 测试 |

### 影响范围

- **向后不兼容**：`--book_id` 已移除，旧脚本需改为 `--novel_id`
- 文档与实现一致

### 后续待办

- 无

---

## [2026-02-28] 导演式朗读音频闭环（SpeechPlan → TTS → Align-Lite → Preview）

### 背景 / 动机

实现 `novel2comic run --until render` 完整流程，产出 chapter.wav、chapter.srt/ass、preview.mp4。

### 变更内容

| 模块 | 变更 |
|------|------|
| **core/quote_splitter.py** | 新增，按中文引号 "" 切分 raw_text 为 narration/quote segments |
| **core/speech_schema.py** | 新增，intensity/pace/pause 离散集合、narrator/quote 模板 |
| **core/audio_utils.py** | 新增，纯 stdlib wav 拼接（避免 pydub，兼容 Python 3.13） |
| **core/io.py** | 扩展 ChapterPaths：audio_shots_dir、audio_chapter_wav、subtitles_srt/ass、video_preview_mp4 |
| **skills/speech_plan/** | 新增，patch-only LLM 标签（schema/prompt/validator/applier/skill） |
| **stages/plan.py** | 新增，引号切分 + SpeechPlanSkill → 补齐 shot.speech |
| **providers/tts/siliconflow_tts.py** | 新增，SiliconFlow /audio/speech |
| **stages/tts.py** | 新增，按 segment 合成 shot wav，拼接 chapter.wav |
| **stages/align.py** | 新增，align-lite：按 shot 时长与 segment 比例生成 SRT/ASS |
| **stages/render.py** | 新增，ffmpeg 纯色背景 + chapter.wav + ass → preview.mp4 |
| **pipeline/orchestrator.py** | 接入 plan/tts/align/render |
| **scripts/smoke_audio_pipeline.py** | 新增，冒烟测试 |
| **tests/** | 新增 test_quote_splitter、test_speech_plan、test_align_lite |

### 影响范围

- manifest stage 顺序：planned → tts_done → aligned → rendered
- .env 需配置 SILICONFLOW_TTS_MODEL、SILICONFLOW_TTS_VOICE 等（见 CONFIG_REFERENCE）
- 依赖 ffmpeg（render 阶段）

### 后续待办

- image 阶段（ComfyUI 出图）
- export 阶段（剪映 Draft）

---

## [2026-02-28] TTS MP3→WAV 转换 + 文档同步

### 背景 / 动机

冒烟测试发现 SiliconFlow IndexTTS-2 实际返回 MP3（Content-Type: audio/mpeg），即使请求 `response_format=wav`。`wave.open()` 解析 MP3 报错 `file does not start with RIFF id`，导致 TTS 阶段所有 shot 失败。

### 变更内容

| 模块 | 变更 |
|------|------|
| **core/audio_utils.py** | 新增 `_ensure_wav()`：非 WAV（如 MP3）通过 ffmpeg 转为 WAV |
| **providers/tts/siliconflow_tts.py** | `synthesize()` 返回前调用 `_ensure_wav(r.content)` |
| **docs/** | ARCHITECTURE、CONFIG_REFERENCE、NAMING_CONVENTIONS、README 同步当前实现 |

### 影响范围

- TTS 阶段可正常产出 shot wav 与 chapter.wav
- 依赖系统 ffmpeg（与 Render 阶段相同）

### 后续待办

- 无

---

## [2026-02-28] TTS 全面切换 CosyVoice2 + 节奏/情绪/多音色修复

### 背景 / 动机

任务书要求：省略号不读、节奏改善、quote 按性别切换音色、Plan/TTS 失败不静默、字幕保留引号。

### 变更内容

| 模块 | 变更 |
|------|------|
| **core/tts_utils.py** | 新增 normalize_tts_input、get_tail_pause_ms、quote_inner_text；标点驱动停顿 |
| **core/speech_schema.py** | PACE_TO_SPEED 扩大（slow 0.88/fast 1.10）；build_style_prompt；emotion+intensity 模板 |
| **core/audio_utils.py** | concat_wavs_with_pauses 支持每段不同静音时长 |
| **core/manifest.py** | add_warning() 写入 status.warnings |
| **providers/tts/siliconflow_tts.py** | 默认 CosyVoice2；per-call voice；VOICE_NARRATOR/MALE/FEMALE；TTS_STYLE_MODE |
| **stages/tts.py** | normalize_tts_input、标点停顿、多音色、segment pace 覆盖、错误写 shots_index |
| **stages/plan.py** | SpeechPlan 失败写 manifest.warnings + logs/plan_error.json + 控制台 WARN |
| **scripts/smoke_tts_cosyvoice2.py** | 新增 CosyVoice2 TTS 冒烟测试 |
| **tests/** | test_tts_utils、test_voice_select |

### 影响范围

- .env 需配置 SILICONFLOW_TTS_VOICE_NARRATOR/MALE/FEMALE（或使用默认）
- 字幕仍用 raw_text（保留引号、省略号）；TTS 输入清洗后不含

### 后续待办

- 无

---

*后续变更请在此文件末尾追加新条目。*
