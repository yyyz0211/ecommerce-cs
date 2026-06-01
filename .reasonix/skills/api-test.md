---
name: api-test
description: 用 curl 冒烟测试全部 API 端点，验证是否正常返回
---
## api-test — API 冒烟测试

测试全部 14 个后端端点是否正常返回。

### 操作步骤

1. 先登录获取 token:
   `curl -s -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"username":"buyer1","password":"123456"}'`
   从响应中提取 access_token

2. 用 token 逐个测试以下端点，检查返回状态码是否正常:

   - GET /api/users/me
   - PATCH /api/users/me -d '{"phone":"13900001111"}'
   - POST /api/auth/refresh
   - GET /api/orders?page=1&size=3
   - GET /api/orders/10 (第一个订单 ID)
   - GET /api/orders/10/logistics
   - POST /api/orders -d '{"items":[{"product_name":"测试","quantity":1,"price":9.9}]}'
   - PATCH /api/orders/{new_id}/cancel
   - POST /api/after-sales -d '{"order_id":10,"type":"refund","reason":"测试"}'
   - GET /api/after-sales
   - POST /api/chat/session
   - GET /api/chat/history/{session_id}

3. 报告结果: 成功 N 个 / 失败 N 个，列出失败的端点和错误信息

### 注意事项

- 后端必须已在 8000 端口运行
- 每个端点都打印简要结果（状态码 + 首行 JSON）
