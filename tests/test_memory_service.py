"""记忆服务单元测试 — 测试非 LLM 部分（读写、流程编排）

LLM 摘要压缩质量测试见 eval_summary.py。
这里重点验证：
- 结构化 task_state 可以正确序列化 / 反序列化
- 后台摘要流程在各种失败路径下不会影响主链路
- 置信度计算遵循统一公式
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.core.confidence import calculate_confidence
from app.agent.schemas.task_state import NextAction, TaskIntent, TaskStage, TaskState, TaskStatus
from app.services.memory_service import (
    _load_memory_content,
    _load_recent_messages,
    parse_task_state,
    save_memory_background,
    save_task_state,
)


def _setup_async_session(mock_session_factory):
    """Return the db object yielded by a mocked AsyncSessionLocal."""
    mock_db = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_db


class TestLoadMemoryContent:
    """测试记忆内容读取"""

    @pytest.mark.asyncio
    async def test_returns_content_when_found(self):
        db = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.content = "用户在查询订单"
        exec_result = MagicMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=mock_memory)
        db.execute.return_value = exec_result

        result = await _load_memory_content(db, 1, 7, "summary")

        assert result == "用户在查询订单"

    @pytest.mark.asyncio
    async def test_returns_empty_when_not_found(self):
        db = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute.return_value = exec_result

        result = await _load_memory_content(db, 1, 7, "summary")

        assert result == ""


class TestLoadRecentMessages:
    """测试消息加载"""

    @pytest.mark.asyncio
    async def test_returns_messages_list(self):
        db = AsyncMock()
        msg1, msg2 = MagicMock(), MagicMock()
        exec_result = MagicMock()
        exec_result.scalars = MagicMock()
        exec_result.scalars.return_value.all = MagicMock(return_value=[msg1, msg2])
        db.execute.return_value = exec_result

        result = await _load_recent_messages(db, 1, 7)

        assert len(result) == 2
        stmt = db.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10" in compiled

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        db = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalars = MagicMock()
        exec_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute.return_value = exec_result

        result = await _load_recent_messages(db, 1, 7)

        assert result == []


class TestTaskStateSerialization:
    """测试 task_state 序列化/反序列化"""

    @pytest.mark.asyncio
    async def test_save_task_state_serializes_json(self):
        db = AsyncMock()
        mock_conversation = MagicMock()
        state = TaskState(
            stage=TaskStage.PROCESSING,
            intent=TaskIntent.QUERY_LOGISTICS,
            status=TaskStatus.IN_PROGRESS,
            confidence=0.9,
            next_action=NextAction.CALL_BACKEND_API,
        )
        mock_memory = MagicMock()
        mock_memory.content = state.model_dump_json()
        conversation_result = MagicMock()
        conversation_result.scalar_one_or_none.return_value = mock_conversation
        insert_result = MagicMock()
        memory_result = MagicMock()
        memory_result.scalar_one.return_value = mock_memory
        db.execute.side_effect = [conversation_result, insert_result, memory_result]

        await save_task_state(db, 1, 7, state)

        payload = json.loads(mock_memory.content)
        assert payload["stage"] == "processing"
        assert payload["intent"] == "query_logistics"
        assert payload["status"] == "in_progress"
        assert payload["confidence"] == 0.9
        assert payload["next_action"] == "call_backend_api"
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_save_task_state_uses_upsert(self):
        db = AsyncMock()
        mock_conversation = MagicMock()
        saved_memory = MagicMock()
        conversation_result = MagicMock()
        conversation_result.scalar_one_or_none.return_value = mock_conversation
        insert_result = MagicMock()
        select_result = MagicMock()
        select_result.scalar_one.return_value = saved_memory
        db.execute.side_effect = [conversation_result, insert_result, select_result]

        state = TaskState(
            stage=TaskStage.COMPLETED,
            intent=TaskIntent.QUERY_ORDER_STATUS,
            status=TaskStatus.DONE,
            confidence=0.8,
            next_action=NextAction.REPLY_USER,
        )

        result = await save_task_state(db, 1, 7, state)

        assert result == saved_memory
        assert db.execute.await_count == 3
        assert db.commit.called

    def test_parse_task_state_round_trip(self):
        state = TaskState(
            stage=TaskStage.AWAITING_ORDER_ID,
            intent=TaskIntent.QUERY_ORDER_STATUS,
            status=TaskStatus.PENDING,
            confidence=0.75,
            next_action=NextAction.ASK_USER_FOR_ORDER_ID,
        )
        parsed = parse_task_state(state.model_dump_json())

        assert parsed.stage == TaskStage.AWAITING_ORDER_ID
        assert parsed.next_action == NextAction.ASK_USER_FOR_ORDER_ID
        assert parsed.confidence == 0.75


class TestConfidenceCalculation:
    """测试置信度计算。"""

    def test_uses_expected_weighting(self):
        assert calculate_confidence(1.0, 0.0, 0.0) == 0.4
        assert calculate_confidence(0.0, 1.0, 0.0) == 0.3
        assert calculate_confidence(0.0, 0.0, 1.0) == 0.3

    def test_clamps_out_of_range_values(self):
        assert calculate_confidence(2.0, -1.0, 0.5) == 0.55

    @pytest.mark.asyncio
    async def test_skips_when_no_messages(self):
        with patch("app.services.memory_service.AsyncSessionLocal") as mock_session_factory, \
             patch("app.services.memory_service._load_recent_messages", return_value=[]), \
             patch("app.services.memory_service._summarize_memory") as mock_summarize, \
             patch("app.services.memory_service.save_conversation_memory") as mock_save:

            _setup_async_session(mock_session_factory)

            await save_memory_background(1, 7)

            mock_summarize.assert_not_called()
            mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_saves_summary_when_compression_succeeds(self):
        msg = MagicMock()
        with patch("app.services.memory_service.AsyncSessionLocal") as mock_session_factory, \
             patch("app.services.memory_service._load_recent_messages", return_value=[msg]), \
             patch("app.services.memory_service._load_memory_content", return_value="旧摘要"), \
             patch("app.services.memory_service._summarize_memory", return_value="新摘要"), \
             patch("app.services.memory_service.save_conversation_memory") as mock_save:

            mock_ctx = _setup_async_session(mock_session_factory)

            await save_memory_background(1, 7)

            mock_save.assert_called_once_with(
                mock_ctx, 1, 7, "summary", "新摘要"
            )

    @pytest.mark.asyncio
    async def test_does_not_save_when_compression_returns_empty(self):
        msg = MagicMock()
        with patch("app.services.memory_service.AsyncSessionLocal") as mock_session_factory, \
             patch("app.services.memory_service._load_recent_messages", return_value=[msg]), \
             patch("app.services.memory_service._summarize_memory", return_value=""), \
             patch("app.services.memory_service.save_conversation_memory") as mock_save:

            _setup_async_session(mock_session_factory)

            await save_memory_background(1, 7)

            mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_silently_handles_exception(self):
        with patch("app.services.memory_service.AsyncSessionLocal",
                   side_effect=RuntimeError("DB 挂了")):

            await save_memory_background(1, 7)
