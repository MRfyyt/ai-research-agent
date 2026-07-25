# Agent 项目整体思路回顾

> 记录时间：2026-07-24
> 项目：AI 研究助手 Agent

---

## 一、核心问题

> **"让 LLM 不只是说话，还能真正去做事——搜索网页、计算数学、查询数据。"**

---

## 二、从零到一的 4 步推导

| 步骤 | 尝试 | 结果 | 暴露的问题 |
|:--:|------|:--:|------|
| ① | 让 LLM 直接回答需要实时信息的问题 | LLM 说"我不知道" | LLM 的训练数据有截止日期，无法获取实时信息 |
| ② | 我们先搜索，人工把结果发给 LLM | 能回答了，但需要人操作 | 能不能让 LLM 自己决定什么时候该搜索？ |
| ③ | 给 LLM 一个"菜单"（工具列表），让它点菜 | ✅ LLM 能决定调哪个工具 | 如果一个问题需要调多个工具怎么办？ |
| ④ | 做 ReAct 循环：LLM 思考 → 调工具 → 看结果 → 思考 → ... | ✅ 多步推理 + 自动停止 |

**每一步推导：**

```
问题：DeepSeek 不知道"特斯拉最新股价"，怎么办？

思路①：让 LLM 直接回答
  → ❌ 训练数据有截止日期，不知道实时信息

思路②：你手动搜，结果贴给 LLM
  → ✅ 能回答了，但每次都手动操作

思路③：定义"工具菜单"，LLM 选择要什么工具
  → LLM 说"我要 search_web('特斯拉股价')"
  → 你的代码执行搜索
  → 结果返回 LLM
  → ✅ LLM 能自己决定什么时候需要搜索

思路④：一个问题可能需要多次调用工具
  → "搜一次信息不够 → 换关键词再搜"
  → 用 ReAct 循环：每一步 LLM 评估要不要继续
  → ✅ 最多搜 2-3 次，自己决定什么时候回答
```

---

## 三、技术选型推导

| 选择 | 原因 |
|------|------|
| **DeepSeek** 做 LLM | 已有 API Key；支持 Function Calling（Tool Calling） |
| **自建 Agent 框架** | 不用 LangChain——30 行核心代码就能写一个，理解更透，面试能讲清 |
| **Tavily** 做搜索 | DuckDuckGo 国内不稳定；Tavily 专为 AI Agent 设计，每月 1000 次免费 |
| **CLI 交互** | 不写 Streamlit——Week 3 的终点是 Agent 逻辑，不是界面；CLI 够用 |
| **OpenAI SDK** 调 DeepSeek | 和 Week 1 一样——DeepSeek API 兼容 OpenAI 格式 |

---

## 四、文件分工推导

```
只需回答 2 个问题：

Q1: Agent 的核心逻辑是什么？
  → src/agent.py — Tool 类 + Agent 类 + ReAct 循环 + CLI 交互

Q2: 别人拿到代码怎么跑？
  → .env + requirements.txt + README.md
```

没有 `app.py`——不像 Week 2 有 Streamlit。Agent 本身已经够复杂了，不需要分心写界面。

---

## 五、核心代码的演进

### 阶段 1：一个工具，一次调用

教学脚本里的样子——LLM 调一次工具，拿到结果，回答：

```python
# 定义工具
tools = [{"function": {"name": "get_weather", ...}}]

# 调用 LLM
response = client.chat.completions.create(messages=..., tools=tools)

# LLM 说要调 get_weather("北京")
# 你执行 → 结果回传 → LLM 回答
```

### 阶段 2：抽象 Tool 类

```python
class Tool:
    def to_openai_schema(self):  # 转成 LLM 能理解的 JSON 格式

# 任何函数只要包一层 Tool，就能让 LLM 调用
weather_tool = Tool(name="get_weather", ..., func=get_weather)
```

### 阶段 3：ReAct 循环

```python
for step in range(max_steps):
    response = LLM(messages, tools)
    if 没有 tool_calls:
        return 回答        # ← 退出
    执行工具 → 结果加入 messages → 继续循环
```

**这是整个项目的心跳。** 不管你加多少个工具，这个循环不变。

---

## 六、如果你能从零重现它

关掉代码，你能否写出这个骨架：

```python
class Tool:
    """工具名 + 描述 + 参数规则 + 执行函数"""
    def to_openai_schema(self): ...

class Agent:
    def __init__(self, system_prompt): ...
    def add_tool(self, tool): ...
    def run(self, user_input, max_steps=5):
        # 1. 加 System Prompt + User Message
        # 2. for step in range(max_steps):
        # 3.   调 LLM（带 tools）
        # 4.   如果没 tool_calls → 返回回答
        # 5.   否则 → 执行每个工具 → 结果追加到 messages
        # 6. 达到上限 → 兜底返回
```

**如果能写出这个骨架，你就真正掌握了 Agent。**
