"""记忆服务单元测试 — 测试非 LLM 部分（读写、流程编排）

LLM 摘要压缩质量测试见 eval_summary.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.memory_service import (
    _load_memory_content,
    _load_recent_messages,
    save_memory_background,
)


class TestLoadMemoryContent:
    """测试记忆内容读取"""

    @pytest.mark.asyncio
    async def test_returns_content_when_found(self):
        db = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.content = "用户在查询订单"
        # 构造 execute 返回的对象，scalar_one_or_none() 调用返回 mock_memory
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

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        db = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalars = MagicMock()
        exec_result.scalars.return_value.all = MagicMock(return_value=[])
        db.execute.return_value = exec_result

        result = await _load_recent_messages(db, 1, 7)

        assert result == []


class TestSaveMemoryBackground:
    """测试后台记忆更新流程编排"""

    @pytest.mark.asyncio
    async def test_skips_when_no_messages(self):
        """没有消息时直接跳过，不写任何记忆"""
        with patch("app.services.memory_service.AsyncSessionLocal") as mock_session_factory, \
             patch("app.services.memory_service._load_recent_messages", return_value=[]), \
             patch("app.services.memory_service._summarize_memory") as mock_summarize, \
             patch("app.services.memory_service.save_conversation_memory") as mock_save:

            await save_memory_background(1, 7)

            mock_summarize.assert_not_called()
            mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_saves_summary_when_compression_succeeds(self):
        """压缩成功时写入 summary"""
        msg = MagicMock()
        with patch("app.services.memory_service.AsyncSessionLocal") as mock_session_factory, \
             patch("app.services.memory_service._load_recent_messages", return_value=[msg]), \
             patch("app.services.memory_service._load_memory_content", return_value="旧摘要"), \
             patch("app.services.memory_service._summarize_memory", return_value="新摘要"), \
             patch("app.services.memory_service.save_conversation_memory") as mock_save:

            mock_ctx = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_ctx

            await save_memory_background(1, 7)

            mock_save.assert_called_once_with(
                mock_ctx, 1, 7, "summary", "新摘要"
            )

    @pytest.mark.asyncio
    async def test_does_not_save_when_compression_returns_empty(self):
        """压缩失败（返回空字符串）时不写入，旧摘要保持不变"""
        msg = MagicMock()
        with patch("app.services.memory_service.AsyncSessionLocal"), \
             patch("app.services.memory_service._load_recent_messages", return_value=[msg]), \
             patch("app.services.memory_service._summarize_memory", return_value=""), \
             patch("app.services.memory_service.save_conversation_memory") as mock_save:

            await save_memory_background(1, 7)

            mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_silently_handles_exception(self):
        """内部异常不向外传播"""
        with patch("app.services.memory_service.AsyncSessionLocal",
                   side_effect=RuntimeError("DB 挂了")):

            # 不抛异常
            await save_memory_background(1, 7)
