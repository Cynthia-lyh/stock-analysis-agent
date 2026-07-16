from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(
    api_key = os.getenv("DEEPSEEK_API_KEY"),
    base_url = os.getenv("DEEPSEEK_API_URL"))


class AgentBrain:
    """Agent 的大脑，负责思考与决策"""

    def __init__(self,model="deepseek-v4-flash"):
        self.model = model

    def think(self,messages,stream=False):
        """核心思考函数：接收提示，返回模型的思考结果"""
        print("\n\n正在请求模型，请稍等...")
        print(f"messages: {messages}")
        try:
            # 使用客户端调用 Chat Completions API（v1.x 版本写法）
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.5,  # 控制创造性，越低越专注
                # max_tokens=500,    # 控制回复长度
                extra_body={"thinking": {"type": "disabled"}}, #思考模式
                stream=stream #流式输出
            )
            content = response.choices[0].message.content
            print(f"模型思考结果: {content}")
            return content
        except Exception as e:
            return f"思考过程出错: {e}"
        
    

# 简单测试一下大脑是否工作
# if __name__ == "__main__":
#     brain = AgentBrain()
#     test_prompt = "你好，请简单介绍一下你自己。"
#     print("测试提问：", test_prompt)
#     print("大脑回复：", brain.think(test_prompt))