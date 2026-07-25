# Agent 项目深度复盘

> 复盘时间：2026-07-24
> 项目：AI 研究助手 Agent

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

### 🔴 严重：`search_web` return 在 for 循环里面

```python
# agent.py 第 147-149 行
for i, r in enumerate(results):
    output.append(f"[{i+1}{r['title']}...")
    return "\n\n".join(output)   # ← return 在循环里！
```

**后果：** 只返回第 1 条搜索结果，后面的全丢了。LLM 看不到完整的搜索结果。

**修复：** `return` 的缩进应该和 `for` 对齐，而不是在 `for` 里面：

```python
for i, r in enumerate(results):
    output.append(f"[{i+1}] {r['title']}...")
return "\n\n".join(output)   # ← 缩进减少一级，等循环完再返回
```

### 🔴 格式错误：缺少 `]`

```python
f"[{i+1}{r['title']}..."    # ❌ [{i+1} 后面缺 ]
f"[{i+1}] {r['title']}..."  # ✅
```

### 🟡 中等：`eval()` 的安全风险

```python
def calculate(expression: str) -> str:
    return str(eval(expression))   # ← 用户可以执行任意 Python 代码
```

如果用户输入 `__import__('os').system('del /f *.*')`，Agent 可能会传给 calculate。虽然 Agent 一般不会这样做，但生产环境必须替换为安全的表达式解析器。

---

## 三、架构评价

```
当前架构：

  agent.py (单一文件，所有逻辑)
    ├── Tool 类 — 工具定义
    ├── Agent 类 — ReAct 循环
    └── __main__ — 工具定义 + 交互循环
```

**优点：**
- 一个文件就能跑，部署简单
- 自建 Agent 框架，不依赖 LangChain/CrewAI —— **面试加分项**
- 代码量小（~170 行），容易理解

**缺点：**
- 工具定义和交互代码混在一起，加功能时容易乱
- `messages` 无限增长，长对话会撑爆上下文窗口
- 没有流式输出（目前是非流式，等完整回复）

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
| **ReAct 循环** | `agent.py:49-69` | "Thought → Action → Observation 循环，直到 LLM 认为可以回答" |
| **Tool Schema** | `agent.py:21-31` | "用 JSON Schema 告诉 LLM：工具叫啥、干什么、参数是什么" |
| **多工具调度** | `agent.py:52` | "LLM 看到 3 个工具描述，自己判断用哪个" |
| **消息管理** | `agent.py:43-45,58,68` | "每轮对话追加到 messages，LLM 靠这个记住上下文" |
| **System Prompt 工程** | `agent.py:156-164` | "好的 System Prompt 告诉 Agent 工作流程和边界，防止无限循环" |

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
  └── ReAct + Tool Calling: LLM 决定调哪个工具
      └── 可以和 Week 2 合并: 搜索 → 存入知识库 → 检索问答
```

**三个项目串起来就是一个完整的 AI 产品原型。**

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
