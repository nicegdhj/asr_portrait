"""
ETL 服务 - 数据抽取与转换

从 MySQL 源数据库同步通话记录到 PostgreSQL 画像存储
包含基于规则引擎的满意度/情绪/风险分析
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
from src.services.rule_engine_service import rule_engine
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

        # 分析已同步的记录（获取 ASR 并进行规则分析）
        if synced_count > 0:
            analyzed_count = await self.analyze_call_records(target_date)
            logger.info(f"已分析 {analyzed_count} 条记录")

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
        # 同时获取 callee (被叫手机号)
        sql = text(f"""
            SELECT 
                cr.id,
                cr.callid,
                cr.task_id,
                cr.customer_id,
                cr.callee,
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
                            "phone": row.callee,  # 被叫手机号
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
                    "phone": r["phone"],
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
                "phone": stmt.excluded.phone,
                "updated_at": datetime.now(),
            },
        )

        await session.execute(stmt)

    async def analyze_call_records(
        self,
        target_date: date,
        batch_size: int = 100,
    ) -> int:
        """
        分析指定日期的通话记录

        获取 ASR 详情并进行规则引擎分析

        Args:
            target_date: 目标日期
            batch_size: 批量处理大小

        Returns:
            分析的记录数
        """
        if not is_source_db_available():
            return 0

        # 获取需要分析的记录（已接通但未分析的）
        records_to_analyze = await self._get_records_for_analysis(target_date)

        if not records_to_analyze:
            return 0

        logger.info(f"需要分析 {len(records_to_analyze)} 条通话记录")

        # 批量获取 ASR 详情
        asr_data = await self._batch_fetch_asr_details(
            [(r["callid"], target_date) for r in records_to_analyze],
            target_date,
        )

        # 分析并批量更新
        analyzed_count = 0
        updates = []

        for record in records_to_analyze:
            callid = record["callid"]

            # 获取该通话的 ASR 数据
            call_asr = asr_data.get(callid, {"user_text": "", "asr_labels": []})

            # 调用规则引擎分析
            result = rule_engine.analyze_call(
                user_text=call_asr.get("user_text", ""),
                asr_labels=call_asr.get("asr_labels", []),
                duration=record.get("bill", 0) // 1000,  # 毫秒转秒
                rounds=record.get("rounds", 0),
            )

            updates.append(
                {
                    "callid": callid,
                    "satisfaction": result.satisfaction,
                    "satisfaction_source": result.satisfaction_source,
                    "emotion": result.emotion,
                    "complaint_risk": result.complaint_risk,
                    "churn_risk": result.churn_risk,
                    "willingness": result.willingness,
                    "risk_level": result.risk_level,
                }
            )
            analyzed_count += 1

        # 批量更新
        if updates:
            await self._batch_update_analysis_results(updates)

        return analyzed_count

    async def _get_records_for_analysis(self, target_date: date) -> list[dict]:
        """获取需要分析的记录"""
        async for session in get_portrait_db():
            result = await session.execute(
                text("""
                    SELECT callid, bill, rounds
                    FROM call_record_enriched
                    WHERE call_date = :target_date
                      AND bill > 0
                      AND (sentiment IS NULL OR satisfaction IS NULL)
                """),
                {"target_date": target_date},
            )
            return [dict(row._mapping) for row in result.fetchall()]
        return []

    async def _batch_fetch_asr_details(
        self,
        call_ids: list[tuple[str, date]],
        target_date: date,
    ) -> dict[str, dict]:
        """
        批量获取 ASR 详情

        Returns:
            {callid: {'user_text': str, 'asr_labels': list}}
        """
        if not call_ids:
            return {}

        # 获取表名
        table_name = get_call_record_detail_table(target_date)

        # 提取所有 callid
        callid_list = [c[0] for c in call_ids]

        # 批量查询 ASR 详情
        # 使用 IN 查询一次获取所有数据
        placeholders = ", ".join([f":callid_{i}" for i in range(len(callid_list))])
        sql = text(f"""
            SELECT 
                callid,
                sequence,
                question,
                answer_text
            FROM {table_name}
            WHERE callid IN ({placeholders})
              AND notify = 'asrmessage_notify'
            ORDER BY callid, sequence ASC
        """)

        params = {f"callid_{i}": callid for i, callid in enumerate(callid_list)}

        result_map = {}
        async for session in get_source_db():
            try:
                result = await session.execute(sql, params)
                rows = result.fetchall()

                # 按 callid 分组
                current_callid = None
                current_user_text = []
                current_labels = []

                for row in rows:
                    if row.callid != current_callid:
                        # 保存上一个 callid 的数据
                        if current_callid:
                            result_map[current_callid] = {
                                "user_text": " ".join(current_user_text),
                                "asr_labels": current_labels,
                            }
                        # 开始新的 callid
                        current_callid = row.callid
                        current_user_text = []
                        current_labels = []

                    # 收集用户说话内容
                    if row.question:
                        current_user_text.append(row.question)

                    # 收集 ASR 标签（answer_text 可能包含标签如 Q7-满分）
                    if row.answer_text and ("Q" in row.answer_text or "满" in row.answer_text):
                        current_labels.append(row.answer_text)

                # 保存最后一个 callid 的数据
                if current_callid:
                    result_map[current_callid] = {
                        "user_text": " ".join(current_user_text),
                        "asr_labels": current_labels,
                    }

            except Exception as e:
                logger.error(f"批量获取 ASR 详情失败: {e}")

        return result_map

    async def _batch_update_analysis_results(
        self,
        updates: list[dict],
    ) -> None:
        """批量更新分析结果到数据库（优化版：使用 VALUES 批量更新）"""
        if not updates:
            return

        async for session in get_portrait_db():
            analyzed_at = datetime.now()

            # 批量执行更新（分批处理避免参数过多）
            batch_size = 100
            for i in range(0, len(updates), batch_size):
                batch = updates[i : i + batch_size]

                # 构建 VALUES 子句和参数
                values_parts = []
                params = {"analyzed_at": analyzed_at}

                for idx, update in enumerate(batch):
                    values_parts.append(
                        f"(:callid_{idx}, :satisfaction_{idx}, :satisfaction_source_{idx}, "
                        f":emotion_{idx}, :complaint_risk_{idx}, :churn_risk_{idx}, "
                        f":willingness_{idx}, :risk_level_{idx})"
                    )
                    params[f"callid_{idx}"] = update["callid"]
                    params[f"satisfaction_{idx}"] = update["satisfaction"]
                    params[f"satisfaction_source_{idx}"] = update["satisfaction_source"]
                    params[f"emotion_{idx}"] = update["emotion"]
                    params[f"complaint_risk_{idx}"] = update["complaint_risk"]
                    params[f"churn_risk_{idx}"] = update["churn_risk"]
                    params[f"willingness_{idx}"] = update["willingness"]
                    params[f"risk_level_{idx}"] = update["risk_level"]

                # 使用 PostgreSQL VALUES + UPDATE FROM 语法批量更新
                values_sql = ", ".join(values_parts)
                await session.execute(
                    text(f"""
                        UPDATE call_record_enriched AS c
                        SET 
                            satisfaction = v.satisfaction,
                            satisfaction_source = v.satisfaction_source,
                            sentiment = v.emotion,
                            complaint_risk = v.complaint_risk,
                            churn_risk = v.churn_risk,
                            willingness = v.willingness,
                            risk_level = v.risk_level,
                            llm_analyzed_at = :analyzed_at
                        FROM (VALUES {values_sql}) AS v(
                            callid, satisfaction, satisfaction_source, 
                            emotion, complaint_risk, churn_risk, 
                            willingness, risk_level
                        )
                        WHERE c.callid = v.callid
                    """),
                    params,
                )

                # 每批次提交一次
                await session.commit()
                logger.info(f"已更新分析结果: {min(i + batch_size, len(updates))}/{len(updates)}")

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

    async def sync_task_names(self) -> dict[str, Any]:
        """
        同步任务名称到画像系统

        从源数据库获取任务名称，更新到 TaskPortraitSummary 表

        Returns:
            同步结果统计
        """
        if not is_source_db_available():
            logger.warning("MySQL 源数据库不可用，跳过任务名称同步")
            return {"status": "skipped", "reason": "source_db_unavailable"}

        logger.info("开始同步任务名称")

        # 从源数据库获取任务信息
        task_map = await self._fetch_task_names()
        if not task_map:
            logger.info("没有需要同步的任务")
            return {"status": "success", "synced": 0}

        logger.info(f"从源库读取到 {len(task_map)} 个任务")

        # 更新 TaskPortraitSummary 表中的任务名称
        updated_count = 0
        async for session in get_portrait_db():
            try:
                from src.models import TaskPortraitSummary

                for task_id, task_name in task_map.items():
                    # 更新所有该任务的汇总记录
                    stmt = text("""
                        UPDATE task_portrait_summary
                        SET task_name = :task_name
                        WHERE task_id = :task_id AND (task_name IS NULL OR task_name != :task_name)
                    """)
                    result = await session.execute(stmt, {"task_id": task_id, "task_name": task_name})
                    updated_count += result.rowcount

                await session.commit()
            except Exception as e:
                logger.error(f"更新任务名称失败: {e}")
                await session.rollback()
                raise

        logger.info(f"任务名称同步完成: 更新 {updated_count} 条记录")
        return {
            "status": "success",
            "tasks": len(task_map),
            "updated": updated_count,
        }

    async def _fetch_task_names(self) -> dict[str, str]:
        """
        从源数据库获取任务名称映射

        Returns:
            {task_id: task_name} 映射
        """
        sql = text("""
            SELECT uuid, name
            FROM autodialer_task
            WHERE name IS NOT NULL AND name != ''
        """)

        task_map = {}
        async for session in get_source_db():
            try:
                result = await session.execute(sql)
                rows = result.fetchall()

                for row in rows:
                    task_map[row.uuid] = row.name
            except Exception as e:
                logger.error(f"读取任务名称失败: {e}")
                raise

        return task_map

    async def get_task_name(self, task_id: str) -> str | None:
        """
        获取单个任务的名称

        Args:
            task_id: 任务UUID

        Returns:
            任务名称，未找到返回 None
        """
        if not is_source_db_available():
            return None

        sql = text("""
            SELECT name FROM autodialer_task WHERE uuid = :task_id
        """)

        async for session in get_source_db():
            try:
                result = await session.execute(sql, {"task_id": task_id})
                row = result.fetchone()
                return row.name if row else None
            except Exception as e:
                logger.error(f"获取任务名称失败: {e}")
                return None

        return None


# 全局服务实例
etl_service = ETLService()
