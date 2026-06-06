"""Agent tool contract tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.tools.ecommerce import execute_tool, submit_after_sale


def test_submit_after_sale_schema_uses_sale_type():
    schema = submit_after_sale.args_schema.model_json_schema()

    assert "sale_type" in schema["properties"]
    assert "type_" not in schema["properties"]


@pytest.mark.asyncio
async def test_submit_after_sale_accepts_type_alias():
    record = SimpleNamespace(id=3, type="refund", status="pending")
    db = AsyncMock()

    with patch("app.agent.tools.ecommerce._resolve_order_id", AsyncMock(return_value=(18, None))), \
         patch("app.agent.tools.ecommerce.create_after_sale", AsyncMock(return_value=record)) as mock_create:

        result = await execute_tool(
            "submit_after_sale",
            {"order_id": "202605280001", "type": "refund", "reason": "商品破损"},
            db=db,
            user_id=7,
        )

    assert result.ok is True
    assert result.data["type_label"] == "退款"
    assert result.data["status_label"] == "待审核"
    mock_create.assert_awaited_once_with(db, 7, 18, "refund", "商品破损")
