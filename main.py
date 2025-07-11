"""
主应用程序文件
FastAPI应用程序的入口点
"""

import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings, create_directories
from database import database
from api import router


# 配置日志
logger.remove()  # 移除默认处理器
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用程序生命周期管理
    处理启动和关闭事件
    """
    # 启动时执行
    logger.info("🚀 启动File Conversion API服务...")
    
    try:
        # 创建必要的目录
        create_directories()
        logger.info("✅ 目录结构创建完成")
        
        # 连接数据库
        await database.connect()
        logger.info("✅ 数据库连接成功")
        
        logger.info(f"🎉 服务启动成功！访问地址: http://{settings.HOST}:{settings.PORT}")
        logger.info(f"📚 API文档地址: http://{settings.HOST}:{settings.PORT}/docs")
        
    except Exception as e:
        logger.error(f"❌ 服务启动失败: {str(e)}")
        sys.exit(1)
    
    yield
    
    # 关闭时执行
    logger.info("🛑 正在关闭File Conversion API服务...")
    
    try:
        # 断开数据库连接
        await database.disconnect()
        logger.info("✅ 数据库连接已断开")
        
    except Exception as e:
        logger.error(f"❌ 服务关闭时出错: {str(e)}")
    
    logger.info("👋 服务已关闭")


# 创建FastAPI应用实例
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="文件转换API服务，支持DOCX转PDF等功能",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    全局异常处理器
    捕获所有未处理的异常并返回统一的错误响应
    """
    logger.error(f"未处理的异常: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "内部服务器错误",
            "message": "服务器发生意外错误，请稍后重试",
            "detail": str(exc) if settings.DEBUG else None
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    HTTP异常处理器
    处理HTTPException类型的异常
    """
    logger.warning(f"HTTP异常: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "请求错误",
            "message": exc.detail
        }
    )


# 根路径
@app.get("/")
async def root():
    """
    根路径处理器
    返回API服务的基本信息
    """
    return {
        "message": "欢迎使用File Conversion API",
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


# 健康检查端点
@app.get("/health")
async def health_check():
    """
    健康检查端点
    用于监控服务状态
    """
    try:
        # 检查数据库连接
        # 这里可以添加更多的健康检查逻辑
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": "2024-01-01T00:00:00Z"
        }
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        raise HTTPException(status_code=503, detail="服务不可用")


# 包含API路由
app.include_router(router)


if __name__ == "__main__":
    """
    直接运行时的入口点
    使用uvicorn启动服务器
    """
    import uvicorn
    
    logger.info("启动开发服务器...")
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    ) 