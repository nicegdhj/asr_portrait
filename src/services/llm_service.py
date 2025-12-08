"""
LLM 服务 - 情感分析与风险识别

支持双环境：
- 开发环境: 通义千问 API (DashScope)
- 生产环境: 自定义网关 API
"""

import asyncio
import json
from datetime import datetime
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings


# 情感分析 Prompt
SENTIMENT_PROMPT = """分析以下外呼通话内容，评估客户的情绪和风险。

通话内容:
{dialogue}

请严格按照以下 JSON 格式返回分析结果，不要返回其他内容:
{{
    "sentiment": "positive/neutral/negative",
    "sentiment_score": 0.0-1.0,
    "complaint_risk": "low/medium/high",
    "churn_risk": "low/medium/high",
    "reason": "简要分析原因(50字以内)"
}}

分析要点:
- sentiment: 客户整体情绪倾向
- sentiment_score: 情绪得分，0=极度负面，1=极度正面
- complaint_risk: 投诉风险，检测"投诉"、"举报"、"工信部"等关键词
- churn_risk: 流失风险，检测"不用了"、"取消"、"换运营商"等关键词
"""


class LLMService:
    """
    LLM 服务类

    统一封装 LLM API 调用，支持开发/生产双环境
    """

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=settings.llm_timeout)
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrent)

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()

    @property
    def is_gateway_mode(self) -> bool:
        """是否使用网关模式"""
        return settings.llm_gateway_mode

    async def analyze_sentiment(self, dialogue: str) -> dict[str, Any]:
        """
        分析对话情感和风险

        Args:
            dialogue: 对话文本

        Returns:
            分析结果字典
        """
        if not dialogue or not dialogue.strip():
            return self._default_result("empty_dialogue")

        prompt = SENTIMENT_PROMPT.format(dialogue=dialogue)

        try:
            response = await self._call_llm(prompt)
            result = self._parse_response(response)
            return result
        except Exception as e:
            logger.error(f"LLM 分析失败: {e}")
            return self._default_result(f"error: {str(e)}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM API

        根据配置自动选择开发环境 API 或生产网关

        Args:
            prompt: 提示词

        Returns:
            LLM 响应文本
        """
        async with self._semaphore:
            if self.is_gateway_mode:
                return await self._call_gateway_api(prompt)
            else:
                return await self._call_qwen_api(prompt)

    async def _call_qwen_api(self, prompt: str) -> str:
        """
        调用通义千问 API (开发环境)

        使用 OpenAI 兼容格式
        """
        url = f"{settings.llm_api_base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        }

        payload = {
            "model": settings.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500,
        }

        logger.debug(f"调用通义千问 API: {settings.llm_model}")

        response = await self.client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return content

    async def _call_gateway_api(self, prompt: str) -> str:
        """
        调用网关 API (生产环境)

        使用自定义网关认证
        """
        url = settings.llm_api_base_url

        headers = {
            "Content-Type": "application/json",
            "Authorization-Gateway": settings.llm_gateway_auth_header,
        }

        payload = {
            "model": settings.llm_model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
        }

        logger.debug(f"调用网关 API: {settings.llm_model}")

        response = await self.client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return content

    def _parse_response(self, response: str) -> dict[str, Any]:
        """
        解析 LLM 响应

        Args:
            response: LLM 原始响应

        Returns:
            解析后的结果字典
        """
        try:
            # 尝试提取 JSON
            response = response.strip()

            # 处理 markdown 代码块
            if response.startswith("```"):
                lines = response.split("\n")
                response = "\n".join(lines[1:-1])

            result = json.loads(response)

            # 验证必需字段
            required = ["sentiment", "sentiment_score", "complaint_risk", "churn_risk"]
            for field in required:
                if field not in result:
                    result[field] = self._default_value(field)

            # 规范化值
            result["sentiment"] = self._normalize_sentiment(result["sentiment"])
            result["sentiment_score"] = max(0.0, min(1.0, float(result["sentiment_score"])))
            result["complaint_risk"] = self._normalize_risk(result["complaint_risk"])
            result["churn_risk"] = self._normalize_risk(result["churn_risk"])
            result["raw_response"] = response

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"解析 LLM 响应失败: {e}, response={response[:200]}")
            return self._default_result(f"parse_error: {response[:100]}")

    def _normalize_sentiment(self, value: str) -> str:
        """规范化情感值"""
        value = str(value).lower().strip()
        if value in ["positive", "积极", "正面"]:
            return "positive"
        elif value in ["negative", "消极", "负面"]:
            return "negative"
        else:
            return "neutral"

    def _normalize_risk(self, value: str) -> str:
        """规范化风险值"""
        value = str(value).lower().strip()
        if value in ["high", "高"]:
            return "high"
        elif value in ["medium", "中"]:
            return "medium"
        else:
            return "low"

    def _default_value(self, field: str) -> Any:
        """返回字段默认值"""
        defaults = {
            "sentiment": "neutral",
            "sentiment_score": 0.5,
            "complaint_risk": "low",
            "churn_risk": "low",
        }
        return defaults.get(field)

    def _default_result(self, reason: str) -> dict[str, Any]:
        """返回默认结果"""
        return {
            "sentiment": "neutral",
            "sentiment_score": 0.5,
            "complaint_risk": "low",
            "churn_risk": "low",
            "reason": reason,
            "raw_response": None,
        }

    async def analyze_pending_batch(self, limit: int = 100) -> dict[str, Any]:
        """
        批量分析待处理的通话记录

        Args:
            limit: 最大处理数量

        Returns:
            处理结果统计
        """
        from src.services.etl_service import etl_service
        from src.core.database import get_portrait_db
        from sqlalchemy import text

        logger.info(f"开始批量 LLM 分析 (limit={limit})")

        # 获取待分析记录
        records = await etl_service.get_pending_records_for_analysis(limit)

        if not records:
            logger.info("没有待分析的记录")
            return {"status": "success", "analyzed": 0, "skipped": 0}

        logger.info(f"待分析记录数: {len(records)}")

        analyzed = 0
        skipped = 0
        errors = 0

        for record in records:
            try:
                # 获取 ASR 对话文本
                dialogue = await etl_service.get_asr_text_for_analysis(
                    record.callid,
                    record.call_date,
                )

                if not dialogue:
                    skipped += 1
                    continue

                # 调用 LLM 分析
                result = await self.analyze_sentiment(dialogue)

                # 更新记录
                async for session in get_portrait_db():
                    await session.execute(
                        text("""
                            UPDATE call_record_enriched
                            SET sentiment = :sentiment,
                                sentiment_score = :sentiment_score,
                                complaint_risk = :complaint_risk,
                                churn_risk = :churn_risk,
                                llm_analyzed_at = :analyzed_at,
                                llm_raw_response = :raw_response,
                                updated_at = :updated_at
                            WHERE id = :id
                        """),
                        {
                            "id": record.id,
                            "sentiment": result["sentiment"],
                            "sentiment_score": result["sentiment_score"],
                            "complaint_risk": result["complaint_risk"],
                            "churn_risk": result["churn_risk"],
                            "analyzed_at": datetime.now(),
                            "raw_response": result.get("raw_response", "")[:2000],
                            "updated_at": datetime.now(),
                        },
                    )
                    await session.commit()

                analyzed += 1

                # 批量处理间隔，避免 API 限流
                if analyzed % 10 == 0:
                    logger.info(f"已分析 {analyzed}/{len(records)} 条")
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"分析记录 {record.callid} 失败: {e}")
                errors += 1

        logger.info(f"LLM 分析完成: analyzed={analyzed}, skipped={skipped}, errors={errors}")

        return {
            "status": "success",
            "analyzed": analyzed,
            "skipped": skipped,
            "errors": errors,
        }


# 全局服务实例
llm_service = LLMService()
