# Agent Eval 前端

Vue 3 / Vite，Agent Eval 的独立前端。导航按「准备 → 看结果 → 试修改 → 看变化 → 整理项目」组织；「日志与评分」检查已有回答与评分方法。

主要包含逐题结果与运行日志、五种修改的本题方案、新手原理图解、CSV 导出和项目整理提问。两处「复制提问给 AI」分别用于分析单题改法、整理项目求职表达，内容在浏览器本地准备。

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm test
pnpm build
```

开发站点默认 `http://127.0.0.1:5173`，`/api` 代理至 `http://127.0.0.1:8000`。完整运行、独立后端和浏览器测试配置见 [Agent Eval 说明](../README.md)。历史阶段说明保留在 [LEGACY_README.md](LEGACY_README.md)。
