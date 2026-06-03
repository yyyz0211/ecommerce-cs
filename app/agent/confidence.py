"""记忆与任务状态的辅助计算。

这里把置信度计算单独抽出来，方便后续在 graph / service / tests 里复用，
避免把权重逻辑散落在多个节点中。
"""

from __future__ import annotations


def calculate_confidence(
    model_prob: float,
    rule_score: float,
    context_score: float,
) -> float:
    """计算综合置信度。

    组合公式遵循 plan 中的过渡策略:
      model_prob   × 0.4
      rule_score   × 0.3
      context_score × 0.3

    为了防止上游传入越界值，这里会把每个分项先夹紧到 [0.0, 1.0]。
    最终结果也会再夹紧一次，确保返回值可直接用于阈值判断。
    """
    model_prob = max(0.0, min(1.0, model_prob))
    rule_score = max(0.0, min(1.0, rule_score))
    context_score = max(0.0, min(1.0, context_score))

    confidence = model_prob * 0.4 + rule_score * 0.3 + context_score * 0.3
    return max(0.0, min(1.0, confidence))
