"""
数据库连接和模型定义
使用Motor进行异步MongoDB操作
"""

import motor.motor_asyncio
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from bson import ObjectId
from config import settings


class PyObjectId(ObjectId):
    """
    自定义ObjectId类，用于Pydantic模型
    支持MongoDB的ObjectId序列化和反序列化
    """
    
    @classmethod
    def __get_validators__(cls):
        """获取验证器"""
        yield cls.validate
    
    @classmethod
    def validate(cls, v, field=None):
        """验证ObjectId (兼容Pydantic v2)"""
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)
    
    @classmethod
    def _get_pydantic_json_schema__(cls, field_schema):
        """修改schema"""
        field_schema.update(type="string")


class FileModel(BaseModel):
    """
    文件数据模型
    定义文件在数据库中的结构
    """
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    filename: str = Field(..., description="文件名")
    original_filename: str = Field(..., description="原始文件名")
    file_path: str = Field(..., description="文件存储路径")
    file_size: int = Field(..., description="文件大小（字节）")
    file_type: str = Field(..., description="文件类型")
    status: str = Field(default="uploaded", description="文件状态")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    
    class Config:
        """Pydantic配置"""
        validate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "filename": "document.docx",
                "original_filename": "my_document.docx",
                "file_path": "uploads/document.docx",
                "file_size": 1024000,
                "file_type": "docx",
                "status": "uploaded"
            }
        }


class FileResponse(BaseModel):
    """
    文件响应模型
    用于API响应的文件信息
    """
    
    id: str = Field(..., description="文件ID")
    filename: str = Field(..., description="文件名")
    original_filename: str = Field(..., description="原始文件名")
    file_size: int = Field(..., description="文件大小")
    file_type: str = Field(..., description="文件类型")
    status: str = Field(..., description="文件状态")
    created_at: datetime = Field(..., description="创建时间")
    
    class Config:
        """Pydantic配置"""
        json_encoders = {datetime: lambda v: v.isoformat()}


class ConversionRequest(BaseModel):
    """
    转换请求模型
    用于PDF转换请求
    """
    
    file_id: str = Field(..., description="要转换的文件ID")
    
    class Config:
        """Pydantic配置"""
        json_schema_extra = {
            "example": {
                "file_id": "507f1f77bcf86cd799439011"
            }
        }


class WeeklyReportRequest(BaseModel):
    """
    周报生成请求模型
    用于接收前端传递的期望文件名和多个文件ID
    """
    
    file_ids: Optional[List[str]] = Field(None, description="要生成周报的文件ID列表")
    week_key: Optional[str] = Field(None, description="周次标识")
    expected_filename: Optional[str] = Field(None, description="期望的周报文件名")
    
    class Config:
        """Pydantic配置"""
        json_schema_extra = {
            "example": {
                "file_ids": ["file1", "file2", "file3"],
                "week_key": "2025-W01",
                "expected_filename": "2025年第01周周报.docx"
            }
        }


class ConversionResponse(BaseModel):
    """
    转换响应模型
    用于PDF转换响应
    """
    
    file_id: str = Field(..., description="原始文件ID")
    pdf_file_id: str = Field(..., description="生成的PDF文件ID")
    pdf_filename: str = Field(..., description="PDF文件名")
    pdf_file_path: str = Field(..., description="PDF文件路径")
    status: str = Field(..., description="转换状态")
    created_at: datetime = Field(..., description="转换时间")
    
    class Config:
        """Pydantic配置"""
        json_encoders = {datetime: lambda v: v.isoformat()}


class Database:
    """
    数据库连接管理类
    提供MongoDB连接和集合操作
    """
    
    def __init__(self):
        """初始化数据库连接"""
        self.client = None
        self.database = None
        self.files_collection = None
    
    async def connect(self):
        """
        连接到MongoDB数据库
        建立异步连接并获取集合引用
        """
        try:
            # 创建异步MongoDB客户端
            self.client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URL)
            
            # 获取数据库实例
            self.database = self.client[settings.DATABASE_NAME]
            
            # 获取文件集合
            self.files_collection = self.database.files
            
            # 创建索引
            await self.files_collection.create_index("filename")
            await self.files_collection.create_index("created_at")
            
            print(f"✅ 成功连接到MongoDB数据库: {settings.DATABASE_NAME}")
            
        except Exception as e:
            print(f"❌ 连接MongoDB失败: {str(e)}")
            raise
    
    async def disconnect(self):
        """
        断开MongoDB连接
        关闭客户端连接
        """
        if self.client:
            self.client.close()
            print("🔌 已断开MongoDB连接")
    
    async def get_file_by_id(self, file_id: str) -> Optional[FileModel]:
        """
        根据ID获取文件信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件模型对象或None
        """
        try:
            if self.files_collection is None:
                print("❌ 数据库集合未初始化")
                return None
            file_data = await self.files_collection.find_one({"_id": ObjectId(file_id)})
            if file_data:
                return FileModel(**file_data)
            return None
        except Exception as e:
            print(f"❌ 获取文件失败: {str(e)}")
            return None
    
    async def get_files(self, skip: int = 0, limit: int = 100) -> List[FileModel]:
        """
        获取文件列表
        
        Args:
            skip: 跳过的记录数
            limit: 返回的记录数限制
            
        Returns:
            文件模型对象列表
        """
        try:
            if self.files_collection is None:
                print("❌ 数据库集合未初始化")
                return []
            cursor = self.files_collection.find().skip(skip).limit(limit).sort("created_at", -1)
            files = []
            async for file_data in cursor:
                files.append(FileModel(**file_data))
            return files
        except Exception as e:
            print(f"❌ 获取文件列表失败: {str(e)}")
            return []
    
    async def create_file(self, file_data: dict) -> Optional[FileModel]:
        """
        创建新文件记录
        
        Args:
            file_data: 文件数据字典
            
        Returns:
            创建的文件模型对象或None
        """
        try:
            if self.files_collection is None:
                print("❌ 数据库集合未初始化")
                return None
            file_data["created_at"] = datetime.utcnow()
            file_data["updated_at"] = datetime.utcnow()
            
            result = await self.files_collection.insert_one(file_data)
            file_data["_id"] = result.inserted_id
            
            return FileModel(**file_data)
        except Exception as e:
            print(f"❌ 创建文件记录失败: {str(e)}")
            return None
    
    async def update_file_status(self, file_id: str, status: str) -> bool:
        """
        更新文件状态
        
        Args:
            file_id: 文件ID
            status: 新状态
            
        Returns:
            更新是否成功
        """
        try:
            if self.files_collection is None:
                print("❌ 数据库集合未初始化")
                return False
            result = await self.files_collection.update_one(
                {"_id": ObjectId(file_id)},
                {"$set": {"status": status, "updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ 更新文件状态失败: {str(e)}")
            return False

    async def delete_file(self, file_id: str) -> bool:
        """
        根据文件ID删除数据库中的文件记录
        Args:
            file_id: 文件ID（字符串）
        Returns:
            是否删除成功
        """
        try:
            if self.files_collection is None:
                print("❌ 数据库集合未初始化")
                return False
            result = await self.files_collection.delete_one({"_id": ObjectId(file_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"❌ 删除文件记录失败: {str(e)}")
            return False

    async def get_files_count(self) -> int:
        """
        获取文件总数
        Returns:
            文件总数（int）
        """
        try:
            if self.files_collection is None:
                print("❌ 数据库集合未初始化")
                return 0
            return await self.files_collection.count_documents({})
        except Exception as e:
            print(f"❌ 获取文件总数失败: {str(e)}")
            return 0

    async def get_files_by_filter(self, filter_dict):
        """
        按条件筛选文件列表
        """
        if self.files_collection is None:
            return []
        return await self.files_collection.find(filter_dict).to_list(length=1000)


# 创建全局数据库实例
database = Database() 