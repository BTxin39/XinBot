"""临时测试 Agent 能否正常初始化。"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.core.agent import Agent

print("init ok")
a = Agent()
print("agent created, tools:", len(a.tool_registry.list_tools()))
a.shutdown()
print("done")
