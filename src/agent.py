import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

client = OpenAI(
    api_key = os.getenv("DEEPSEEK_API_KEY"),
    base_url = os.getenv("DEEPSEEK_BASE_URL","https://api.deepseek.com"),
)

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

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
            self.messages.append(msg)

            if not msg.tool_calls:
                return msg.content or ""

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
        weather_data = {
            "北京": "22°C,晴",
            "上海": "25°C,多云",
            "深圳": "28°C,阵雨",
        }
        return weather_data.get(city, f"未找到{city}的天气数据")

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

    agent = Agent(system_prompt="""你是一个AI研究助手。你可以用 search_web 搜索网页。

工作流程：
1. 先用最精准的关键词搜索一次
2. 评估搜索结果：信息够了吗？
   - 够了 → 直接总结回答
   - 不够 → 换关键词再搜一次(最多搜2-3次)
3. 搜完2-3次后,不管信息是否完美,都必须用已有信息组织回答
4. 用中文回答，列出信息来源

重要:不要把时间浪费在反复搜索上。2-3次搜索后必须给出答案。""")

    agent.add_tool(weather_tool)
    agent.add_tool(calc_tool)
    agent.add_tool(search_tool)

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