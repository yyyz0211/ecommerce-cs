"""摘要压缩质量评估脚本

不依赖数据库，直接用样本对话测试 _summarize_memory 的输出质量。

用法:
    python tests/eval_summary.py

评估维度:
    1. 长度: 2-4 句话为佳，过长扣分
    2. 信息密度: 是否包含"正在做 / 想达成 / 进展 / 下一步"
    3. 噪声: 是否误入了订单号、原始数据等不该有的内容
"""

import asyncio
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.conversation import Message
from app.services.memory_service import _summarize_memory


# ── 样本对话 ──

SAMPLE_DIALOGUES = [
    {
        "name": "场景1: 查订单 → 查物流",
        "old_summary": "",
        "messages": [
            _make_msg("user", "帮我查一下最近的订单"),
            _make_msg("agent", "您共有 3 笔订单，最近的是一台机械键盘，状态为已发货。"),
            _make_msg("user", "那个机械键盘到哪了"),
            _make_msg("agent", "订单 202605280004 物流：顺丰快递 SF9988776655，正在运输中。"),
        ],
    },
    {
        "name": "场景2: 增量压缩（已有旧摘要）",
        "old_summary": "用户在查询订单物流。物流已查询完成。当前没有待处理任务。",
        "messages": [
            _make_msg("user", "我要退货"),
            _make_msg("agent", "好的，请问您要退哪个订单？"),
            _make_msg("user", "就是刚才那个机械键盘"),
            _make_msg("agent", "已为您提交售后申请。售后编号 8，类型为退货。"),
        ],
    },
    {
        "name": "场景3: 纯闲聊（不应生成有意义的摘要）",
        "old_summary": "",
        "messages": [
            _make_msg("user", "你好"),
            _make_msg("agent", "你好！有什么可以帮您的？"),
            _make_msg("user", "今天天气真好"),
            _make_msg("agent", "是的呢！需要帮您查订单或物流吗？"),
        ],
    },
    {
        "name": "场景4: 长对话压缩（消息超过 10 条）",
        "old_summary": "用户在查询订单。",
        "messages": [
            _make_msg("user", f"问题 {i}") or _make_msg("agent", f"回答 {i}")
            for i in range(15)
        ],
    },
]


def _make_msg(role: str, content: str) -> Message:
    """构造一个伪 Message 对象（只设测试需要的字段）"""
    msg = Message.__new__(Message)
    msg.role = role
    msg.content = content
    return msg


# ── 评分函数 ──

def score_summary(name: str, summary: str, old_summary: str) -> dict:
    """对摘要做启发式评分（不调 LLM）"""
    issues = []
    score = 10

    # 1. 长度检查
    sentences = [s.strip() for s in summary.replace("。", ".").split(".") if s.strip()]
    if len(sentences) == 0:
        issues.append("空摘要")
        score -= 10
    elif len(sentences) > 5:
        issues.append(f"过长 ({len(sentences)} 句)")
        score -= 2

    # 2. 信息密度：检查是否包含主题/目标/进展类词汇
    topic_words = ["查询", "申请", "退货", "退款", "换货", "订单", "物流", "售后", "客服"]
    has_topic = any(w in summary for w in topic_words)
    if not has_topic and old_summary:
        issues.append("缺少主题关键词，可能丢失了上下文")

    # 3. 噪声检查：不应包含订单号、原始数据
    noise_patterns = [
        ("SF", "快递单号"),
        ("20260", "订单号"),
        ("¥", "金额数字"),
        ("x1 x", "原始商品数据"),
    ]
    for pattern, desc in noise_patterns:
        if pattern in summary:
            issues.append(f"含噪声: {desc}")
            score -= 2

    # 4. 与旧摘要重复度检查
    if old_summary and old_summary.strip() == summary.strip():
        issues.append("与旧摘要完全相同，没有增量更新")
        score -= 3

    return {"score": max(0, score), "issues": issues}


# ── 主流程 ──

async def main():
    print("=" * 60)
    print("摘要压缩质量评估")
    print("=" * 60)

    for case in SAMPLE_DIALOGUES:
        print(f"\n{'─' * 60}")
        print(f"【{case['name']}】")
        print(f"旧摘要: {case['old_summary'] or '（无）'}")
        print(f"消息数: {len(case['messages'])} 条")
        print()

        new_summary = await _summarize_memory(
            case["old_summary"], case["messages"]
        )

        result = score_summary(case["name"], new_summary, case["old_summary"])

        print(f"新摘要: {new_summary}")
        print(f"得分: {result['score']}/10")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"  ⚠ {issue}")
        else:
            print("  ✅ 无问题")

    print(f"\n{'=' * 60}")
    print("评估完成。请人工复核每项摘要是否准确反映了对话内容。")


if __name__ == "__main__":
    asyncio.run(main())
