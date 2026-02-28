# novel2comic 配置参考（CONFIG_REFERENCE）

> 目录与命名约定详见 [NAMING_CONVENTIONS.md](./NAMING_CONVENTIONS.md)。

## 1. 环境与密钥管理

### 1.1 系统依赖
- **ffmpeg**：Render 阶段生成 preview.mp4；TTS 阶段将 SiliconFlow 返回的 MP3 转为 WAV。需在系统 PATH 中可用。

### 1.2 .env（项目内 dotenv）
本项目使用 `.env` 存储密钥与服务地址（不要求 export 环境变量）：

示例：
SILICONFLOW_API_KEY=api-key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2

# TTS（plan/tts 阶段）- 默认 CosyVoice2
# 切换说话人：修改 VOICE_NARRATOR（旁白）、VOICE_MALE（男性对话）、VOICE_FEMALE（女性对话）
SILICONFLOW_TTS_MODEL=FunAudioLLM/CosyVoice2-0.5B
SILICONFLOW_TTS_VOICE_NARRATOR=FunAudioLLM/CosyVoice2-0.5B:claire
SILICONFLOW_TTS_VOICE_MALE=FunAudioLLM/CosyVoice2-0.5B:benjamin
SILICONFLOW_TTS_VOICE_FEMALE=FunAudioLLM/CosyVoice2-0.5B:anna
SILICONFLOW_TTS_SAMPLE_RATE=24000
SILICONFLOW_TTS_RESPONSE_FORMAT=wav
SILICONFLOW_TIMEOUT_S=120

# style_prompt 模式：endofprompt（默认，短指令+<|endofprompt|>+正文）| none | prefix
# 文档要求 instruction 简短（~10 字）、输入不加空格
TTS_USE_STYLE_PROMPT=endofprompt

# Director Review（plan 之后、TTS 之前）
DIRECTOR_REVIEW_ENABLED=1
DIRECTOR_REVIEW_MODEL=
DIRECTOR_REVIEW_TEMPERATURE=0.2
DIRECTOR_REVIEW_APPLY_PATCH=1

**注意**：API 可能返回 MP3，代码在 `core/audio_utils._ensure_wav` 中通过 ffmpeg 自动转为 WAV。

说明：
- 大多数 dotenv 解析器支持 `KEY=value`，不需要引号
- 只有当 value 含空格/特殊字符时，才建议加引号
- `.env` 不应提交到 git（建议在 .gitignore 中忽略）


## 2. 关键参数（MVP 推荐）

### 2.1 Baseline split（规则粗切）
目的：把章节文本先粗切成相对稳定的片段，供 LLM refine。
- min_chars：最小片段阈值（过短不切）
- soft_target：期望片段长度（尽量接近）
- hard_cut：硬上限（超过则强制切）

典型用途：
- 控制 LLM 输入长度，避免超长段落拖垮 refine
- 控制 shot 粒度，避免后续 TTS/字幕过长不适合观看

### 2.2 Refine（refine_shot_split）约束
目的：让 LLM 在语义理解下矫正切分边界，并输出 patch。
- min_shots / max_shots：每章 shot 数约束（当前目标 60–120）
- patch_only：强制输出 patch，不允许整章重写
- keep_raw_alignment：保留 raw_text 片段可追溯性（避免编造）

建议：
- 小说每章几千字，真实视角切换不多
- 更合理的流程：代码粗切 -> LLM 语义修正 -> patch 输出


## 3. 文件与脚本清单（当前已用到）

### 3.1 scripts/normalize_to_utf8.py（建议保留）
用途：
- 把任意编码 txt 标准化为 UTF-8
- 推荐通过 uchardet 自动识别编码（已验证可识别 GB18030）

输入/输出（路径任意，建议与 output 统一）：
- 输入：任意 txt 路径
- 输出：`--out_dir` 指定，建议 `output/<novel_id>/utf8/`

示例：
```bash
python scripts/normalize_to_utf8.py --in_path /path/to/raw.txt --out_dir output/xuanjianxianzu/utf8
```


### 3.2 scripts/split_novel_to_chapters.py
用途：
- 整本小说 -> 按章节标题切分成多个章节文件
- 章节命名必须按章节号作为主键：
  - 第一章 -> ch_0001.txt
  - 第一千零九十七章 -> ch_1097.txt
- 前言/简介/广告等无章节头内容输出为 front_matter.txt
- 生成 chapters_index.json（按章节号排序）

参数：
- `--in_path`：输入 txt（UTF-8）
- `--out_dir`：输出根目录（默认 output）
- `--novel_id`：小说 ID，输出到 output/<novel_id>/chapters/（默认 novel_demo）


### 3.3 scripts/normalize_chapter_indent.py
用途：
- 修复章节文本段首缩进不一致问题（TAB/全角空格混杂）
规则（当前约定）：
- 去掉行首 TAB
- 正文段首统一两个全角空格（\u3000\u3000）
- 章节标题行不缩进


### 3.4 scripts/debug_refine_split.py（调试用）
用途：
- 读入单章文本
- baseline split -> base_shots
- 调用 SiliconFlow LLM -> 输出 patch/refined shots
- 打印统计与预览，便于 prompt/参数迭代

### 3.5 scripts/smoke_audio_pipeline.py（冒烟测试）
用途：
- 对 ChapterPack 跑 `novel2comic run --until render`
- 临时截断 shotscript 为前 N 个 shots（`--limit_shots`），跑完后恢复
- 检查 chapter.wav、chapter.ass、chapter.srt、preview.mp4 是否存在

示例：
```bash
python scripts/smoke_audio_pipeline.py --chapter_dir output/xuanjianxianzu/ch_0001 --limit_shots 3
```

前置条件：`.env` 配置 SILICONFLOW_API_KEY、SILICONFLOW_BASE_URL；系统安装 ffmpeg。


## 4. 输出目录与命名约定

统一使用 `output/<novel_id>/` 作为单本小说的输出根目录。

### 4.1 章节切分输出
output/<novel_id>/chapters/
  front_matter.txt
  ch_0001.txt
  ch_0002.txt
  ...
  chapters_index.json

说明：
- `novel_id`：小说唯一标识（如 xuanjianxianzu）
- chapters_index.json 记录每个章节文件的章节号/标题/路径/行数等

### 4.2 ChapterPack（pipeline 输出）
output/<novel_id>/<chapter_id>/
  manifest.json
  shotscript.json
  text/
    chapter_clean.txt
  audio/
    chapter.wav          # 整章拼接音频（TTS 阶段产出）
    shots/               # 分镜级 wav
      <shot_id>.wav      # 如 ch_0001_shot_0000.wav
  subtitles/
    chapter.ass          # ASS 字幕（Align 阶段产出）
    chapter.srt          # SRT 字幕
    align/
  images/
    layers/
  video/
    preview.mp4          # 预览视频（Render 阶段产出）
  draft/
  logs/

说明：
- `chapter_id`：章节标识（如 ch_0001），与 chapters/ 下文件名对应
- 音频路径由 `core/io.ChapterPaths` 定义


## 5. 渲染与交付关键参数（待落地但需预留）

### 5.1 render_profile（建议字段）
- timebase_ms：时间基准（毫秒）
- fps：输出帧率（24/30）
- resolution：最终 1920×1080（MVP 可先 1280×720）
- duration_policy：tts_driven（以音频真实时长决定镜头长度）
- motion_defaults：Ken Burns 缩放/平移参数范围

### 5.2 Draft（剪映/CapCut）导出参数
- timeline_unit：以 ms 为主
- materials：图片/音频/字幕素材路径相对 ChapterPack
- tracks：视频轨/音频轨/字幕轨
- subtitle_style：ASS 模板或 Draft 内样式映射


## 6. 已知输入风险与建议策略

- txt 可能混入后期章节/重复内容/广告块
  - 建议在 split 阶段支持按章节号过滤（min_no/max_no）
- 不同站点 txt 的章节头格式不同
  - 建议对章节标题正则做可配置（configs/）
- 为保证可追溯，raw_text 片段应保持 substring 可定位
  - refine 输出 patch 时必须避免“编造与大改写”
