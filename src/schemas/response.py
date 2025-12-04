"""
通用响应模式
"""

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """
    统一 API 响应格式
    """
    
    code: int = Field(default=0, description="状态码，0 表示成功")
    message: str = Field(default="success", description="响应消息")
    data: Optional[T] = Field(default=None, description="响应数据")
    
    @classmethod
    def success(cls, data: T = None, message: str = "success") -> "ApiResponse[T]":
        """成功响应"""
        return cls(code=0, message=message, data=data)
    
    @classmethod
    def error(cls, message: str, code: int = -1) -> "ApiResponse":
        """错误响应"""
        return cls(code=code, message=message, data=None)


class PaginatedResponse(BaseModel, Generic[T]):
    """
    分页响应格式
    """
    
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="success", description="响应消息")
    data: List[T] = Field(default_factory=list, description="数据列表")
    total: int = Field(default=0, description="总记录数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页数量")
    total_pages: int = Field(default=0, description="总页数")
    
    @classmethod
    def create(
        cls,
        data: List[T],
        total: int,
        page: int = 1,
        page_size: int = 20,
    ) -> "PaginatedResponse[T]":
        """创建分页响应"""
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            data=data,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

