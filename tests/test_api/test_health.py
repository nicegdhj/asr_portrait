"""
健康检查接口测试
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """测试健康检查接口"""
    response = await client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """测试根路径"""
    response = await client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert "service" in data
    assert "version" in data

