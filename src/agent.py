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

client = OpenAI(
    api_key = os.getenv("DEEPSEEK_API_KEY"),
    base_url = os.getenv("DEEPSEEK_BASE_URL","https://api.deepseek.com"),
)

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

embed_model = SentenceTransformer("all-MiniLM-L6-V2")
chroma_client = chromadb.PersistentClient(path="./memory_db")
memory = chroma_client.get_or_create_collection(name="conversation_memory")

class Tool:
    """一个工具 = 名字 + 描述 + 参数规则 + 实际要调用的函数"""
    def __init__(self,name :str ,description : str,parameters :dict,func):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_openai_schema(self)->dict:
        """转成OpenAI/DeepSeek要求的JSON Schema格式"""
        return {
            "type":"function",
            "function":{
                "name":self.name,
                "description":self.description,
                "parameters":self.parameters,
            }
        }

class Agent:
    def __init__(self,system_prompt):
        self.system_prompt = system_prompt
        self.tools = {}
        self.messages = []

    def add_tool(self,tool:Tool):
        self.tools[tool.name] = tool  

    def run(self,user_input : str,max_steps : int = 5)->str:
        if self.system_prompt and not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})
        
        self.messages.append({"role": "user", "content": user_input})

        for step in range(max_steps):
            response = client.chat.completions.create(
                model = os.getenv("DEEPSEEK_MODEL","deepseek-v4-pro"),
                messages = self.messages,
                tools = [t.to_openai_schema() for t in self.tools.values()],
                temperature = 0.3
            )

            msg = response.choices[0].message
            self.messages.append(msg.model_dump())

            if not msg.tool_calls:
                # 清理历史：只保留 system + user + 最终 assistant 回复
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

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                tool = self.tools.get(name)
                if not tool:
                    result = f"工具 '{name}' 不存在"
                else:
                    try:
                        result = tool.func(**args)
                    except Exception as e:
                        result = f"工具执行失败: {e}"
                self.messages.append({
                    "role":"tool",
                    "tool_call_id":tc.id,
                    "content":str(result),
                })

        return "已达到最大步数，但仍未得到答案"

if __name__ == "__main__":
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

    memory_counter = 0
    def save_to_memory(info:str)->str:
            global memory_counter
            try:
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
              
    agent.add_tool(weather_tool)
    agent.add_tool(calc_tool)
    agent.add_tool(search_tool)
    agent.add_tool(save_memory_tool)
    agent.add_tool(memory_tool)

    # 4. 测试
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