"""京东 FAQ 关键词词库与文档打标。

关键词在这里被定义为“业务概念词”，不是普通分词 token。
本模块只做离线建库和可解释打标，不直接调用 LLM。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Union


KEYWORD_VERSION = "jd_faq_keywords_v1"
CATEGORY_ORDER = ("售后政策", "物流配送", "支付发票", "账户管理")
MAX_SAMPLE_IDS = 5


@dataclass(frozen=True)
class KeywordRule:
    """受控词表中的一个标准业务概念。

    canonical 是最终写入文档 keywords 的标准词。
    aliases 是用户可能说法或 FAQ 原文中的变体，用来帮助匹配到 canonical。
    boost 用来表达某些关键词更能代表主意图，例如“退款时效”比“退款”更具体。
    """

    id: str
    canonical: str
    category: str
    aliases: tuple[str, ...] = ()
    boost: float = 1.0

    @property
    def terms(self) -> tuple[str, ...]:
        return (self.canonical, *self.aliases)


BASE_KEYWORD_RULES: tuple[KeywordRule, ...] = (
    KeywordRule("after_sale.refund", "退款", "售后政策", ("退钱", "钱退回", "款项退回"), 0.95),
    KeywordRule("after_sale.refund_time","退款时效","售后政策",("退款的时效", "退款多久", "退款时效多久", "几天到账", "多久到账", "退款一般几天"),1.4),
    KeywordRule("after_sale.refund_arrival", "退款到账", "售后政策", ("退款到账", "原路退回", "退回账户", "到账时间"), 1.15),
    KeywordRule("after_sale.return_goods", "退货", "售后政策", ("申请退货", "退回商品", "退换货"), 1.1),
    KeywordRule("after_sale.exchange_goods", "换货", "售后政策", ("申请换货", "退换货", "换新"), 1.1),
    KeywordRule("after_sale.no_reason_return", "七天无理由", "售后政策", ("7天无理由", "无理由退货", "七日无理由"), 1.25),
    KeywordRule("after_sale.pickup", "上门取件", "售后政策", ("上门取件", "上门退货", "快递员取件", "取件单"), 1.2),
    KeywordRule("after_sale.pickup_fee", "取件收费", "售后政策", ("取件收费", "上门取件费", "取件费", "收费标准"), 1.15),
    KeywordRule("after_sale.apply", "售后申请", "售后政策", ("申请售后", "提交售后", "售后单"), 1.1),
    KeywordRule("after_sale.repair", "返修", "售后政策", ("返修", "维修", "检测维修"), 1.05),
    KeywordRule("after_sale.warranty", "保修", "售后政策", ("保修", "质保", "三包", "全国联保"), 1.05),
    KeywordRule("after_sale.reject_warranty", "拒保", "售后政策", ("拒保", "不予保修", "不予办理"), 1.1),
    KeywordRule("after_sale.freight_refund", "运费退还", "售后政策", ("退运费", "运费退还", "返回运费", "退货运费"), 1.15),
    KeywordRule("after_sale.quality_issue", "商品质量问题", "售后政策", ("质量问题", "功能性故障", "性能故障"), 1.1),
    KeywordRule("after_sale.missing_parts", "缺件", "售后政策", ("缺件", "配件缺失", "少件"), 1.05),
    KeywordRule("after_sale.logistics_damage", "物流损", "售后政策", ("物流损", "运输损坏", "破损", "漏液"), 1.05),
    KeywordRule("after_sale.fresh_goods", "生鲜售后", "售后政策", ("生鲜", "鲜活易腐", "生鲜商品"), 1.05),
    KeywordRule("after_sale.expired_warranty", "过保", "售后政策", ("过保", "超过三包", "超过保修期"), 1.05),
    KeywordRule("after_sale.invoice_warranty_card", "三包凭证", "售后政策", ("三包凭证", "保修卡", "质保证书"), 1.05),
    KeywordRule("logistics.tracking", "物流查询", "物流配送", ("物流查询", "查物流", "物流信息", "配送信息"), 1.15),
    KeywordRule("logistics.shipping_time", "发货时间", "物流配送", ("发货时间", "什么时候发货", "多久发货"), 1.15),
    KeywordRule("logistics.delivery_time", "配送时效", "物流配送", ("配送时效", "送达时间", "多久送到", "预计送达"), 1.15),
    KeywordRule("logistics.signed", "签收", "物流配送", ("签收", "已签收", "实际签收"), 1.1),
    KeywordRule("logistics.reject_delivery", "拒收", "物流配送", ("拒收", "拒签", "不想收", "不要了"), 1.2),
    KeywordRule("logistics.self_pickup", "自提", "物流配送", ("自提", "自提点", "上门自提"), 1.1),
    KeywordRule("logistics.pickup_locker", "自提柜", "物流配送", ("自提柜", "智能柜", "取件柜"), 1.05),
    KeywordRule("logistics.home_delivery", "送货上门", "物流配送", ("送货上门", "配送上门", "上门配送"), 1.1),
    KeywordRule("logistics.delivery_area", "配送范围", "物流配送", ("配送范围", "支持配送", "无法配送", "配送区域"), 1.1),
    KeywordRule("logistics.freight", "运费", "物流配送", ("运费", "配送费", "快递费", "基础运费"), 1.1),
    KeywordRule("logistics.jd_precise", "京准达", "物流配送", ("京准达", "精准达"), 1.2),
    KeywordRule("logistics.211", "211限时达", "物流配送", ("211限时达", "211", "限时达"), 1.2),
    KeywordRule("logistics.abnormal", "快递异常", "物流配送", ("快递异常", "物流异常", "配送异常", "未收到货"), 1.1),
    KeywordRule("logistics.modify_address", "修改收货地址", "物流配送", ("修改地址", "改地址", "收货地址", "配送地址"), 1.15),
    KeywordRule("logistics.appointment", "配送预约", "物流配送", ("预约配送", "配送预约", "预约送货"), 1.1),
    KeywordRule("logistics.large_item", "大件配送", "物流配送", ("大件", "大件商品", "冰箱", "洗衣机", "空调"), 1.05),
    KeywordRule("payment.method", "支付方式", "支付发票", ("支付方式", "付款方式", "如何支付", "怎么支付"), 1.2),
    KeywordRule("payment.online", "在线支付", "支付发票", ("在线支付", "网上支付", "立即支付"), 1.05),
    KeywordRule("payment.combined", "组合支付", "支付发票", ("组合支付", "混合支付", "同时支付"), 1.15),
    KeywordRule("payment.cod", "货到付款", "支付发票", ("货到付款", "到付", "货到付"), 1.2),
    KeywordRule("payment.baitiao", "白条", "支付发票", ("白条", "京东白条", "打白条"), 1.2),
    KeywordRule("payment.jdecard", "京东E卡", "支付发票", ("京东E卡", "E卡", "京东e卡"), 1.2),
    KeywordRule("payment.jdcard", "京东卡", "支付发票", ("京东卡",), 1.15),
    KeywordRule("payment.failed", "支付失败", "支付发票", ("支付失败", "付款失败", "无法支付", "付不了"), 1.15),
    KeywordRule("payment.installment", "分期付款", "支付发票", ("分期", "分期付款", "分期支付"), 1.1),
    KeywordRule("payment.corporate_transfer", "对公转账", "支付发票", ("对公转账", "公司转账", "银行转账"), 1.1),
    KeywordRule("invoice.invoice", "发票", "支付发票", ("发票", "票据"), 1.05),
    KeywordRule("invoice.issue", "开发票", "支付发票", ("开发票", "开票", "发票开具", "申请发票"), 1.2),
    KeywordRule("invoice.title", "发票抬头", "支付发票", ("发票抬头", "公司抬头", "个人抬头"), 1.2),
    KeywordRule("invoice.modify", "发票修改", "支付发票", ("修改发票", "发票修改", "改发票", "发票信息修改"), 1.15),
    KeywordRule("invoice.reissue", "发票补开", "支付发票", ("补开发票", "发票补开", "补开"), 1.15),
    KeywordRule("invoice.electronic", "电子发票", "支付发票", ("电子发票", "电票"), 1.1),
    KeywordRule("invoice.vat", "增值税发票", "支付发票", ("增值税发票", "专票", "增票"), 1.1),
    KeywordRule("promotion.coupon", "优惠券", "支付发票", ("优惠券", "券", "优惠码"), 1.05),
    KeywordRule("promotion.jingdou", "京豆", "支付发票", ("京豆", "豆"), 1.05),
    KeywordRule("account.login_password", "登录密码", "账户管理", ("登录密码", "登陆密码", "账户密码"), 1.15),
    KeywordRule("account.payment_password", "支付密码", "账户管理", ("支付密码", "付款密码"), 1.15),
    KeywordRule("account.modify_payment_password", "修改支付密码","账户管理",("修改支付密码", "改支付密码", "改一下支付密码", "更换支付密码", "支付密码怎么改", "付款密码怎么改", "支付密码在哪里改"),1.3),
    KeywordRule("account.retrieve_payment_password", "找回支付密码", "账户管理", ("找回支付密码", "忘记支付密码", "支付密码忘了", "付款密码忘记"), 1.3),
    KeywordRule("account.modify_login_password", "修改登录密码", "账户管理", ("修改登录密码", "改登录密码", "更换登录密码"), 1.2),
    KeywordRule("account.retrieve_login_password", "找回登录密码", "账户管理", ("找回登录密码", "忘记登录密码", "登录密码忘了"), 1.2),
    KeywordRule("account.bind_phone", "手机号绑定", "账户管理", ("绑定手机号", "手机绑定", "绑定手机"), 1.1),
    KeywordRule("account.modify_phone", "修改手机号", "账户管理", ("修改手机号", "改手机号", "换绑手机号", "更换手机号"), 1.15),
    KeywordRule("account.real_name", "实名认证", "账户管理", ("实名认证", "实名", "身份认证"), 1.15),
    KeywordRule("account.security", "账户安全", "账户管理", ("账户安全", "账号安全", "安全中心", "安全设置"), 1.1),
    KeywordRule("account.plus", "PLUS会员", "账户管理", ("PLUS会员", "plus会员", "PLUS", "plus"), 1.15),
    KeywordRule("account.cancel", "注销账户", "账户管理", ("注销账户", "账号注销", "注销账号"), 1.15),
    KeywordRule("account.frozen", "账户冻结", "账户管理", ("账户冻结", "账号冻结", "冻结账户"), 1.1),
    KeywordRule("account.appeal", "账号申诉", "账户管理", ("账号申诉", "账户申诉", "申诉"), 1.05),
    KeywordRule("account.balance", "账户余额", "账户管理", ("账户余额", "余额", "小金库"), 1.05),
)


def _normalize_for_match(text: str) -> str:
    # 规则匹配前先去掉标点和空白，避免“7天无理由”和“7 天无理由”
    # 因为格式差异匹配不上。
    value = text or ""
    value = value.lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value)


def _count_term(normalized_text: str, term: str) -> int:
    normalized_term = _normalize_for_match(term)
    if not normalized_term:
        return 0
    return normalized_text.count(normalized_term)


def _as_text(row: dict[str, Any], field: str) -> str:
    return str(row.get(field) or "")


def _source_text(row: dict[str, Any]) -> str:
    return _as_text(row, "text") or _as_text(row, "answer")


def _score_rule(row: dict[str, Any], rule: Union[KeywordRule, dict[str, Any]]) -> Optional[dict[str, Any]]:
    """计算一条 FAQ/chunk 对某个关键词规则的命中分。

    打分不是为了做最终检索排序，而是为了离线判断“这条文档该不该打上这个关键词”。
    标题权重最高，因为 FAQ 标题通常最接近用户真实问题；正文权重最低，因为长答案里
    很容易顺带提到别的概念。
    """
    category = _as_text(row, "category")
    question = _as_text(row, "question")
    section_title = _as_text(row, "section_title")
    text = _source_text(row)
    fields = (
        ("question", question, 6.0),
        ("section_title", section_title, 3.0),
        ("text", text, 1.0),
    )

    terms = tuple(rule.terms) if isinstance(rule, KeywordRule) else (rule["canonical"], *rule.get("aliases", []))
    canonical = rule.canonical if isinstance(rule, KeywordRule) else str(rule["canonical"])
    rule_category = rule.category if isinstance(rule, KeywordRule) else str(rule.get("category") or "")
    boost = rule.boost if isinstance(rule, KeywordRule) else float(rule.get("boost") or 1.0)

    score = 0.0
    evidence: list[str] = []
    for field_name, field_text, field_weight in fields:
        normalized_text = _normalize_for_match(field_text)
        if not normalized_text:
            continue
        for term in terms:
            term_count = _count_term(normalized_text, term)
            if term_count <= 0:
                continue
            # 同一个概念出现在标题里，比出现在正文里更能说明这条 FAQ 的主意图。
            score += field_weight * term_count
            evidence.append(f"{field_name}:{term}")

    if score <= 0:
        return None
    same_category = category == rule_category
    if same_category:
        # 分类一致只做小幅加分，不直接决定是否打标。
        # 这样可以兼容“发票保修”这类跨分类词同时出现的真实 FAQ。
        score += 0.5
    return {
        "canonical": canonical,
        "category": rule_category,
        "score": score * boost,
        "raw_score": score,
        "same_category": same_category,
        "evidence": evidence[:5],
    }


def _iter_candidate_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("kb_candidate") is not False]


def build_keyword_vocabulary(rows: Iterable[dict[str, Any]], *, min_doc_count: int = 1) -> dict[str, Any]:
    """根据当前 FAQ 数据过滤受控词表，并统计每个关键词覆盖的文档。

    BASE_KEYWORD_RULES 是候选规则，不代表每个词都一定进入本次知识库。
    这里会根据真实 FAQ 是否命中过滤一遍，避免词库里保留完全没有文档支撑的关键词。
    """
    candidate_rows = _iter_candidate_rows(rows)
    keyword_items: list[dict[str, Any]] = []

    for rule in BASE_KEYWORD_RULES:
        matched_ids: list[str] = []
        sample_questions: list[str] = []
        for row in candidate_rows:
            if not _score_rule(row, rule):
                continue
            matched_ids.append(str(row.get("id") or row.get("faq_id") or ""))
            if len(sample_questions) < MAX_SAMPLE_IDS:
                sample_questions.append(_as_text(row, "question"))

        if len(matched_ids) < min_doc_count:
            # 低于覆盖阈值的词不进入词库，避免过细或无数据支撑的关键词污染检索。
            continue

        keyword_items.append(
            {
                "id": rule.id,
                "canonical": rule.canonical,
                "category": rule.category,
                "aliases": list(rule.aliases),
                "boost": rule.boost,
                "document_count": len(matched_ids),
                "sample_faq_ids": matched_ids[:MAX_SAMPLE_IDS],
                "sample_questions": sample_questions,
            }
        )

    category_rank = {category: index for index, category in enumerate(CATEGORY_ORDER)}
    keyword_items.sort(
        key=lambda item: (
            category_rank.get(item["category"], 99),
            -int(item["document_count"]),
            item["canonical"],
        )
    )

    return {
        "version": KEYWORD_VERSION,
        "document_count": len(candidate_rows),
        "keyword_count": len(keyword_items),
        "keywords": keyword_items,
    }


def _keyword_entries(vocabulary: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in vocabulary.get("keywords", [])]


def extract_document_keywords(
    row: dict[str, Any],
    vocabulary: dict[str, Any],
    *,
    max_keywords: int = 8,
) -> dict[str, Any]:
    """从受控词表中为一条 FAQ 或 chunk 选择关键词。

    输出的 keywords 是后续 BM25、embedding、rerank 都会用到的结构化信号。
    因此这里宁可少打一点，也不要把正文里偶然出现的弱相关词全部打进去。
    """
    matches: list[dict[str, Any]] = []
    for entry in _keyword_entries(vocabulary):
        match = _score_rule(row, entry)
        if not match:
            continue
        primary_hit = any(
            evidence.startswith("question:") or evidence.startswith("section_title:")
            for evidence in match["evidence"]
        )
        if not match["same_category"] and not primary_hit and float(match["raw_score"]) < 3.0:
            # 跨分类且只在正文里弱命中的词容易误伤。
            # 例如售后 FAQ 正文里提到“自提”，不代表这条 FAQ 属于物流自提问题。
            continue
        matches.append(
            {
                **match,
                "boost": float(entry.get("boost") or 1.0),
            }
        )

    matches.sort(key=lambda item: (-float(item["score"]), -float(item["boost"]), item["canonical"]))
    selected = matches[:max_keywords]
    keywords = [item["canonical"] for item in selected]
    return {
        "keywords": keywords,
        "keyword_version": str(vocabulary.get("version") or KEYWORD_VERSION),
        "keyword_evidence": {item["canonical"]: item["evidence"] for item in selected},
        "keyword_confidence": {
            item["canonical"]: round(min(1.0, float(item["score"]) / 8.0), 3) for item in selected
        },
    }


def annotate_record_keywords(
    row: dict[str, Any],
    vocabulary: dict[str, Any],
    *,
    max_keywords: int = 8,
) -> dict[str, Any]:
    """返回带关键词字段的新记录，保持原始字段不变。"""
    output = dict(row)
    output.update(extract_document_keywords(row, vocabulary, max_keywords=max_keywords))
    return output


def extract_query_keywords(query: str, *, max_keywords: int = 8) -> list[str]:
    """把用户口语 query 映射到受控词表标准词。

    这个函数使用内置规则，主要作为 query 侧兜底。
    正常线上会优先用 keyword_vocabulary.load_keyword_vocabulary() 读正式词库。
    """
    vocabulary = {
        "version": KEYWORD_VERSION,
        "keywords": [
            {
                "id": rule.id,
                "canonical": rule.canonical,
                "category": rule.category,
                "aliases": list(rule.aliases),
                "boost": rule.boost,
            }
            for rule in BASE_KEYWORD_RULES
        ],
    }
    return extract_query_keywords_from_vocabulary(query, vocabulary, max_keywords=max_keywords)


def extract_query_keywords_from_vocabulary(
    query: str,
    vocabulary: dict[str, Any],
    *,
    max_keywords: int = 8,
) -> list[str]:
    """使用正式关键词词库把用户 query 映射到标准关键词。

    这里把 query 当成一条只有 question 的“伪文档”来跑同一套规则，
    这样文档打标和 query 映射使用相同的 canonical/aliases 逻辑。
    """
    row = {
        "category": "",
        "question": query,
        "text": "",
    }
    matches: list[dict[str, Any]] = []
    for entry in _keyword_entries(vocabulary):
        match = _score_rule(row, entry)
        if not match:
            continue
        matches.append(match)
    matches.sort(key=lambda item: (-float(item["score"]), item["canonical"]))
    return _ordered_unique(item["canonical"] for item in matches)[:max_keywords]


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def annotate_chunk_keywords(
    row: dict[str, Any],
    vocabulary: dict[str, Any],
    *,
    faq_keywords: Optional[list[str]] = None,
    max_keywords: int = 8,
) -> dict[str, Any]:
    """给 chunk 打关键词；chunk 局部命中优先，再继承所属 FAQ 的关键词。

    chunk 很短，可能只截到答案的一部分，局部文本不一定包含完整主题词。
    继承 FAQ 关键词可以保留上层主题，局部关键词则帮助定位更精确的证据片段。
    """
    output = annotate_record_keywords(row, vocabulary, max_keywords=max_keywords)
    local_keywords = output.get("keywords", [])
    inherited_keywords = faq_keywords or []
    output["keywords"] = _ordered_unique([*local_keywords, *inherited_keywords])[:max_keywords]
    return output
