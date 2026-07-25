"""
AI Agent 核心概念 —— 一次性跑通
================================
Agent = LLM + 工具 + 循环决策
"""

import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ============================================================
# 概念 1: 普通 LLM vs Agent
# ============================================================
print("=" * 60)
print("概念 1: 普通 LLM vs Agent")
print("=" * 60)

print("""
  普通 LLM:
    用户: "北京今天几度？"
    LLM:  "抱歉，我不知道实时天气。"

  Agent:
    用户: "北京今天几度？"
    LLM:  决定调用 get_weather 工具
    代码: 真的去查天气 → "22°C，晴"
    LLM:  "北京今天 22°C，晴天。"
""")

print("▶ 概念 2: Function Calling 数据流"); print("-" * 40)

# ============================================================
# 概念 2: Function Calling 完整流程
# ============================================================
print("""
  ① 你定义工具 → 告诉 LLM 有什么能力
  ② 用户提问 → LLM 判断是否需要工具
  ③ 如果需要 → LLM 返回 JSON（工具名 + 参数）
  ④ 你的代码执行工具 → 拿到真实结果
  ⑤ 结果喂回 LLM → LLM 组织自然语言回答

  关键: LLM 不执行函数，它只是"说"要调用哪一个。
  真正执行的是你的代码。
""")

print("▶ 概念 3: ReAct 循环"); print("-" * 40)

# ============================================================
# 概念 3: ReAct 模式
# ============================================================
print("""
  ReAct = Reasoning + Acting

  Thought → Action → Observation → Thought → ... → Final Answer

  循环直到 LLM 认为可以给出最终答案。
""")

print("▶ 实战: 调用 DeepSeek Function Calling"); print("-" * 40)

# ============================================================
# 实战: 用 DeepSeek 跑一次 Function Calling
# ============================================================
import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY", "")
if not api_key or "your" in api_key:
    print("  ⚠️  请先在 .env 中配置 DEEPSEEK_API_KEY")
else:
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    # 定义工具
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的实时天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，如'北京'"
                    }
                },
                "required": ["city"]
            }
        }
    }]

    print("  > 用户: 北京今天天气怎么样？")

    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[
            {"role": "system", "content": "你是一个天气助手。"},
            {"role": "user", "content": "北京今天天气怎么样？"},
        ],
        tools=tools,
        temperature=0.3,
    )

    msg = response.choices[0].message

    if msg.tool_calls:
        for tc in msg.tool_calls:
            func_name = tc.function.name
            func_args = json.loads(tc.function.arguments)
            print(f"  > LLM 决定调用: {func_name}({func_args})")

            # 模拟执行工具
            fake_result = f"{func_args['city']}今天22°C，晴"
            print(f"  > 执行结果: {fake_result}")

            # 结果发回 LLM
            response2 = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": "你是一个天气助手。"},
                    {"role": "user", "content": "北京今天天气怎么样？"},
                    msg,
                    {"role": "tool", "tool_call_id": tc.id, "content": fake_result},
                ],
                temperature=0.3,
            )
            print(f"  > 最终回答: {response2.choices[0].message.content}")
    else:
        print(f"  > 直接回复: {msg.content}")

print()
print("=" * 60)
print("🎉 Agent 概念过完！")
print("=" * 60)
