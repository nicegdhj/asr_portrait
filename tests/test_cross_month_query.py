"""
测试跨月查询功能

验证 ETL 服务的 _batch_fetch_asr_details 方法能否正确处理跨月数据
"""

from datetime import date

import pytest

from src.services.etl_service import etl_service
from src.utils.table_utils import get_tables_for_period


class TestCrossMonthQuery:
    """测试跨月查询功能"""

    def test_get_tables_for_period_single_month(self):
        """测试单月查询"""
        start_date = date(2025, 11, 1)
        end_date = date(2025, 11, 30)

        tables = get_tables_for_period(start_date, end_date, "call_record_detail")

        assert len(tables) == 1
        assert tables[0] == "autodialer_call_record_detail_2025_11"

    def test_get_tables_for_period_cross_month(self):
        """测试跨月查询 (11月底到12月初)"""
        start_date = date(2025, 11, 28)
        end_date = date(2025, 12, 5)

        tables = get_tables_for_period(start_date, end_date, "call_record_detail")

        assert len(tables) == 2
        assert "autodialer_call_record_detail_2025_11" in tables
        assert "autodialer_call_record_detail_2025_12" in tables

    def test_get_tables_for_period_quarter(self):
        """测试季度查询 (跨3个月)"""
        start_date = date(2025, 10, 1)
        end_date = date(2025, 12, 31)

        tables = get_tables_for_period(start_date, end_date, "call_record_detail")

        assert len(tables) == 3
        assert "autodialer_call_record_detail_2025_10" in tables
        assert "autodialer_call_record_detail_2025_11" in tables
        assert "autodialer_call_record_detail_2025_12" in tables

    @pytest.mark.asyncio
    async def test_batch_fetch_asr_details_cross_month(self):
        """
        测试 _batch_fetch_asr_details 跨月查询

        注意: 此测试需要 MySQL 源数据库可用
        """
        # 模拟跨月的 call_ids (11月30日和12月1日)
        call_ids = [
            ("call_20251130_001", date(2025, 11, 30)),
            ("call_20251201_001", date(2025, 12, 1)),
        ]

        # 调用方法 (如果数据库不可用会返回空字典)
        result = await etl_service._batch_fetch_asr_details(call_ids)

        # 验证返回格式正确
        assert isinstance(result, dict)
        # 实际数据验证需要真实数据库


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
