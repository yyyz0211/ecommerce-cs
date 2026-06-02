---
name: test-driven-development
description: TDD 工作流：先写测试 → 再写实现 → 验证通过
runAs: subagent
---
## test-driven-development — TDD 工作流

Red → Green → Refactor。

### 流程

1. **Red — 先写测试**
   - 明确要测试的接口/函数
   - 用 curl 写一个会失败的测试场景
   - 确认测试确实失败（不是假阳性）

2. **Green — 最小实现**
   - 写刚好让测试通过的代码
   - 运行测试验证通过

3. **Refactor — 重构**
   - 消除重复代码
   - 检查边界情况（空值、超长输入、权限校验）
   - 运行测试确认仍然通过

### 原则

- 测试是需求的可执行文档
- 不要跳过 Red 阶段——先看到失败才能确认测试有效
- 每步都验证，不要攒到最后
