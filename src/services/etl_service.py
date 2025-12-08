"""
ETL 服务 - 数据抽取与转换

从 MySQL 源数据库同步通话记录到 PostgreSQL 画像存储
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_portrait_db, get_source_db, is_source_db_available
from src.models.portrait.call_enriched import CallRecordEnriched
from src.utils.table_utils import (
    get_call_record_table,
    get_call_record_detail_table,
    get_tables_for_period,
    NUMBER_STATUS_MAP,
)


class ETLService:
    """
    ETL 服务类

    负责从源数据库同步通话记录到画像存储
    """

    async def sync_call_records(
        self,
        target_date: date,
        batch_size: int = 100,  # 降低批次大小避免参数过多
    ) -> dict[str, Any]:
        """
        同步指定日期的通话记录

        Args:
            target_date: 目标日期
            batch_size: 批量处理大小

        Returns:
            同步结果统计
        """
        if not is_source_db_available():
            logger.warning("MySQL 源数据库不可用，跳过同步")
            return {"status": "skipped", "reason": "source_db_unavailable"}

        logger.info(f"开始同步 {target_date} 的通话记录")

        # 获取源数据
        source_records = await self._fetch_source_records(target_date)
        if not source_records:
            logger.info(f"{target_date} 没有需要同步的记录")
            return {"status": "success", "synced": 0, "date": str(target_date)}

        logger.info(f"从源库读取到 {len(source_records)} 条记录")

        # 批量保存到画像库
        synced_count = 0
        async for session in get_portrait_db():
            for i in range(0, len(source_records), batch_size):
                batch = source_records[i : i + batch_size]
                try:
                    await self._upsert_enriched_records(session, batch)
                    await session.commit()  # 每批次提交
                    synced_count += len(batch)
                    logger.info(f"已同步 {synced_count}/{len(source_records)} 条记录")
                except Exception as e:
                    logger.error(f"批次同步失败: {e}")
                    await session.rollback()
                    raise

        logger.info(f"同步完成: {synced_count} 条记录")
        return {
            "status": "success",
            "synced": synced_count,
            "date": str(target_date),
        }

    async def _fetch_source_records(self, target_date: date) -> list[dict]:
        """
        从源数据库读取通话记录

        Args:
            target_date: 目标日期

        Returns:
            通话记录列表
        """
        # 根据日期确定表名
        table_name = get_call_record_table(target_date)

        # 构建查询 SQL - 注意: 使用 customer_id 而不是 user_id
        sql = text(f"""
            SELECT 
                cr.id,
                cr.callid,
                cr.task_id,
                cr.customer_id,
                DATE(cr.calldate) as call_date,
                cr.duration,
                cr.bill,
                cr.rounds,
                cr.level_name,
                cr.intention_results as intention_result,
                cr.hangup_disposition as hangup_by,
                CASE 
                    WHEN cr.bill > 0 THEN 'connected'
                    ELSE 'failed'
                END as call_status
            FROM {table_name} cr
            WHERE DATE(cr.calldate) = :target_date
        """)

        records = []
        async for session in get_source_db():
            try:
                result = await session.execute(sql, {"target_date": target_date})
                rows = result.fetchall()

                for row in rows:
                    # 转换 MySQL 字符串 UUID 到 Python UUID 对象
                    task_id = row.task_id
                    if isinstance(task_id, str):
                        task_id = uuid.UUID(task_id)

                    # 转换 intention_result 为字符串（MySQL 可能返回整数）
                    intention_result = row.intention_result
                    if intention_result is not None:
                        intention_result = str(intention_result) if intention_result != 0 else None

                    records.append(
                        {
                            "id": row.id,
                            "callid": row.callid,
                            "task_id": task_id,
                            "user_id": row.customer_id,  # 注意: user_id 字段存储 customer_id
                            "call_date": row.call_date,
                            "duration": row.duration or 0,
                            "bill": row.bill or 0,
                            "rounds": row.rounds or 0,
                            "level_name": row.level_name,
                            "intention_result": intention_result,
                            "hangup_by": row.hangup_by,
                            "call_status": row.call_status,
                        }
                    )
            except Exception as e:
                logger.error(f"读取源数据失败: {e}")
                # 检查表是否存在
                if "doesn't exist" in str(e):
                    logger.warning(f"表 {table_name} 不存在")
                raise

        return records

    async def _upsert_enriched_records(
        self,
        session: AsyncSession,
        records: list[dict],
    ) -> None:
        """
        批量插入或更新增强记录

        Args:
            session: 数据库会话
            records: 记录列表
        """
        if not records:
            return

        # 构建 upsert 语句 (PostgreSQL)
        stmt = insert(CallRecordEnriched).values(
            [
                {
                    "callid": r["callid"],
                    "task_id": r["task_id"],
                    "user_id": r["user_id"],
                    "call_date": r["call_date"],
                    "duration": r["duration"],
                    "bill": r["bill"],
                    "rounds": r["rounds"],
                    "level_name": r["level_name"],
                    "intention_result": r["intention_result"],
                    "hangup_by": r["hangup_by"],
                    "call_status": r["call_status"],
                }
                for r in records
            ]
        )

        # 冲突时更新
        stmt = stmt.on_conflict_do_update(
            index_elements=["callid"],
            set_={
                "duration": stmt.excluded.duration,
                "bill": stmt.excluded.bill,
                "rounds": stmt.excluded.rounds,
                "level_name": stmt.excluded.level_name,
                "intention_result": stmt.excluded.intention_result,
                "hangup_by": stmt.excluded.hangup_by,
                "call_status": stmt.excluded.call_status,
                "updated_at": datetime.now(),
            },
        )

        await session.execute(stmt)

    async def get_call_details(
        self,
        callid: str,
        task_create_date: date,
    ) -> list[dict]:
        """
        获取通话的 ASR 详情

        Args:
            callid: 通话ID
            task_create_date: 任务创建日期 (用于确定表名)

        Returns:
            对话详情列表
        """
        if not is_source_db_available():
            return []

        table_name = get_call_record_detail_table(task_create_date)

        sql = text(f"""
            SELECT 
                sequence,
                question,
                answer_text,
                speak_ms,
                created_at
            FROM {table_name}
            WHERE callid = :callid
              AND notify = 'asrmessage_notify'
            ORDER BY sequence ASC
        """)

        details = []
        async for session in get_source_db():
            try:
                result = await session.execute(sql, {"callid": callid})
                rows = result.fetchall()

                for row in rows:
                    details.append(
                        {
                            "sequence": row.sequence,
                            "question": row.question,  # 用户说话内容 (ASR)
                            "answer_text": row.answer_text,  # 机器人回复
                            "speak_ms": row.speak_ms,
                            "created_at": row.created_at,
                        }
                    )
            except Exception as e:
                logger.error(f"读取通话详情失败: {e}")
                if "doesn't exist" in str(e):
                    logger.warning(f"表 {table_name} 不存在")

        return details

    async def get_asr_text_for_analysis(
        self,
        callid: str,
        task_create_date: date,
    ) -> str:
        """
        获取通话的完整 ASR 文本用于 LLM 分析

        Args:
            callid: 通话ID
            task_create_date: 任务创建日期

        Returns:
            拼接的对话文本
        """
        details = await self.get_call_details(callid, task_create_date)

        if not details:
            return ""

        # 拼接对话文本
        dialogues = []
        for d in details:
            if d["question"]:
                dialogues.append(f"客户: {d['question']}")
            if d["answer_text"]:
                dialogues.append(f"机器人: {d['answer_text']}")

        return "\n".join(dialogues)

    async def get_pending_records_for_analysis(
        self,
        limit: int = 100,
    ) -> list[CallRecordEnriched]:
        """
        获取待 LLM 分析的记录

        Args:
            limit: 最大返回数量

        Returns:
            待分析的记录列表
        """
        async for session in get_portrait_db():
            result = await session.execute(
                text("""
                    SELECT * FROM call_record_enriched
                    WHERE llm_analyzed_at IS NULL
                      AND bill > 0
                    ORDER BY call_date DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            )
            rows = result.fetchall()
            return [CallRecordEnriched(**dict(row._mapping)) for row in rows]

        return []


# 全局服务实例
etl_service = ETLService()
