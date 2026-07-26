# Agent 项目深度复盘

> 复盘时间：2026-07-25（更新）
> 项目：AI 研究助手 Agent（完整版：5 工具 + 短期记忆 + 长期记忆 + Planning）

---

## 一、完整数据流追踪

追踪"特斯拉最新股价是多少？"从输入到回答的完整路径：

```
用户: "特斯拉最新股价是多少？"
  │
  ├─ agent.py:run()  ← Agent.run() 入口
  │
  ├─ 追加 System Prompt (首次) + User Message
  │   messages = [
  │     {"role": "system", "content": "你是一个AI研究助手..."},
  │     {"role": "user", "content": "特斯拉最新股价是多少？"}
  │   ]
  │
  ├─ ReAct Step 1:
  │   ├─ client.chat.completions.create(
  │   │     model="deepseek-v4-pro",
  │   │     messages=[...],
  │   │     tools=[search_web, calculate, get_weather]  ← 3个工具的描述
  │   │   )
  │   │
  │   ├─ LLM 返回: msg.tool_calls = [
  │   │     {function: {name: "search_web",
  │   │      arguments: '{"query":"特斯拉 最新股价 2025","max_results":3}'}}
  │   │   ]
  │   │
  │   ├─ msg 追加到 messages (role: "assistant", 含 tool_calls)
  │   │
  │   └─ 执行: search_web(query="特斯拉 最新股价 2025", max_results=3)
  │       → Tavily API → 返回 3 条搜索结果
  │       → 追加到 messages (role: "tool")
  │
  ├─ ReAct Step 2:
  │   ├─ client.chat.completions.create(messages=[..., tool_result])
  │   ├─ LLM 返回: msg.tool_calls = None  ← 信息够了！
  │   └─ return msg.content
  │       → "特斯拉当前股价 313.03 美元 | 来源 TradingView"
  │
  └─ 打印回复
```

**关键观察：** 整个循环中，`messages` 列表在增长。LLM 每次都能看到之前的搜索历史和结果，所以能判断"信息够了"。

---

## 二、代码中的 Bug

### 🟢 已修复 Bug

| Bug | 原因 | 修复 |
|-----|------|------|
| `search_web` return 在 for 里面 | 缩进错误 | `return` 移出循环 |
| `[i+1` 缺 `]` | 格式遗漏 | 补上 `]` |
| `msg` 被 append 两次 | 复制粘贴残留 | 删重复行 |
| `parameters` 拼成 `paramaters` | 少一个 e | 改正拼写 |
| `client` 变量名被 TavilyClient 覆盖 | 同名变量 | 改名 `tavily` |
| `msg` 存为对象而非 dict | `ChatCompletionMessage` 不可下标 | 使用 `msg.model_dump()` |
| `memory.get()` 空集合报错 | ChromaDB 空集合调用 | 改用 `memory_counter` 自增 ID |
| `tollist()` 拼写错误 | 多一个 l | 改为 `tolist()` |
| `memory_db/` 被提交到 Git | .gitignore 遗漏 | 添加到 .gitignore |

### 🟡 遗留问题

| 问题 | 风险 | 修复方向 |
|------|------|---------|
| `eval()` 安全风险 | 恶意代码注入 | 替换为 `ast.literal_eval()` |
| LLM 假装执行工具 | 说"已保存"但没调函数 | System Prompt 硬指令 |
| 消息历史无限增长 | 长对话撑爆上下文窗口 | 截断早期消息 |
| 无流式输出 | 等待完整回复 | 改用 `stream=True` |

---

## 三、架构评价

```
最终架构：

  agent.py (~250 行)
    ├── 外部依赖: DeepSeek(LLM) + Tavily(搜索) + Open-Meteo(天气)
    ├── 本地依赖: ChromaDB(长期记忆) + sentence-transformers(Embedding)
    ├── Tool 类 — 工具定义
    ├── Agent 类 — ReAct 循环 + 短期记忆清理
    ├── 5 个工具: search_web, calculate, get_weather, save_to_memory, search_memory
    └── CLI 交互循环 + Planning(System Prompt)
```

**优点：**
- 一个文件就能跑，部署简单
- 自建 Agent 框架，不依赖 LangChain/CrewAI —— **面试加分项**
- 5 个工具覆盖搜索、计算、天气、记忆存取
- 短期记忆（消息清理）+ 长期记忆（ChromaDB）双记忆系统
- Planning 能力通过 System Prompt 工程实现，不增加代码复杂度

**缺点：**
- 工具定义和交互代码混在一起，加功能时容易乱
- 消息历史无限增长（长对话会撑爆上下文窗口）
- 没有流式输出
- 每次启动都加载 ChromaDB + sentence-transformers，冷启动慢

**和 LangChain 的对比：**

| | 你的实现 | LangChain |
|------|------|------|
| Agent 循环 | 30 行 for 循环 | 框架封装，10 行配置 |
| 工具定义 | Tool 类 + JSON Schema | @tool 装饰器 |
| 理解深度 | ✅ 知道每行在干什么 | ❌ 框架黑盒 |
| 面试价值 | ✅ 能讲清楚原理 | 一般 |

---

## 四、概念掌握度检查

| 概念 | 代码位置 | 你应该能解释 |
|------|----------|-------------|
| **Tool Calling** | `agent.py:54-68` | "LLM 返回 JSON 说'我要调这个工具'，你的代码执行，结果回传" |
| **ReAct 循环** | `agent.py:49-75` | "Thought → Action → Observation 循环，直到 LLM 认为可以回答" |
| **Tool Schema** | `agent.py:21-31` | "用 JSON Schema 告诉 LLM：工具叫啥、干什么、参数是什么" |
| **多工具调度** | `agent.py:52` | "LLM 看到 5 个工具描述，自己判断用哪个" |
| **短期记忆** | `agent.py:63-71` | "run() 结束时清理 tool_calls 中间状态，保留干净对话历史" |
| **长期记忆** | `save_to_memory + search_memory` | "ChromaDB 持久化，跨对话检索历史，和 Week 2 RAG 同原理" |
| **Planning** | System Prompt | "通过 Prompt Engineering 让 LLM 先列计划再逐步执行" |
| **System Prompt 工程** | System Prompt 全文 | "定义工具列表 + 工作流程 + 边界规则 = Agent 的行为准则" |

---

## 五、三个项目的关系

```
Week 1: CLI AI 助手
  └── DeepSeek API 基础: client.chat.completions.create()
      └── 被 Week 2 和 Week 3 复用

Week 2: RAG 知识库问答
  └── Embedding + ChromaDB: 文本 → 向量 → 语义搜索
      └── 可以接到 Week 3: Agent 搜索 → 存储 → RAG 检索

Week 3: AI 研究助手 Agent
  └── ReAct + Tool Calling + 短期记忆 + 长期记忆 + Planning
      ├── 长期记忆直接复用了 Week 2 的 ChromaDB + sentence-transformers
      └── 和 Week 2 串联: Agent 搜索 → 存知识库 → RAG 查询
```

**三个项目形成了完整技术栈：基础调用 → 检索增强 → 自主决策。**

---

## 六、面试可能追问

| 问题 | 答案要点 |
|------|---------|
| **Agent 和普通 LLM 对话有什么区别？** | 普通对话 LLM 只能说；Agent 能调工具做事。区别在 `tools` 参数和 `tool_calls` 响应。 |
| **ReAct 是什么？** | Reasoning + Acting：LLM 先思考要做什么（Thought），再决定调哪个工具（Action），拿到结果（Observation），循环直到可以回答。 |
| **为什么不用 LangChain？** | 自建 Agent 只用 30 行核心代码，理解更深。LangChain 适合复杂场景，入门学习阶段手写更好。 |
| **Agent 无限循环怎么办？** | 设置 `max_steps` 上限 + System Prompt 约束"搜几次必须回答"。 |
| **LLM 调了错误的工具怎么办？** | try/except 兜底，把错误信息作为 tool result 返回，LLM 看到错误会调整。 |
| **消息历史太长怎么办？** | 截断早期消息，或只保留 System Prompt + 最近 N 轮对话。 |
| **短期记忆和长期记忆的区别？** | 短期记忆 = 消息列表，跨轮不丢上下文。长期记忆 = ChromaDB，跨对话持久化。 |
| **Planning 是怎么实现的？** | 不需要额外代码，通过 System Prompt 让 LLM 自己列计划再执行。 |

---

## 七、踩坑记录

| 坑 | 原因 | 学到的 |
|----|------|--------|
| **`parameters` 拼成 `paramaters`** | 少一个 e | API 字段名拼写极度敏感，一个字母导致 LLM 看不懂工具定义 |
| **`msg` 被 append 两次** | 复制粘贴残留 | 每次复制代码都要检查上下文 |
| **DuckDuckGo 国内不稳定** | 墙的波动 | 国内项目优先选国内可用的 API 或加代理 |
| **Tavily 字段名不匹配** | DuckDuckGo 用 `href`/`body`，Tavily 用 `url`/`content` | 换 API 的时候要逐字段检查 |
| **`return` 缩进在 for 里面** | 不注意 | 循环里 return = 第一次迭代就退出 |
| **Agent 反复搜索不回答** | System Prompt 没约束 | 好的 Prompt = Agent 的边界感 |
| **`client` 变量名冲突** | TavilyClient 覆盖了 OpenAI client | 变量命名要区分职责 |
