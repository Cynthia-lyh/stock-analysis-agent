import ast
import inspect
import os
import re
import sys
from string import Template
from typing import List, Callable, Tuple, Optional
from pathlib import Path

from dotenv import load_dotenv
from ..core import AgentBrain
from ..core import Agent
from ..core import Message
from ..core.config import Config

from .prompt_template import react_system_prompt_template
from .investment_knowledge import investment_knowledge

from ..tools import MemoryTool, RAGTool,ToolRegistry,MCPTool

# 加载环境变量
load_dotenv()

class ReActAgent(Agent):
    def __init__(
        self,
        name: str,
        llm,
        tool_registry: Optional[ToolRegistry] = None,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None,
        max_steps: int = 5,
    ):
        """
        初始化ReActAgent

        Args:
            name: Agent名称
            llm: LLM实例
            tool_registry: 工具注册表（可选，如果不提供则创建空的工具注册表）
            system_prompt: 系统提示词
            config: 配置对象
            max_steps: 最大执行步数
            custom_prompt: 自定义提示词模板
        """
        super().__init__(name, system_prompt, config)
        self.llm = llm
        # 如果没有提供tool_registry，创建一个空的
        if tool_registry is None:
            self.tool_registry = ToolRegistry()
        else:
            self.tool_registry = tool_registry

        self.max_steps = max_steps
        self.current_history: List[str] = []

    def run(self,user_input:str):
        messages = [
            {"role":"system","content": self.render_system_prompt(react_system_prompt_template)},
            {"role":"user","content": f"<question>{user_input}</question>"}
        ]
        # 执行工具调用
        # action='[TOOL_CALL:mcp_get_weather:{"city": "北京"}]'
        action='[TOOL_CALL:rag:search=股票 定义 解释]'
        tool_calls = self._parse_tool_calls(action)
        result = self._execute_tool_call(tool_calls['tool_name'], tool_calls['parameters'])
        print(f"tool_calls: {tool_calls}")
        print(f"🎬 行动: {result}")
        current_step = 6
        while current_step < self.max_steps:
            current_step += 1

            #请求模型
            print(f"messages:{messages}")
            content = self.llm.think(messages = messages)
            messages.append({"role": "assistant", "content": content})
            print(f"\n\n模型回复：{content}")
            #检测 Though
            thought_match = re.search(r"<thought>(.*?)</thought>", content, re.DOTALL)
            if thought_match:
                thought = thought_match.group(1)
                print(f"\n\n💭 Thought: {thought}")

            # 检测模型是否输出 Final Answer，如果是的话，直接返回
            if "<final_answer>" in content:
                final_answer = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
                # 保存到历史记录
                self.add_message(Message(user_input, "user"))
                self.add_message(Message(final_answer.group(1), "assistant"))
                return final_answer.group(1)

            #检测 Action
            action_match = re.search(r"<action>(.*?)</action>", content, re.DOTALL)
            if not action_match:
                raise RuntimeError("模型未输出 <action>")
            action = action_match.group(1)
            print(f"\n\n🔧 Action: {action}")
            # tool_name, args = self.parse_action(action)

            # 执行工具调用
            tool_calls = self._parse_tool_calls(action)
            result = self._execute_tool_call(tool_calls['tool_name'], tool_calls['parameters'])

            print(f"\n\n🔍 Observation：{result}")
            obs_msg = f"<observation>{result}</observation>"
            messages.append({"role": "user", "content": obs_msg})
            
        print("⏰ 已达到最大步数，流程终止。")
        final_answer = "抱歉，我无法在限定步数内完成这个任务。"
        
        # 保存到历史记录
        self.add_message(Message(user_input, "user"))
        self.add_message(Message(final_answer, "assistant"))
        
        return final_answer

    def get_tool_list(self) -> str:
        """生成工具列表字符串，包含函数签名和简要说明"""
        tool_descriptions = []
        for func in self.tool_registry.values():
            name = func.__name__
            signature = str(inspect.signature(func))
            doc = inspect.getdoc(func)
            tool_descriptions.append(f"- {name}{signature}: {doc}")
        print(f"🔧 可用工具列表：\n{os.linesep.join(tool_descriptions)}")
        return "\n".join(tool_descriptions)

    def render_system_prompt(self, tsystem_prompt_template: str) -> str:
        """渲染系统提示模板，替换变量"""
        tool_list = self.tool_registry.get_tools_description()
        # file_list = ", ".join(
        #     os.path.abspath(os.path.join(self.project_directory, f)) 
        #     for f in os.listdir(self.project_directory)
        # )
        # print(f"📂 当前目录下文件列表：{self.project_directory}")
        return Template(tsystem_prompt_template).substitute(
            tool_list=tool_list
        )

    # @staticmethod
    # def get_api_key() -> str:
    #     """Load the API key from an environment variable."""
    #     load_dotenv()
    #     api_key = os.getenv("OPENROUTER_API_KEY")
    #     if not api_key:
    #         raise ValueError("未找到 OPENROUTER_API_KEY 环境变量，请在 .env 文件中设置。")
    #     return api_key

    # def call_model(self, messages):
    #     print("\n\n正在请求模型，请稍等...")
    #     response = self.client.chat.completions.create(
    #         model=self.model,
    #         messages=messages,
    #     )
    #     content = response.choices[0].message.content
    #     messages.append({"role": "assistant", "content": content})
    #     return content

    def _parse_action(self, action_text: str) -> Tuple[Optional[str], Optional[str]]:
        """解析行动文本，提取工具名称和输入"""
        match = re.match(r"(\w+)\[(.*)\]", action_text)
        print(f"🔍 解析行动文本：{action_text},匹配：{match}")
        if match:
            return match.group(1), match.group(2)
        return None, None
    
    def _parse_tool_calls(self, text: str) -> list:
        """解析文本中的工具调用"""
        pattern = r'\[TOOL_CALL:([^:]+):([^\]]+)\]'
        matches = re.search(pattern, text)
        tool_calls={
            'tool_name': matches.group(1).strip(),
            'parameters': matches.group(2).strip(),
            'original': f'[TOOL_CALL:{matches.group(1)}:{matches.group(2)}]'
        }
        
        return tool_calls
    
    def add_tool(self, tool, auto_expand: bool = True) -> None:
        """
        添加工具到Agent（便利方法）

        Args:
            tool: Tool对象
            auto_expand: 是否自动展开可展开的工具（默认True）

        如果工具是可展开的（expandable=True），会自动展开为多个独立工具
        """
        if not self.tool_registry:
            from tools.registry import ToolRegistry
            self.tool_registry = ToolRegistry()
            self.enable_tool_calling = True

        # 直接使用 ToolRegistry 的 register_tool 方法
        # ToolRegistry 会自动处理工具展开
        self.tool_registry.register_tool(tool, auto_expand=auto_expand)

    def _execute_tool_call(self, tool_name: str, parameters: str) -> str:
        """执行工具调用"""
        if not self.tool_registry:
            return f"❌ 错误：未配置工具注册表"

        try:
            # 获取Tool对象
            tool = self.tool_registry.get_tool(tool_name)
            if not tool:
                return f"❌ 错误：未找到工具 '{tool_name}'"

            # 智能参数解析
            param_dict = self._parse_tool_parameters(tool_name, parameters)
            print(f"🔧 调用工具 '{tool_name}'，参数: {param_dict}")
            # 调用工具
            result = tool.run(param_dict)
            return f"🔧 工具 {tool_name} 执行结果：\n{result}"

        except Exception as e:
            return f"❌ 工具调用失败：{str(e)}"

    def _parse_tool_parameters(self, tool_name: str, parameters: str) -> dict:
        """智能解析工具参数"""
        import json
        param_dict = {}

        # 尝试解析JSON格式
        if parameters.strip().startswith('{'):
            try:
                param_dict = json.loads(parameters)
                # JSON解析成功，进行类型转换
                param_dict = self._convert_parameter_types(tool_name, param_dict)
                return param_dict
            except json.JSONDecodeError:
                # JSON解析失败，继续使用其他方式
                pass

        if '=' in parameters:
            # 格式: key=value 或 action=search,query=Python
            if ',' in parameters:
                # 多个参数：action=search,query=Python,limit=3
                pairs = parameters.split(',')
                for pair in pairs:
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        param_dict[key.strip()] = value.strip()
            else:
                # 单个参数：key=value
                key, value = parameters.split('=', 1)
                param_dict[key.strip()] = value.strip()

            # 类型转换
            param_dict = self._convert_parameter_types(tool_name, param_dict)

            # 智能推断action（如果没有指定）
            if 'action' not in param_dict:
                param_dict = self._infer_action(tool_name, param_dict)
        else:
            # 直接传入参数，根据工具类型智能推断
            param_dict = self._infer_simple_parameters(tool_name, parameters)

        return param_dict

    def _convert_parameter_types(self, tool_name: str, param_dict: dict) -> dict:
        """
        根据工具的参数定义转换参数类型

        Args:
            tool_name: 工具名称
            param_dict: 参数字典

        Returns:
            类型转换后的参数字典
        """
        if not self.tool_registry:
            return param_dict

        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return param_dict

        # 获取工具的参数定义
        try:
            tool_params = tool.get_parameters()
        except:
            return param_dict

        # 创建参数类型映射
        param_types = {}
        for param in tool_params:
            param_types[param.name] = param.type

        # 转换参数类型
        converted_dict = {}
        for key, value in param_dict.items():
            if key in param_types:
                param_type = param_types[key]
                try:
                    if param_type == 'number' or param_type == 'integer':
                        # 转换为数字
                        if isinstance(value, str):
                            converted_dict[key] = float(value) if param_type == 'number' else int(value)
                        else:
                            converted_dict[key] = value
                    elif param_type == 'boolean':
                        # 转换为布尔值
                        if isinstance(value, str):
                            converted_dict[key] = value.lower() in ('true', '1', 'yes')
                        else:
                            converted_dict[key] = bool(value)
                    else:
                        converted_dict[key] = value
                except (ValueError, TypeError):
                    # 转换失败，保持原值
                    converted_dict[key] = value
            else:
                converted_dict[key] = value

        return converted_dict

    def _infer_action(self, tool_name: str, param_dict: dict) -> dict:
        """根据工具类型和参数推断action"""
        if tool_name == 'memory':
            if 'recall' in param_dict:
                param_dict['action'] = 'search'
                param_dict['query'] = param_dict.pop('recall')
            elif 'store' in param_dict:
                param_dict['action'] = 'add'
                param_dict['content'] = param_dict.pop('store')
            elif 'query' in param_dict:
                param_dict['action'] = 'search'
            elif 'content' in param_dict:
                param_dict['action'] = 'add'
        elif tool_name == 'rag':
            if 'search' in param_dict:
                param_dict['action'] = 'search'
                param_dict['query'] = param_dict.pop('search')
            elif 'query' in param_dict:
                param_dict['action'] = 'search'
            elif 'text' in param_dict:
                param_dict['action'] = 'add_text'


        return param_dict

    def _infer_simple_parameters(self, tool_name: str, parameters: str) -> dict:
        """为简单参数推断完整的参数字典"""
        if tool_name == 'rag':
            return {'action': 'search', 'query': parameters}
        elif tool_name == 'memory':
            return {'action': 'search', 'query': parameters}
        else:
            return {'input': parameters}

    def parse_action(self, code_str: str) -> Tuple[str, List[str]]:
        match = re.match(r'(\w+)\((.*)\)', code_str, re.DOTALL)
        if not match:
            raise ValueError("Invalid function call syntax")

        func_name = match.group(1)
        args_str = match.group(2).strip()

        # 手动解析参数，特别处理包含多行内容的字符串
        args = []
        current_arg = ""
        in_string = False
        string_char = None
        i = 0
        paren_depth = 0
        
        while i < len(args_str):
            char = args_str[i]
            
            if not in_string:
                if char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_arg += char
                elif char == '(':
                    paren_depth += 1
                    current_arg += char
                elif char == ')':
                    paren_depth -= 1
                    current_arg += char
                elif char == ',' and paren_depth == 0:
                    # 遇到顶层逗号，结束当前参数
                    args.append(self._parse_single_arg(current_arg.strip()))
                    current_arg = ""
                else:
                    current_arg += char
            else:
                current_arg += char
                if char == string_char and (i == 0 or args_str[i-1] != '\\'):
                    in_string = False
                    string_char = None
            
            i += 1
        
        # 添加最后一个参数
        if current_arg.strip():
            args.append(self._parse_single_arg(current_arg.strip()))
        
        return func_name, args

    def _parse_single_arg(self, arg_str: str):
        """解析单个参数"""
        arg_str = arg_str.strip()
        
        # 如果是字符串字面量
        if (arg_str.startswith('"') and arg_str.endswith('"')) or \
           (arg_str.startswith("'") and arg_str.endswith("'")):
            # 移除外层引号并处理转义字符
            inner_str = arg_str[1:-1]
            # 处理常见的转义字符
            inner_str = inner_str.replace('\\"', '"').replace("\\'", "'")
            inner_str = inner_str.replace('\\n', '\n').replace('\\t', '\t')
            inner_str = inner_str.replace('\\r', '\r').replace('\\\\', '\\')
            return inner_str
        
        # 尝试使用 ast.literal_eval 解析其他类型
        try:
            return ast.literal_eval(arg_str)
        except (SyntaxError, ValueError):
            # 如果解析失败，返回原始字符串
            return arg_str


def demo_mcp_tool():
    brain = AgentBrain()
    # 添加天气 MCP 工具
    server_script = os.path.join(os.path.dirname(__file__), "mcpServer.py")
    weather_tool = MCPTool(server_command=["python", server_script])
    tool_registry = ToolRegistry()
    assistant = ReActAgent(name="TestAgent",llm=brain,tool_registry=tool_registry)
    assistant.add_tool(weather_tool)
    print(f"121212{assistant.tool_registry.get_tools_description()}")

    print("\n查询北京天气：")
    response = assistant.run("北京今天天气怎么样？")
    print(f"回答: {response}\n")

def test():
    # 创建 ReActAgent 实例
    brain = AgentBrain()
    # 获取项目根目录（假设当前在 src/agents/）
    project_root = Path(__file__).parent.parent.parent

    # 1. 使用 -m 方式运行，而不是直接跑文件
    # 模块名：src.mcp.mcpServer（注意没有 .py）
    module_name = "src.mcp.mcpServer"

    # 2. 关键：将项目根目录加入环境变量，确保子进程能找到包
    env = os.environ.copy()
    # 将项目根目录添加到 PYTHONPATH
    python_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{project_root}:{python_path}" if python_path else str(project_root)

    # 3. 启动命令
    weather_tool = MCPTool(server_command=
        [sys.executable, "-m", module_name],
        cwd=str(project_root),  # 工作目录设为根目录
        env=env             # 传入修正后的环境变量
    )
    agent = ReActAgent(name="TestAgent",llm=brain)
    agent.add_tool(weather_tool)

    # 添加工具
    # agent.add_tool(MemoryTool())
    # agent.add_tool(RAGTool())

    # 测试运行
    print(f"121212{agent.tool_registry.get_tools_description()}")
    user_input = "广州今天天气如何"
    response = agent.run(user_input)
    print(f"最终回答: {response}")

def memory_rag():
    brain = AgentBrain()
    # agent = ReActAgent(name="TestAgent",llm=brain)
    # 创建记忆工具
    memory_tool = MemoryTool(
        user_id="demo_user_001",
        memory_types=["working", "episodic", "semantic"]
    )

    # 创建工具注册表
    tool_registry = ToolRegistry()
    tool_registry.register_tool(memory_tool)

    print("💬 开始智能对话演示...")
    agent = ReActAgent(name="TestAgent",llm=brain,tool_registry=tool_registry)

    # 模拟多轮对话
    conversations = [
        "你好！我叫李明，是一名软件工程师，专门做Python开发",
        "我最近在学习机器学习，特别对深度学习感兴趣",
        "你能推荐一些Python机器学习的库吗？",
        "你还记得我的名字和职业吗？请结合我的背景给我一些学习建议"
    ]

    for i, user_input in enumerate(conversations, 1):
        print(f"\n--- 对话轮次 {i} ---")
        print(f"👤 用户: {user_input}")

        # SimpleAgent会自动使用memory工具
        response = agent.run(user_input)
        print(f"🤖 助手: {response}")

    # 显示记忆摘要
    print(f"\n📊 最终记忆系统状态:")
    summary = memory_tool.run({"action": "summary"})
    print(summary)

def demo_rag_tool():
    brain = AgentBrain()
    # 创建RAG工具
    rag_tool = RAGTool(knowledge_base_path="./combo_knowledge_base")

    # 创建工具注册表
    tool_registry = ToolRegistry()
    tool_registry.register_tool(rag_tool)
    content = investment_knowledge
    # result = rag_tool.run({"action": "add_text", "text": content})
    print("💬 开始RAG演示...")
    agent = ReActAgent(name="TestAgent",llm=brain,tool_registry=tool_registry)

    # 模拟多轮对话
    conversations = [
        "市盈率是什么"
    ]
    user_input="股票是什么"
    response = agent.run(user_input)
    print(f"🤖 助手: {response}")

    # for i, user_input in enumerate(conversations, 1):
    #     print(f"\n--- 对话轮次 {i} ---")
    #     print(f"👤 用户: {user_input}")

    #     response = agent.run(user_input)
    #     print(f"🤖 助手: {response}")


def main():
    # test()
    # memory_rag()
    demo_rag_tool()
    # demo_mcp_tool()

if __name__ == "__main__":
    main()