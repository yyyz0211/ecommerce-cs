"""Agent 子系统。

目录分层:
- core: LangGraph 编排、runtime、状态机和辅助计算
- schemas: Agent 内部结构化数据模型
- tools: LLM 可调用工具及工具执行器
- prompts.py: 系统提示词

根目录下的 graph/runtime/state 等文件是兼容旧导入路径的薄转发层。
新代码优先从 core / schemas / tools 子包导入。
"""
