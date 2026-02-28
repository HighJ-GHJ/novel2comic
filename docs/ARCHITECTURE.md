# novel2comic 架构文档（ARCHITECTURE）

> 重大变更记录见 [CHANGELOG.md](./CHANGELOG.md)。

## 1. 项目目标

将中文小说 txt 全自动生成 ≥30min 的“动态漫画/动态分镜”长视频：
- 主体是静态图 + 轻动效（Ken Burns/视差/震屏/贴纸/转场）
- 旁白：TTS（Qwen-TTS）
- 字幕：音频 + 文本强制对齐（WhisperX/MFA）生成 ASS/SRT
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
(5) TTS：shot.tts_text -> audio（shot 级 or chapter 合并）
↓
(6) Align：audio + subtitle_text -> 字幕时轴（ASS/SRT）
↓
(7) Image：ComfyUI 出图（scene/shot）
↓
(8) Render：动效/字幕/音频 -> preview/final MP4（ffmpeg）
↓
(9) Export：剪映/CapCut Draft 工程结构


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
  - image：prompt/negative/style_tags/seed/size/ref_images/output_key
  - motion：Ken Burns/视差/震屏等动效参数
  - overlays：贴纸/气泡/大字特效等
  - sfx_tags：音效标签（可选）
  - quality / retry_policy：失败重试与质量档位

强约束：
- shot_id 必须稳定
- raw_text / tts_text / subtitle_text 必须区分
- 时间轴以真实音频为准（duration_policy = tts_driven）


### 3.2 ChapterPack v0.1（每章一个包，支持断点续跑）
每章一个目录，包含该章生成全过程的输入/中间产物/输出：
- shotscript.json：本章镜头脚本
- manifest.json：状态机与产物索引（断点续跑/复现）
- text/：章节文本与中间文本
- audio/：旁白与 shot 音频
- subtitles/：ASS/SRT 与对齐中间文件
- images/：出图与分层素材
- video/：preview/final 视频
- draft/：剪映/CapCut 工程结构
- logs/：阶段日志

建议目录结构（示意）：
output/<novel>/<chapter>/
  manifest.json
  shotscript.json
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


### 3.3 manifest.json v0.1（状态机与断点续跑）
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
- configs/：配置（providers/render_profile/默认参数）
- docs/：文档与示例
- scripts/：工具脚本（一次性/调试）
- src/novel2comic/：核心包
  - core/：数据结构、schema、基础处理
    - schemas/：ShotScript/ChapterPack/Manifest schema 定义
  - providers/：外部能力封装（llm/tts/image/align/render/export）
  - stages/：阶段实现（每阶段输入/输出/状态落盘）
  - pipeline/：编排（run/init、stage 调度、错误处理）
- tests/：单测与冒烟


## 5. Providers（外部能力接口）

### 5.1 LLM Provider
- 目标：用于 refine_shot_split / prompt 优化 / 文本改写等
- 当前：SiliconFlow API（deepseek-ai/DeepSeek-V3.2）或 DeepSeek 官方

### 5.2 TTS Provider
- 目标：shot.tts_text -> 音频
- 当前：Qwen-TTS（后续可扩展 voice clone、style）

### 5.3 Image Provider
- 目标：shot.image.prompt -> 场景图/角色图/分层图
- 当前：ComfyUI（工作流可固定模板 + 参数注入）

### 5.4 Align Provider
- 目标：audio + subtitle_text -> 时轴（ASS/SRT）
- 当前：WhisperX/MFA（择一，后续定）

### 5.5 Render Provider
- 目标：图片 + 动效 + 字幕 + 音频 -> 视频（preview/final）
- 当前：ffmpeg（MVP）；后续可扩展 AE/PR 工程导出

### 5.6 Export Provider
- 目标：输出剪映/CapCut Draft 工程结构
- 价值：可编辑交付（字幕样式/转场/配乐/贴纸二次创作）


## 6. Stages（阶段划分建议）

- stage00_normalize_input：原 txt 编码 -> UTF-8
- stage01_split_chapters：整本 -> chapters（按章节号落盘）
- stage02_normalize_chapters：缩进/空白归一化
- stage03_baseline_split：章节 -> base_shots（规则切）
- stage04_refine_shot_split：LLM -> patch -> refined_shots
- stage05_tts：refined_shots -> audio
- stage06_align：audio + subtitle_text -> ASS/SRT
- stage07_image：shots -> images（ComfyUI）
- stage08_render：合成 preview/final MP4
- stage09_export_draft：导出剪映/CapCut 工程


## 7. 当前实现状态（截至今日）

已完成：
- 项目目录架构初始化与 CLI 安装，可运行 init/run
- 输入编码问题定位：GB18030 -> UTF-8，已成功转码并验证
- 章节切分流程打通，并识别出“必须按章节号命名/排序”的正确需求
- 章节正文缩进不一致问题解决（TAB/全角空格混杂）并通过脚本规范化

待实现（下一步）：
- baseline split + refine_shot_split（patch 输出）
- SiliconFlow LLM 接入与调试脚本完善
- Qwen-TTS provider 接入并生成 audio
- 对齐字幕与 ffmpeg 渲染
- Draft 工程导出（剪映/CapCut）


## 8. 关键工程约定（必须遵守）

- 内部文本统一 UTF-8
- shot_id 稳定（复现/断点续跑关键）
- raw_text/tts_text/subtitle_text 分离
- 时间轴以音频真实时长为准（tts_driven）
- ChapterPack 路径相对根，所有产物可迁移归档
