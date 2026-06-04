"""记忆与任务状态的辅助计算。

这里把任务状态的启发式分数计算单独抽出来，方便后续在 graph / service / tests 里复用，
避免把权重逻辑散落在多个节点中。

注意：这里返回的是启发式分数，不是模型校准后的真实概率。
"""

from __future__ import annotations


def calculate_heuristic_score(
    model_signal: float,
    rule_signal: float,
    context_signal: float,
) -> float:
    """计算任务状态的启发式分数。

    组合公式遵循当前过渡策略:
      model_signal   × 0.4
      rule_signal    × 0.3
      context_signal × 0.3

    这些输入目前都是规则化信号，不代表真实模型概率。
    为了防止上游传入越界值，这里会把每个分项先夹紧到 [0.0, 1.0]。
    最终结果也会再夹紧一次，确保返回值可直接用于阈值判断。
    """
    model_signal = max(0.0, min(1.0, model_signal))
    rule_signal = max(0.0, min(1.0, rule_signal))
    context_signal = max(0.0, min(1.0, context_signal))

    score = model_signal * 0.4 + rule_signal * 0.3 + context_signal * 0.3
    return max(0.0, min(1.0, score))


def calculate_confidence(
    model_prob: float,
    rule_score: float,
    context_score: float,
) -> float:
    """兼容旧调用入口，内部转发到启发式分数实现。"""
    return calculate_heuristic_score(
        model_signal=model_prob,
        rule_signal=rule_score,
        context_signal=context_score,
    )
