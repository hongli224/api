"""
配置文件
包含数据库连接、应用程序设置等配置信息
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    应用程序设置类
    使用Pydantic进行配置管理和验证
    """
    
    # 数据库配置
    MONGODB_URL: str = "mongodb://root:m4t6n2mf@test-db-mongodb.ns-0urjgbs0.svc:27017"
    DATABASE_NAME: str = "file_conversion_db"
    
    # 应用程序配置
    APP_NAME: str = "File Conversion API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # 文件存储配置
    UPLOAD_DIR: str = "uploads"
    OUTPUT_DIR: str = "outputs"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: set = {".docx", ".pdf"}
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 5000
    
    class Config:
        """Pydantic配置类"""
        env_file = ".env"
        case_sensitive = True


# 创建全局设置实例
settings = Settings()


def create_directories():
    """
    创建必要的目录结构
    确保上传和输出目录存在
    """
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True) 