---
name: subagent-driven-development
description: 将独立任务委派给子 Agent，并行执行后合并结果
runAs: subagent
---
## subagent-driven-development — 子 Agent 驱动开发

将大任务拆解为独立子任务，并行委派给 explore/research/review 等子 Agent。

### 适用场景

- 需要同时调查多个模块
- 需要兼顾代码审查和外部文档查询
- 上下文太大，超出单次对话能力

### 流程

1. **拆解**：把任务拆成 2-4 个独立的子任务
2. **委派**：`explore` 负责代码调查，`research` 负责代码+网络，`review` 负责审查
3. **合并**：收集所有子 Agent 的返回结果
4. **决策**：根据合并结果决定下一步

### 常用模式

- 改代码前：`explore("相关模块的实现")` + `research("官方文档最新方案")`
- 改完代码后：`review("检查变更")` + `security-review("安全检查")`
- 排查问题：`explore("搜索所有调用点")` + `explore("搜索错误日志相关代码")`

### 原则

- 子任务必须完全独立，不共享状态
- 每个子 Agent 的 prompt 要自包含，描述清楚上下文
- 不要为简单任务（单文件搜索）创建子 Agent
