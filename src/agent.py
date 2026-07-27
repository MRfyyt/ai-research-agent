# ============================================================
# agent.py — AI Agent 完整实现
# ============================================================
# 职责: 自建 ReAct Agent 框架——LLM 决策调哪个工具 → 代码执行 → 结果回传 → 循环。
# 依赖: DeepSeek(LLM) + Tavily(搜索) + Open-Meteo(天气) + ChromaDB(长期记忆)
# 工程技能: Function Calling、ReAct 循环、多工具调度、短期记忆清理、长期记忆
#
# Agent 工作流:
#   用户提问 → LLM 分析 → 决定调哪个工具 → 代码执行 → 结果喂回 LLM → 循环 → 回答
#   核心: LLM 不执行函数，它只是"说"要调哪个。真正执行的是你的代码。
# ============================================================

import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import json
import requests
import chromadb
from openai import OpenAI
from dotenv import load_dotenv
from tavily import TavilyClient
from sentence_transformers import SentenceTransformer

load_dotenv()

# ============================================================
# 两个 API 客户端: 一个管"大脑"，一个管"手"
# ============================================================
# client: DeepSeek LLM → 推理决策 +
# 工具调用 tavily: Tavily Search API → 真正搜网页
client = OpenAI(
    api_key = os.getenv("DEEPSEEK_API_KEY"),
    base_url = os.getenv("DEEPSEEK_BASE_URL","https://api.deepseek.com"),
)

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# ============================================================
# 长期记忆: 复用 Week 2 的 ChromaDB + sentence-transformers
# ============================================================
embed_model = SentenceTransformer("all-MiniLM-L6-V2")
chroma_client = chromadb.PersistentClient(path="./memory_db")
memory = chroma_client.get_or_create_collection(name="conversation_memory")

# ============================================================
# Tool 类: 把任意 Python 函数包装成 LLM 可调用的工具
# ============================================================
class Tool:
    """一个工具 = 名字 + 描述 + 参数规则 + 实际要调用的函数。
    LLM 通过名字和描述决定"该不该调这个工具"，
    通过 parameters（JSON Schema 格式）知道"要传什么参数"，
    你的代码通过 func 真正执行。"""

    def __init__(self,name :str ,description : str,parameters :dict,func):
        self.name = name                # 工具名，如 "search_web"
        self.description = description  # 告诉 LLM 这个工具干什么
        self.parameters = parameters    # JSON Schema 格式的参数定义
        self.func = func                # 实际执行的 Python 函数

    def to_openai_schema(self)->dict:
        """转成 OpenAI/DeepSeek API 要求的 tools 参数格式。
        type: "function" + function: {name, description, parameters}"""
        return {
            "type":"function",
            "function":{
                "name":self.name,
                "description":self.description,
                "parameters":self.parameters,
            }
        }

# ============================================================
# Agent 类: ReAct 循环引擎
# ============================================================
class Agent:
    """自建 Agent——不依赖 LangChain/CrewAI。
    核心是一个 for 循环（ReAct 模式）:
      Thought（LLM 思考）→ Action（执行工具）→ Observation（看结果）→ 循环"""

    def __init__(self,system_prompt):
        self.system_prompt = system_prompt  # Agent 人设 + 工作规则
        self.tools = {}                     # 工具名 → Tool 对象
        self.messages = []                  # 对话历史

    def add_tool(self,tool:Tool):
        """注册一个工具到 Agent。注册后 LLM 在 run() 中可以看到并调用它。"""
        self.tools[tool.name] = tool

    def run(self,user_input : str,max_steps : int = 5)->str:
        """ReAct 循环入口。max_steps 防止无限循环。
        返回 LLM 的最终回答（自然语言文本）。"""

        # ---- 首次调用时加入 System Prompt ----
        if self.system_prompt and not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})

        self.messages.append({"role": "user", "content": user_input})

        # ============================================================
        # ReAct 循环: 最多 max_steps 轮
        # ============================================================
        for step in range(max_steps):
            # ---- Step 1: 调 LLM，告诉它有哪些工具可用 ----
            response = client.chat.completions.create(
                model = os.getenv("DEEPSEEK_MODEL","deepseek-v4-pro"),
                messages = self.messages,
                tools = [t.to_openai_schema() for t in self.tools.values()],  # 所有工具描述
                temperature = 0.3
            )

            msg = response.choices[0].message
            # model_dump(): ChatCompletionMessage 对象 → dict，否则不能下标访问
            self.messages.append(msg.model_dump())

            # ---- Step 2: LLM 没说要调工具 → 这就是最终回答 ----
            if not msg.tool_calls:
                # ---- 短期记忆清理: 只保留干净的对话历史 ----
                # 删掉 tool_calls 和 tool 结果等中间状态，
                # 只留 System Prompt + 用户消息 + 不含 tool_calls 的助手消息
                answer = msg.content or""
                clean = []
                for m in self.messages:
                    if m["role"] == "system":
                        clean.append(m)
                    elif m["role"] == "user":
                        clean.append(m)
                    elif m["role"] == "assistant" and not m.get("tool_calls"):
                        clean.append(m)
                clean.append({"role":"assistant","content":answer})
                self.messages = clean
                return answer

            # ---- Step 3: LLM 决定调工具 → 真正执行 ----
            for tc in msg.tool_calls:
                name = tc.function.name          # 工具名，如 "search_web"
                args = json.loads(tc.function.arguments)  # 参数 JSON → dict
                tool = self.tools.get(name)      # 找到对应的 Tool 对象

                # 防御性处理: 工具不存在 or 执行出错
                if not tool:
                    result = f"工具 '{name}' 不存在"
                else:
                    try:
                        result = tool.func(**args)   # ← 真正执行函数！
                    except Exception as e:
                        result = f"工具执行失败: {e}"

                # 执行结果作为 Tool 消息喂回 LLM
                self.messages.append({
                    "role":"tool",
                    "tool_call_id":tc.id,
                    "content":str(result),
                })

        # 达到最大步数仍无最终回答 → 兜底返回
        return "已达到最大步数，但仍未得到答案"

# ============================================================
# 工具定义 + CLI 交互（__main__ 块）
# ============================================================
if __name__ == "__main__":

    # ============================================================
    # 工具 1: get_weather — 真实天气 API（Open-Meteo，免费无需注册）
    # ============================================================
    def get_weather(city: str) -> str:
        cities = {
            "北京": (39.9, 116.4),
            "上海": (31.2, 121.5),
            "深圳": (22.5, 114.1),
            "广州": (23.1, 113.3),
            "杭州": (30.3, 120.2),
            "成都": (30.6, 104.1),
            "武汉": (30.6, 114.3),
            "南京": (32.1, 118.8),
        }
        coords = cities.get(city)
        if not coords:
             return f"暂不支持查询{city}的天气（可用城市：{', '.join(cities.keys())})"
        lat,lon = coords
        try:
          url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=Asia/Shanghai"
          resp = requests.get(url, timeout=5).json()
          temp = resp["current"]["temperature_2m"]
          code = resp["current"]["weather_code"]
          weather_map = {
            0: "晴", 1: "少云", 2: "多云", 3: "阴",
            45: "雾", 51: "小雨", 61: "中雨", 80: "阵雨"
          }
          weather = weather_map.get(code, f"code={code}")
          return f"{city}当前{weather}，气温{temp}°C"

        except Exception as e:
            return f"查询天气失败: {e}"

    weather_tool = Tool(
        name="get_weather",
        description="查询指定城市的实时天气",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名"}
            },
            "required": ["city"]
        },
        func=get_weather,
    )

    # ============================================================
    # 工具 2: calculate — 数学计算
    # ============================================================
    def calculate(expression: str) -> str:
            """安全计算数学表达式"""
            try:
                return str(eval(expression))
            except Exception as e:
                return f"计算错误: {e}"

    calc_tool = Tool(
            name="calculate",
            description="计算数学表达式，如 '123 * 456' 或 'sqrt(144)'",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式"}
                },
                "required": ["expression"]
            },
            func=calculate,
        )

    # ============================================================
    # 工具 3: search_web — Tavily 搜索 API
    # ============================================================
    def search_web(query:str,max_results = 3)->str:
        try:
            response = tavily.search(query, max_results=max_results)
            results = response.get("results", [])
            if not results:
                return "未找到相关结果"
            output = []
            for i,r in enumerate(results):
                output.append(f"[{i+1}{r['title']}\n  链接:{r['url']}\n   摘要:{r['content']}")
            return "\n\n".join(output)
        except Exception as e:
            return f"搜索失败:{e}"

    search_tool = Tool(
        name = "search_web",
        description="搜索网页，获取实时信息。输入搜索关键词，返回标题、链接和摘要。",
        parameters = {
            "type" :"object",
            "properties":{
                "query":{"type":"string","description":"搜索关键词"},
                "max_results":{"type":"integer","description":"返回结果数量,默认3"}
            },
            "required":["query"]
        },
        func = search_web,
    )

    # ============================================================
    # 工具 4: save_to_memory — 长期记忆存储（复用 Week 2 ChromaDB）
    # ============================================================
    memory_counter = 0
    def save_to_memory(info:str)->str:
            global memory_counter
            try:
                # 文本 → 向量 → 存入 ChromaDB（和 Week 2 add_documents 完全一样）
                embedding = embed_model.encode(info).tolist()
                memory.add(
                    documents = [info],
                    embeddings = [embedding],
                    ids = [f"men_{memory_counter}"]
                )
                memory_counter +=1
                return "已保存到长期记忆"
            except Exception as e:
                print(f"  [DEBUG] save_to_memory 错误: {e}")   # ← 加这行
                return f"保存失败:{e}"

    save_memory_tool = Tool(
        name="save_to_memory",
        description="保存重要信息到长期记忆。当用户说'记住''记下来'时调用。",
        parameters={
            "type": "object",
            "properties": {"info": {"type": "string", "description": "要保存的信息"}},
            "required": ["info"]
        },
        func=save_to_memory,
    )

    # ============================================================
    # 工具 5: search_memory — 长期记忆搜索
    # ============================================================
    def search_memory(query:str)->str:
        try:
            embedding = embed_model.encode(query).tolist()
            results = memory.query(query_embeddings = [embedding],n_results = 3)
            docs = results["documents"][0]
            if not docs:
                return "未找到相关记忆"
            return "\n".join([f"-{d}" for d in docs])
        except Exception as e:
            return f"搜索记忆失败:{e}"

    memory_tool = Tool(
        name = "search_memory",
        description="搜索之前的对话记忆。如果用户提到'之前''上次'等问题，先搜索记忆。",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "搜索关键词"}},
            "required": ["query"]
        },
        func=search_memory,
    )

    # ============================================================
    # Agent 初始化: System Prompt = Agent 的行为准则
    # ============================================================
    # Planning 通过 Prompt 工程实现——让 LLM 先列计划再逐步执行
    agent = Agent(system_prompt="""你是一个AI研究助手。你可以用以下工具完成任务：
- search_web: 搜索网页获取实时信息
- calculate: 计算数学表达式
- get_weather: 查询城市天气
- save_to_memory: 保存信息到长期记忆。当用户说"记住"时必须调用！
- search_memory: 搜索之前的对话记忆

## 工作流程

收到用户问题后，你必须先列出执行计划，再逐步执行：

### 第一步：输出计划
在开始搜索之前，先说：
"📋 计划：
1. ...
2. ...
3. ..."

### 第二步：逐步执行
按计划顺序调用工具，每次调用后评估结果。

### 第三步：汇总回答
信息够了就停下来，用中文组织完整回答，列出信息来源。

## 示例

用户: "比较一下北京和上海今天的天气，哪个更适合出游"
计划:
1. 查北京天气
2. 查上海天气
3. 对比分析
→ 依次执行 → 汇总回答

## 规则
- 最多搜索 3 次，之后必须给出答案
- 用中文回答
- 列出信息来源链接""")

    # ---- 注册全部 5 个工具 ----
    agent.add_tool(weather_tool)
    agent.add_tool(calc_tool)
    agent.add_tool(search_tool)
    agent.add_tool(save_memory_tool)
    agent.add_tool(memory_tool)

    # ============================================================
    # CLI 交互循环: 和 Week 1 的 main.py 一样的模式
    # ============================================================
    print("🤖 AI Agent 助手")
    print("输入 /quit 退出\n")

    while True:
        user_input = input("你>").strip()
        if not user_input:
            continue
        if user_input =="/quit":
            break
        reply = agent.run(user_input)
        print(f"{reply}\n")
