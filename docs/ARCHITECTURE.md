# novel2comic 架构文档（ARCHITECTURE）

> 重大变更记录见 [CHANGELOG.md](./CHANGELOG.md)。

## 1. 项目目标

将中文小说 txt 全自动生成 ≥30min 的“动态漫画/动态分镜”长视频：
- 主体是静态图 + 轻动效（Ken Burns/视差/震屏/贴纸/转场）
- 旁白：TTS（SiliconFlow IndexTTS-2）
- 字幕：Align-Lite 按 shot 时长与 segment 比例生成 ASS/SRT（MVP 不做 WhisperX 强制对齐）
- 输出同时支持：
  - MP4（ffmpeg 渲染）
  - 剪映/CapCut 工程结构（Draft）用于可编辑交付

非目标（MVP 不做）：
- 全片逐帧动画
- 复杂角色骨骼动画与长镜头高一致性 I2V（后续可扩展）


## 2. 总体流水线（概念）

输入：整本小说 txt（任意编码）
↓
(0) Normalize 输入编码 -> UTF-8（内部标准）
↓
(1) Split：整本 -> chapters（按“第…章/回/节”）
↓
(2) Normalize chapter 排版（缩进/空白一致）
↓
(3) Baseline split：章节 -> base_shots（规则粗切）
↓
(4) Skill: refine_shot_split：LLM 语义理解 -> patch -> refined_shots
↓
(5) Plan：引号切分 + SpeechPlan（LLM patch）-> shot.speech（narration/quote 分段与朗读参数）
↓
(5.5) Director Review：LLM 导演审阅 -> patch-only（gap_after_ms、节奏、转场）-> shotscript.directed.json
↓
(6) TTS：shot.speech.segments -> 各 segment 合成 -> shot wav -> 按 gap_after_ms 拼接 chapter.wav
↓
(7) Align-Lite：shot 时长 + segment 比例 -> 字幕时轴（ASS/SRT）
↓
(8) Image：ComfyUI 出图（scene/shot）
↓
(9) Render：动效/字幕/音频 -> preview/final MP4（ffmpeg）
↓
(10) Export：剪映/CapCut Draft 工程结构


## 3. 关键中间表示

### 3.1 ShotScript schema v0.1（唯一上游结构化输入）
ShotScript 是全流程上游“镜头脚本”，用来驱动后续所有阶段（TTS/Image/Render/Export），核心字段：
- meta：书名/章节/版本
- render_profile：渲染参数（timebase、fps、分辨率、duration_policy 等）
- characters：角色表（speaker、形象描述、风格 tags 等）
- shots：镜头数组（核心）
  - shot_id（稳定 ID，复现与断点续跑关键）
  - block_id / order（章节内顺序与分组）
  - text：
    - raw_text：原始小说片段（溯源）
    - tts_text：旁白合成用文本（可改写、去口水词）
    - subtitle_text：字幕用文本（可改写、分行友好）
  - emotion / tts_params：情绪、语速、能量等（可选）
  - gap_after_ms：该 shot 结束后的停顿（ms），Director Review 或 fallback 规则填充
  - image：prompt/negative/style_tags/seed/size/ref_images/output_key
  - motion：Ken Burns/视差/震屏等动效参数
  - overlays：贴纸/气泡/大字特效等
  - sfx_tags：音效标签（可选）
  - quality / retry_policy：失败重试与质量档位

强约束：
- shot_id 必须稳定
- raw_text / tts_text / subtitle_text 必须区分
- 时间轴以真实音频为准（duration_policy = tts_driven）


### 3.2 shot.speech 结构（Plan 阶段产出）

Plan 阶段为每个 shot 补齐 `speech` 字段，供 TTS 与 Align 使用：

```json
{
  "speech": {
    "default": { "pace": "normal", "pause_ms": 80, "intensity": 0.35, ... },
    "segments": [
      { "seg_id": "s0", "kind": "narration", "raw_text": "旁白文本", "tone": "neutral", ... },
      { "seg_id": "s1", "kind": "quote", "raw_text": "\"对话内容\"", "gender_hint": "male", "tone": "stern", ... }
    ]
  }
}
```

- `quote_splitter`：按中文引号 "" 或 「」 切分 raw_text 为 narration/quote
- `SpeechPlan` skill：LLM patch-only，为 segment 打标签（tone、gender_hint、pace 等）
- TTS 按 segment 合成，narration 用 `NARRATOR_TEMPLATE`，quote 用 `get_quote_style_prompt(gender_hint, tone)`


### 3.3 ChapterPack v0.1（每章一个包，支持断点续跑）
每章一个目录，包含该章生成全过程的输入/中间产物/输出：
- shotscript.json：本章镜头脚本（Plan 产出）
- shotscript.directed.json：Director Review 合并补丁后的镜头脚本（TTS/Align/Render 实际读取）
- manifest.json：状态机与产物索引（断点续跑/复现）
- director/：Director Review 产出
  - director_review.json：LLM 审阅原始输出
- text/：章节文本与中间文本
- audio/：旁白与 shot 音频
- subtitles/：ASS/SRT 与对齐中间文件
- images/：出图与分层素材
- video/：preview/final 视频
- draft/：剪映/CapCut 工程结构
- logs/：阶段日志

建议目录结构（示意）：
output/<novel_id>/<chapter_id>/
  manifest.json
  shotscript.json
  shotscript.directed.json   # Director Review 产出，存在则 TTS/Align 优先使用
  director/
    director_review.json
  text/
  audio/
    chapter.wav
    shots/
  subtitles/
    chapter.ass
    chapter.srt
    align/
  images/
    scene_*.png
    layers/
  video/
    preview.mp4
    final.mp4
  draft/
    jianying/
      draft_content.json
      draft_meta_info.json
      materials/
  logs/


### 3.4 manifest.json v0.1（状态机与断点续跑）
manifest 记录：
- 已完成 stage 列表 / failed stage
- durations（耗时）
- providers（使用了哪些 provider/模型）
- artifacts 路径
- shots_index：shot_id -> 音频/图片/seed/耗时/状态

用途：
- 复现（同 seed/同 prompt）
- 局部重做（只重做某几个 shot）
- 失败恢复（从上一次成功 stage 继续）


## 4. 代码结构与职责

项目根目录结构：

```
novel2comic/
├── configs/           # 配置（预留）
├── docs/              # 文档
├── scripts/           # 预处理脚本 + smoke_audio_pipeline.py
└── src/novel2comic/
    ├── core/          # 数据结构、基础处理
    │   ├── schemas/   # Shot 等（core 定义，skills 使用）
    │   ├── manifest.py
    │   ├── io.py      # ChapterPaths（路径约定）
    │   ├── quote_splitter.py   # 引号切分 narration/quote
    │   ├── speech_schema.py    # 朗读参数常量与模板
    │   ├── audio_utils.py      # wav 拼接、MP3→WAV 转换
    │   └── split_baseline.py
    ├── providers/    # 外部能力封装
    │   ├── llm/       # SiliconFlow
    │   └── tts/       # SiliconFlow IndexTTS-2
    ├── director_review/  # 导演审阅（patch-only 节奏与转场）
    │   ├── schema.py / prompt.py / client.py / apply.py / fallback.py
    ├── stages/        # 阶段实现
    │   ├── ingest.py / segment.py / plan.py / director_review.py / tts.py / align.py / render.py
    │   └── base.py    # StageContext
    ├── pipeline/      # orchestrator（stage 调度）
    ├── skills/        # refine_shot_split、speech_plan
    └── cli.py
```


## 5. Providers（外部能力接口）

### 5.1 LLM Provider
- 目标：refine_shot_split（分镜语义修正）、SpeechPlan（朗读参数 patch）、Director Review（节奏与转场 patch）
- 当前：SiliconFlow API（deepseek-ai/DeepSeek-V3.2）
- 代码：`providers/llm/siliconflow_client.py`

### 5.2 TTS Provider
- 目标：shot.speech.segments -> 各 segment 合成 -> shot wav
- 当前：SiliconFlow `/audio/speech`（默认 CosyVoice2-0.5B，支持 IndexTTS-2）
- 策略：API 可能返回 MP3，代码内用 ffmpeg 转为 WAV 再拼接（`core/audio_utils._ensure_wav`）
- 说话人：`.env` 配置 `SILICONFLOW_TTS_VOICE_NARRATOR`、`VOICE_MALE`、`VOICE_FEMALE` 切换
- 代码：`providers/tts/siliconflow_tts.py`

### 5.3 Image Provider
- 目标：shot.image.prompt -> 场景图/角色图/分层图
- 当前：ComfyUI（工作流可固定模板 + 参数注入，待实现）

### 5.4 Align Provider（Align-Lite）
- 目标：shot 时长 + segment 比例 -> 字幕时轴（ASS/SRT）
- 当前：Align-Lite（无 WhisperX/MFA）：按 shot wav 时长与 segments 字符比例分配时间
- 策略：quote 段字幕保留引号；后续可扩展 WhisperX 强制对齐
- 代码：`stages/align.py`

### 5.5 Render Provider
- 目标：纯色背景 + chapter.wav + ass -> preview.mp4
- 当前：ffmpeg（MVP）；依赖系统安装 ffmpeg
- 代码：`stages/render.py`

### 5.6 Export Provider
- 目标：输出剪映/CapCut Draft 工程结构
- 状态：待实现


## 6. Stages（阶段划分与实现）

Pipeline 阶段顺序（`orchestrator.STAGE_ORDER`）：

| 阶段 | 实现 | 职责 |
|------|------|------|
| ingest | `stages/ingest.py` | 创建 manifest、复制 chapter_clean.txt |
| segment | `stages/segment.py` | baseline split + refine_shot_split -> shotscript.json |
| plan | `stages/plan.py` | quote_splitter + SpeechPlan -> 补齐 shot.speech |
| director_review | `stages/director_review.py` | LLM 导演审阅 -> patch-only（gap_after_ms 等）-> shotscript.directed.json |
| tts | `stages/tts.py` | 按 segment 合成 shot wav，按 gap_after_ms 拼接 chapter.wav |
| align | `stages/align.py` | 按 shot 时长、gap 与 segment 比例生成 chapter.ass / chapter.srt |
| image | 待实现 | ComfyUI 出图 |
| render | `stages/render.py` | ffmpeg 生成 preview.mp4 |
| export | 待实现 | 剪映/CapCut Draft 工程 |

预处理脚本（独立于 pipeline）：
- `normalize_to_utf8.py`：原 txt 编码 -> UTF-8
- `split_novel_to_chapters.py`：整本 -> chapters
- `normalize_chapter_indent.py`：缩进/空白归一化


## 7. 当前实现状态（截至 2026-03-01）

### 已完成

| 模块 | 说明 |
|------|------|
| **CLI / Pipeline** | init、prepare、run --until；orchestrator 调度 ingest→segment→plan→tts→align→render |
| **Ingest** | 创建 manifest、复制 chapter_clean.txt |
| **Segment** | baseline split + refine_shot_split（SiliconFlow LLM）；LLM 不可用时回退 baseline |
| **Plan** | quote_splitter（按 "" 切分 narration/quote）+ SpeechPlan skill（LLM patch 朗读参数）→ shot.speech |
| **Director Review** | LLM 导演审阅（节奏、转场）；patch-only 输出 gap_after_ms 等；LLM 失败时 fallback 规则 |
| **TTS** | SiliconFlow IndexTTS-2；segment 级合成 → shot wav → 按 gap_after_ms 拼接 chapter.wav；MP3→WAV 转换（ffmpeg） |
| **Align-Lite** | 按 shot 时长与 segment 字符比例生成 ASS/SRT；quote 段保留引号 |
| **Render** | ffmpeg 纯色背景 + chapter.wav + ass → preview.mp4 |
| **core** | quote_splitter、speech_schema、audio_utils（wav 拼接 + MP3→WAV）、io（ChapterPaths） |
| **skills** | refine_shot_split、speech_plan（patch-only） |
| **providers** | llm（SiliconFlow）、tts（SiliconFlow IndexTTS-2） |
| **scripts** | smoke_audio_pipeline.py（冒烟测试） |

### 待实现

- image 阶段（ComfyUI 出图）
- export 阶段（剪映/CapCut Draft 工程）
- WhisperX 强制对齐（可选，替代 Align-Lite）


## 8. 关键工程约定（必须遵守）

- 内部文本统一 UTF-8
- shot_id 稳定（复现/断点续跑关键）
- raw_text/tts_text/subtitle_text 分离
- 时间轴以音频真实时长为准（tts_driven）
- ChapterPack 路径相对根，所有产物可迁移归档
