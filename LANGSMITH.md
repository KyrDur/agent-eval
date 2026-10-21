# 电商 Agent 的 LangSmith 评测

可选接入使用当前产品的 `retrieve_context()`、`grounded_answer()`、本地 Chroma / ONNX 语义索引、检索指标和四维 Judge 协议。Agent 在本机运行，LangSmith 保存数据集、实验、模型子调用、检索证据和评测反馈。

## 安装与配置

从仓库根目录，在 Python 3.12 环境安装：

```sh
python -m pip install -r requirements-langsmith.txt
```

默认凭据文件为 `~/.config/agent-eval/langsmith.env`，权限应为 `600`。文件不在仓库中；API Key 不写入实验结果。也可用同名环境变量，环境变量优先。

```dotenv
LANGSMITH_API_KEY=填写你的LangSmithKey
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=Agent Eval 电商评测
AGENTEVAL_MODEL_API_KEY=填写模型提供商的Key
AGENTEVAL_MODEL_PROVIDER=openai-compatible
AGENTEVAL_MODEL_BASE_URL=https://api.deepseek.com/v1
AGENTEVAL_MODEL=deepseek-chat
AGENTEVAL_MAX_TOKENS=2200
AGENTEVAL_TEMPERATURE=0
```

LangSmith Key 和模型 Key 属于两个服务。LangSmith 浏览器登录不能替代脚本鉴权。

独立 Judge 可用 `AGENTEVAL_JUDGE_API_KEY`、`AGENTEVAL_JUDGE_BASE_URL`、`AGENTEVAL_JUDGE_MODEL` 和 `AGENTEVAL_JUDGE_PROVIDER` 指定；未填 Judge Key 时使用生成模型。`LANGSMITH_WORKSPACE_ID` 可选，默认使用 Key 绑定的工作区。

## 运行

只检查 LangSmith 鉴权，不调用模型：

```sh
python scripts/langsmith-eval.py --check
```

内置八题完整评测：

```sh
python scripts/langsmith-eval.py
```

macOS 可在安装依赖后双击 `scripts/运行电商LangSmith评测.command`，默认使用 `AgentEval/.venv/bin/python`；其他环境可通过 `AGENTEVAL_PYTHON` 指定解释器。

开启重排，在同一测试集上再运行一个实验：

```sh
python scripts/langsmith-eval.py --rerank --experiment-prefix '电商 RAG Rerank'
```

其他参数：`--rewrite`、`--top-k 5`、`--concurrency 1`、`--limit 2`、`--no-judge`、`--config /path/to/private.env`、`--data /path/to/ecommerce.json`。`--embedding` 可显式选择词汇向量作为对照；默认语义模型失败会停止，不自动降级。

结果保存在 `output/langsmith/<时间戳>-<内容hash>/`；`summary.json` 包含可打开的 LangSmith 实验及数据集链接，`results.json` 包含实际回答、证据、模型响应标识及完整 Judge 原始输出。每次创建独立目录，不改写旧记录。

首轮最多八次生成、八次 Judge。每开启一项改写或重排，每题再增加一次调用。生成和 Judge 均不自动重试；并发默认为 2，每个模型请求超时 90 秒。

## 数据与评分含义

`examples/langsmith/ecommerce.json` 来自前端的 `rag-demo.js`，保留原来的八条政策、八道题和人工编写的相关文档标签。它们是演示资料，不代表商家真实政策。自定义文件使用同一结构：`name`、`documents`、`cases`。

输入只包含题目、上下文和题目 ID。参考答案和相关文档标签仅供评测，不进入回答生成输入。完整知识库按版本冻结，测试集名称带内容 hash；重用数据集时核对已有每条输入与参考输出，发现修改会停止。

LangSmith 反馈分为：

- 检索：`hit_at_1`、`hit_at_3`、`mrr`、`recall_at_k`、`precision_at_k`、`ndcg_at_k`；沿用项目的固定候选池和去重口径。
- 四维 Judge：`faithfulness`、`conditions`、`relevance`、`actionability`，数值为 0 / 1 / 2。
- 可用性与判定：`judge_status`、`verdict`、`task_resolved`、`faithful_to_available`、`critical_errors`、`answer_pass`。

默认将项目已有的原文片段映射为 `A1` / `R1` / `P1` 等短编号，模型选择编号后再精确还原到原文、位置和 SHA256；使用现有校验器验证来源。未知编号和错误范围会被拒绝，不做模糊匹配。模型提供四维分数，代码调用现有 `final_verdict()` 按冻结阈值生成最终判定；原始输出和判定来源同时保存。这避免让模型抄写长 hash 或计算通过阈值。

`NA`、`INSUFFICIENT` 不转换成数值，`PENDING` 不计为通过；解析或证据校验失败记为 `UNAVAILABLE`。任一题执行失败或 Judge 不可用，脚本返回 `PARTIAL` 和非零退出码。追踪逐条提交，完成后通过新 SDK 查询接口核对云端根运行记录，并允许短暂的索引延迟。

结束时还会读回每条云端反馈，核对检索指标、四维评分及最终判定，补传遗漏项。沿用工作区已有的评分配置，不重新定义全局分数范围。本地保留完整精度，云端读取的四位小数分数按存储舍入核对。

这次接入的初始规则尚未经过独立人工校准。报告记录 `INITIAL_UNVALIDATED` 和独立人工参照数 0；同模型自评和演示题通过率不能证明真实业务效果。当前范围为电商知识问答，实际订单或退款执行能力需单独实现后再评测。

## 参考

- [LangSmith 异步评测](https://docs.langchain.com/langsmith/evaluation-async)
- [自定义追踪](https://docs.langchain.com/langsmith/annotate-code)
