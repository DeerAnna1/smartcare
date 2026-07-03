"""PostgreSQL checkpointer 集成测试。"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_build_consultation_graph_with_checkpoint_fallback():
    """当 PostgreSQL checkpointer 初始化失败时，应回退到无 checkpointer 模式。"""
    from app.orchestrators.consultation import build_consultation_graph_with_checkpoint

    # 模拟 AsyncPostgresSaver 导入失败
    with patch.dict("sys.modules", {"langgraph.checkpoint.postgres.aio": None}):
        graph = await build_consultation_graph_with_checkpoint()
        # 应该成功返回（回退到无 checkpointer 模式）
        assert graph is not None


@pytest.mark.asyncio
async def test_run_consultation_turn_checkpoint_param():
    """run_consultation_turn 应支持 use_checkpoint 参数。"""
    from app.orchestrators.consultation import run_consultation_turn
    import inspect

    sig = inspect.signature(run_consultation_turn)
    assert "use_checkpoint" in sig.parameters
    assert sig.parameters["use_checkpoint"].default is False


@pytest.mark.asyncio
async def test_cleanup_checkpoint_function_exists():
    """cleanup_checkpoint 函数应可导入且可调用。"""
    from app.orchestrators.consultation import cleanup_checkpoint
    import inspect

    assert callable(cleanup_checkpoint)
    sig = inspect.signature(cleanup_checkpoint)
    assert "session_id" in sig.parameters
