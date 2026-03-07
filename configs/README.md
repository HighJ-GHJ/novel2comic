# configs/

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
