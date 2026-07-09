import asyncio
import json
import sys
import os
from pathlib import Path

# sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'HelloAgents'))
from src.protocols.mcp import MCPClient


async def test_weather_server():
    # server_script = os.path.join(os.path.dirname(__file__), "mcpServer.py")
    # client = MCPClient(["python", server_script])

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
    client = MCPClient(
        [sys.executable, "-m", module_name],
        cwd=str(project_root),  # 工作目录设为根目录
        env=env                 # 传入修正后的环境变量
    )

    try:
        async with client:
            # 测试1: 获取服务器信息
            info = json.loads(await client.call_tool("get_server_info", {}))
            print(f"服务器: {info['name']} v{info['version']}")

            # 测试2: 列出支持的城市
            cities = json.loads(await client.call_tool("list_supported_cities", {}))
            print(f"支持城市: {cities['count']} 个")

            # 测试3: 查询北京天气
            weather = json.loads(await client.call_tool("get_weather", {"city": "北京"}))
            if "error" not in weather:
                print(f"\n北京天气: {weather['temperature']}°C, {weather['condition']}")

            # 测试4: 查询深圳天气
            weather = json.loads(await client.call_tool("get_weather", {"city": "深圳"}))
            if "error" not in weather:
                print(f"深圳天气: {weather['temperature']}°C, {weather['condition']}")

            print("\n✅ 所有测试完成！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")


if __name__ == "__main__":
    asyncio.run(test_weather_server())