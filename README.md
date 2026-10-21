# Agent Eval

**把一次 AI 客服实验，做成可以查看依据、复测和复盘的项目经历。**

Agent Eval 是面向 AI 产品入门者的实践工作台。以模拟电商客服为场景，完成知识准备、回答评测、问题排查、一次修改和前后比较，再把实际做过的过程整理成求职素材。

- [在线演示](https://www.test.softcue.xyz/)：演示环境，功能可能落后于当前源码。
- [新手说明](README-evaluation-guide.md)：已有回答怎么检查、评分标准怎么用。
- [原理图解页面](AgentEvalFrontend/public/evaluation-guide.html)：本地启动后打开 `/evaluation-guide.html`。

源码功能更新至 **2026-10-21**。更新 GitHub 不会自动部署演示站；仓库 CI 只运行检查和构建。

## 适合谁

主要面向 18–24 岁、缺少项目经历，希望理解 AI 产品如何评测和迭代的求职者。工作台的用户是学习者，实验里模拟的客服服务电商购物者，这两个场景分别记录。

可以先看不需要模型 Key 的案例图解，再用自己的模型连接做真实实验。平台提供执行与记录能力；实验结果来自本次运行，不能直接当作商业效果或个人独立开发成果。

## 功能介绍

| 功能 | 可以做什么 |
| --- | --- |
| 准备知识与测试题 | 导入或编辑资料，保存知识版本；聊天试用，把对话变成待审核测试题，也可审核 AI 生成的资料与题目。 |
| 看结果 | 查看初测或复测，一次聚焦一道题，核对原问题、Agent 回答、判定理由和参考依据。失败、证据不足、未执行等状态单独展示。 |
| 试修改 | 选择五种改法之一，只改变一个变量。原题与方案并排，确认后保存，再分别应用和复测。 |
| 看变化 | 对照原题检查改善、退化和未变，记录保留、继续修改或不采用的决定。条件不一致时保留不可比较的原因。 |
| 运行日志 | 按改写、检索、重排、回答和评分查看保存的输入、输出、候选片段、用量与错误；可复制日志，查看不会重跑模型。 |
| 日志评测 | 直接导入前面完成的评测，也支持外部文件。固定已有回答，核对资料后评分、人工复核，或设置每日检查。 |
| 评测标准与校准 | 定义评分细则，保存独立人工判断，与模型评分对照；支持问题记录、协议版本与保留题验证。 |
| 新手图解 | 用示意图说明 RAG 评测原理，五种改法都有证据、修改、复测和取舍的教学案例。教学数据与真实实验分开。 |
| CSV 导出 | 导出初测、复测和前后比较，保留本次全部题目、原始判定、人工复核和版本信息。 |
| 整理项目 | 自动把保存的操作与结果整理成提问，复制给常用 AI，生成简历要点、面试讲述和项目复盘。历史材料仍可查看和导出。 |

### 五种改法

| 改法 | 改的是什么 |
| --- | --- |
| 资料重排（Rerank） | 结合问题重新阅读、排列已经找到的候选原文，再取前几条供客服回答；不能找回候选池里没有的资料。 |
| 查询改写 | 调整检索用的问句，尝试找到更适合原问题的资料，需检查是否偏离原意。 |
| 返回资料数量（Top K） | 调整交给 Agent 的片段条数，观察必要信息与干扰内容之间的取舍。 |
| 回答提示词 | 调整 Agent 怎样使用资料组织回答，保持评分标准不变。 |
| 知识库更新 | 保存新知识与索引版本，按后端检查保持其他控制条件一致，再用原题复测。 |

修改页的 **「复制提问给 AI」** 自动带上当前题目、原回答、判定、检索资料和拟改参数，请 AI 分析原理、是否适合及怎样复测。补充备注可选，无需先填写四段分析。

### 项目经历自动整理

「整理项目」以复制提问为主要入口：

1. 自动汇总当前实验已保存的初测、修改、应用、复测和比较记录。
2. 在提问中要求 AI 查阅牛客等网站的 AI 产品项目、第一手面经和岗位要求，列出实际参考链接。
3. 请 AI 根据本次事实写出简历项目经历、约两分钟面试讲述、项目复盘及追问回答。

提问在浏览器本地准备，不会自动发送给第三方或启动模型。是否能联网查找参考，取决于用户粘贴后使用的 AI。尚未复测、评分失败或没有商业数据的部分保留实际进度，不能改写成已经提升。

## 第一次使用

**准备 → 看结果 → 试修改 → 看变化 → 整理项目**

1. 在「新手入门」先了解资料如何被找到、交给 Agent，再由评分模型检查。
2. 在工作区设置填写提供商地址、模型和自己的 Key，测试连接。
3. 使用演示资料或保存自己的知识版本，审核测试题与参考答案。
4. 运行初测，先看答错或执行失败的题，核对实际提供的资料与完整参考规则。
5. 保存一个修改方案，应用后用原题复测，检查改善和退化。
6. 在「整理项目」复制提问，让 AI 根据记录帮助表达实际做过的事。

只想重新检查旧回答时，进入「日志与评分」。**旧回答重新评分与 Agent 重新回答是两种实验**：改评分规则后分数变化，不能证明客服能力提高。

## 结果怎么看

例如 8 道题中，3 道通过、4 道不通过、1 道评分失败：有效判定覆盖是 `7 / 8`，有效判定中的通过率是 `3 / 7`。评分失败单列，不能算通过，也不能隐去后宣称整批效果。

检索命中、回答是否有依据、用户任务是否解决分别记录。模型判定可能出错，平台提供人工复核和校准流程；这些功能不代表已经完成真实人工校准。一次运行也不能证明稳定性或因果关系。

## 技术与目录

前端使用 **Vue 3 + Vite**，后端使用 **Python 3.12 + FastAPI**。默认采用本地 Chroma / ONNX `all-MiniLM-L6-v2` 语义向量（384 维、CPU），保留明确选择的词汇检索对照，失败时不会静默切换。

实验保存题目、知识、索引、配置和评分协议快照。后台评测提交与查询进度分开，刷新后可接回已知任务。模型 Key 保存在后端进程内存，实验 JSON 不保存 Key。

```text
AgentEval/                  后端、公开演示资料与测试
  experiments/app.py        FastAPI 入口
  experiments/              实验、日志评分、校准、材料和后台任务
  evaluation/               执行结果、评分和证据检查
AgentEvalFrontend/          Vue 前端、单元测试与浏览器流程定义
  public/                   可独立访问的新手图解
examples/langsmith/         公开电商演示数据
scripts/langsmith-eval.py   可选 LangSmith 评测入口
requirements-runtime.txt   产品运行依赖
Dockerfile                  后端镜像
```

历史 `LEGACY_README.md`、旧 API、Memory 和监控模块保留用于溯源，当前入口以本文为准。

## 本地运行

需要 Python 3.12、Node.js 22 和 pnpm 10。从仓库根目录开始：

```sh
git clone https://github.com/KyrDur/agent-eval.git
cd agent-eval
```

终端一，启动后端：

```sh
cd AgentEval
python3.12 -m venv .venv
.venv/bin/python -m pip install -r ../requirements-runtime.txt
# 首次联网下载公开向量模型，之后使用本地缓存。
.venv/bin/python -c "from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2; ONNXMiniLM_L6_V2(preferred_providers=['CPUExecutionProvider'])(['model initialization'])"
.venv/bin/python -m uvicorn experiments.app:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

终端二，启动前端：

```sh
cd AgentEvalFrontend
pnpm install --frozen-lockfile
pnpm dev
```

打开 `http://127.0.0.1:5173`。前端 `/api` 代理至 `127.0.0.1:8000`，可通过 `AGENTEVAL_BACKEND_URL` 修改目标。

默认模式用于本机单用户开发，数据写入 `AgentEval/data/experiments/`，已被 Git 排除。保持一个后端 worker；重启后需重新配置模型 Key。连接、作答、改写、重排和评分可能产生模型调用，单纯查看和复制记录不会重跑。

## 测试

```sh
cd AgentEval
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q -rs
```

```sh
cd AgentEvalFrontend
pnpm test
pnpm build
```

测试使用公开演示数据、合成用例和本地模型替身，需向量模型缓存。部分历史回归需要私人的封存记录，缺少时明确跳过。工程测试通过不等于真实业务效果或 Judge 准确率已验证。

浏览器流程定义在 `AgentEvalFrontend/tests/browser/`，使用独立测试后端。完整的旧版浏览器流程尚未随最新布局全部复验，不能把单元测试结果当成整套浏览器验收。

## 公网部署

公开部署使用匿名独立工作区、HTTPS 和同源反向代理：

```sh
docker build -t agent-eval:latest .
docker volume create agent-eval-state
docker run -d --name agent-eval-backend \
  -p 127.0.0.1:8000:8000 \
  -v agent-eval-state:/state \
  -e AGENTEVAL_ANONYMOUS_WORKSPACES=1 \
  -e AGENTEVAL_WORKSPACE_DIR=/state/workspaces \
  -e AGENTEVAL_PUBLIC_ORIGIN=https://your-domain.example \
  -e AGENTEVAL_COOKIE_SECURE=1 \
  agent-eval:latest
```

`AGENTEVAL_PUBLIC_ORIGIN` 与公开站点一致。匿名工作区通过服务端 cookie 隔离，写请求检查来源。前端执行 `pnpm build` 后发布 `dist/`，反向代理将 `/api/` 去掉前缀转给后端，保留 Host、Origin 和 `X-Forwarded-Proto`。持久化 `/state`，不要让两个服务进程同时写同一组工作区。

## 进一步了解

- [日志评测、日常检查和评分标准](README-evaluation-guide.md)
- [检索实验与五种修改的技术说明](AgentEval/experiments/RETRIEVAL.md)
- [校准 API](AgentEval/experiments/CALIBRATION.md)
- [访问与使用统计](README-analytics.md)
- [可选 LangSmith 接入](LANGSMITH.md)
- [前端说明](AgentEvalFrontend/README.md) · [后端说明](AgentEval/README.md)

仓库提供源码、公开演示资料与测试，不包含本机工作区、私有实验、凭据、模型权重或部署运维记录。
