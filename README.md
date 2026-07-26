# 🤖 AI 研究助手 Agent

基于 **DeepSeek + ReAct 循环 + Tavily 搜索** 的 AI Agent。具备 5 个工具、双记忆系统（短期+长期）、Planning 任务分解能力。自动搜索网页、调用 API、记忆对话、生成带来源引用的研究报告。

## 🧠 什么是 Agent？

Agent ≠ 普通的 LLM 对话。Agent 有自己的"手"——它能调用外部工具：

```
用户: "特斯拉最新股价是多少？"
  ↓
LLM: 这个问题需要联网搜索
  → 调用 search_web("特斯拉 股价")
  → 你的代码真正去搜网页
  → 搜索结果返回 LLM
  → LLM: "特斯拉当前股价 313 美元，来源 TradingView"
```

**LLM 决定做什么，你的代码真正去做，结果喂回 LLM 组织回答。**

## ✨ 功能

- 🔍 **网页搜索** — 通过 Tavily API 实时搜索互联网
- 🧮 **数学计算** — 支持复杂表达式求值
- 🌤️ **真实天气** — 通过 Open-Meteo API 查询实时天气（免费、无需注册）
- 🔄 **ReAct 循环** — Thought → Action → Observation，自动多步推理
- 🎯 **多工具自动选路** — LLM 自动判断该用哪个工具、传什么参数
- 🧠 **短期记忆** — 多轮对话保持上下文，自动清理中间过程
- 💾 **长期记忆** — ChromaDB 持久化存储，跨对话回忆之前的查询
- 📋 **Planning** — 任务分解：列计划 → 逐步执行 → 汇总回答
- 📖 **来源引用** — 回答附带信息来源链接

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`：

```ini
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
TAVILY_API_KEY=tvly-your-key-here
```

- **DeepSeek API Key**: [platform.deepseek.com](https://platform.deepseek.com) 申请
- **Tavily API Key**: [tavily.com](https://tavily.com) 免费注册，每月 1000 次额度

### 3. 运行

```bash
python src/agent.py
```

## 📖 使用方法

```
🤖 AI Agent 助手
输入 /quit 退出

你> 特斯拉最新股价是多少？
🤖 特斯拉当前股价 313.03 美元 | TradingView

你> 234 * 567 等于多少？
🤖 234 × 567 = 132,678

你> 量子计算有什么最新进展？
🤖 2025年量子计算六大关键进展：[详细报告]
```

输入 `/quit` 退出。

## 🔧 工具系统

Agent 当前拥有 5 个工具：

| 工具 | 功能 | 实现 |
|------|------|------|
| `search_web` | 搜索网页，返回标题+链接+摘要 | Tavily Search API |
| `calculate` | 计算数学表达式 | Python `eval()` |
| `get_weather` | 查询城市实时天气 | Open-Meteo API（免费，无需注册） |
| `save_to_memory` | 保存信息到长期记忆 | ChromaDB + sentence-transformers |
| `search_memory` | 搜索之前的对话记忆 | ChromaDB + sentence-transformers |

### 添加新工具

```python
# 1. 写函数
def get_stock_price(symbol: str) -> str:
    ...

# 2. 包装成 Tool
stock_tool = Tool(
    name="get_stock_price",
    description="查询股票实时价格",
    parameters={...},
    func=get_stock_price,
)

# 3. 注册
agent.add_tool(stock_tool)
```

## 📁 项目结构

```
AI Agent/
├── .env                      # API Key 配置（不提交）
├── requirements.txt          # Python 依赖
├── docs/                     # 复盘 + 思路文档
│   ├── Agent项目深度复盘.md
│   └── Agent项目整体思路回顾.md
└── src/
    ├── 01_agent_concepts_demo.py  # Agent 核心概念教学脚本
    └── agent.py                   # Agent 完整实现
```

`agent.py` 包含：
- `Tool` 类 — 工具定义（名称 + 描述 + 参数 Schema + 执行函数）
- `Agent` 类 — ReAct 循环引擎
  - `add_tool()` — 注册工具
  - `run()` — 执行 ReAct 循环（Thought → Action → Observation）
  - 短期记忆管理 — 自动清理 tool_calls 中间状态

## 🧩 Agent 工作流程

```
┌─────────────────────────────────────────┐
│                 用户提问                  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Step 1: LLM 分析问题 + 可用工具列表     │
│  → 决定：需要 search_web("特斯拉股价")    │
│  → 返回 JSON: {name, arguments}          │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Step 2: 你的代码真正执行函数             │
│  → Tavily API 搜索网页                   │
│  → 返回：标题 + 链接 + 内容              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Step 3: 结果喂回 LLM                    │
│  → LLM 判断：信息够了 → 组织回答          │
│  → 或：不够 → 换关键词再搜一次            │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│              带来源的完整回答             │
└─────────────────────────────────────────┘
```

## 🔧 技术栈

| 环节 | 技术 |
|------|------|
| LLM | DeepSeek API (deepseek-v4-pro) |
| Agent 框架 | 自建（ReAct 循环，不依赖 LangChain） |
| 网页搜索 | Tavily Search API |
| 天气查询 | Open-Meteo API（免费，无需注册） |
| 长期记忆 | ChromaDB + sentence-transformers |
| Embedding | all-MiniLM-L6-v2（本地运行） |

## 📚 三个项目的关系

```
Week 1: CLI AI 助手          → DeepSeek API 基础调用 + 流式输出
Week 2: RAG 知识库问答       → Embedding + ChromaDB 向量检索
Week 3: AI 研究助手 Agent    → ReAct + Tool Calling + 双记忆 + Planning

Week 2 的 ChromaDB + sentence-transformers 被 Week 3 复用为长期记忆系统
```
