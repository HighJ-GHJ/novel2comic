# novel2comic 配置参考（CONFIG_REFERENCE）

> 目录与命名约定详见 [NAMING_CONVENTIONS.md](./NAMING_CONVENTIONS.md)。

## 1. 依赖与安装入口

当前仓库有两种依赖安装入口：

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

## 2. 配置体系概览

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

## 3. 项目根目录与 .env 解析

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

## 4. .env 示例

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

## 5. 阶段配置重点

### 5.1 Segment

配置文件：`configs/stage_segment.yaml`

关键字段：
- `split_baseline.min_chars`
- `split_baseline.soft_target`
- `split_baseline.hard_cut`
- `refine_shot_split.min_shots`
- `refine_shot_split.max_shots`

### 5.2 Director Review

配置文件：`configs/stage_director_review.yaml`

关键字段：
- `enabled`
- `apply_patch`
- `model`
- `temperature`

### 5.3 Anchors

配置文件：`configs/stage_anchors.yaml`

关键字段：
- `enabled`
- `topk_chars`
- `default_gender`
- `image_size`
- `steps`
- `cfg`

### 5.4 Image

配置文件：`configs/stage_image.yaml`

关键字段：
- `mode`
- `provider`
- `image_size`
- `steps`
- `cfg`
- `max_attempts`
- `chain_max_hops`
- `use_vlm_review`
- `review_max_attempts`

### 5.5 TTS

配置文件：`configs/stage_tts.yaml`

关键字段：
- `instruction_max_len`
- `use_style_prompt`

---

## 6. 运行时调用关系

当前与配置 / 路径强相关的调用链路如下：

- `core/config_loader.py`：负责读取 `configs/*.yaml`
- `providers/llm/siliconflow_client.py`：读取项目根和 `.env`
- `providers/tts/siliconflow_tts.py`：读取项目根和 `.env`
- `providers/image/image_qwen.py`：读取项目根和 `.env`
- `providers/image/image_flux.py`：读取项目根和 `.env`
- `providers/vlm/siliconflow_vlm.py`：读取项目根和 `.env`
- `scripts/smoke_full_chain.py`：通过 `find_project_root()` 运行整个链路

统一后带来的效果：
- 不再需要把脚本放在固定目录执行
- 不再要求本地和服务器保持同样的绝对路径
- provider 与 stage 对路径解析的认知一致

---

## 7. 输出目录约定

统一使用：

```text
output/<novel_id>/
  chapters/
  <chapter_id>/
```

单章 ChapterPack 典型结构：

```text
output/<novel_id>/<chapter_id>/
  manifest.json
  shotscript.json
  shotscript.directed.json
  text/chapter_clean.txt
  audio/chapter.wav
  audio/shots/<shot_id>.wav
  subtitles/chapter.ass
  subtitles/chapter.srt
  images/anchors/
  images/shots/
  video/preview.mp4
```

这些路径统一由 `core/io.ChapterPaths` 维护，不应在业务代码中手写散落字符串。

---

## 8. 多机器开发建议

- 本地和服务器都以仓库根目录为工作副本，不共享绝对路径假设
- 每台机器维护自己的 `.env`
- 如需统一脚本入口，优先用 `python -m novel2comic ...`
- 如需从仓库外部调用脚本，设置 `NOVEL2COMIC_PROJECT_ROOT`
- 不要在代码里写死 `E:\...`、`C:\...`、`/home/...` 这类机器专属路径

---

*最后更新：2026-03-07*