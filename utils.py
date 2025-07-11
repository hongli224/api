"""
工具函数模块
包含文件处理、验证、转换等通用功能
"""

import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional, Tuple
from fastapi import UploadFile, HTTPException
from loguru import logger
from config import settings


def generate_unique_filename(original_filename: str) -> str:
    """
    生成唯一的文件名
    
    Args:
        original_filename: 原始文件名
        
    Returns:
        唯一的文件名
    """
    # 获取文件扩展名
    file_extension = Path(original_filename).suffix
    
    # 生成UUID作为文件名前缀
    unique_id = str(uuid.uuid4())
    
    # 组合新的文件名
    return f"{unique_id}{file_extension}"


def validate_file_extension(filename: str) -> bool:
    """
    验证文件扩展名是否允许
    
    Args:
        filename: 文件名
        
    Returns:
        是否允许的文件类型
    """
    file_extension = Path(filename).suffix.lower()
    return file_extension in settings.ALLOWED_EXTENSIONS


def validate_file_size(file_size: int) -> bool:
    """
    验证文件大小是否在允许范围内
    
    Args:
        file_size: 文件大小（字节）
        
    Returns:
        文件大小是否合法
    """
    return file_size <= settings.MAX_FILE_SIZE


async def save_uploaded_file(content: bytes, filename: str) -> str:
    """
    保存上传的文件到本地存储
    
    Args:
        content: 文件内容（二进制）
        filename: 要保存的文件名
        
    Returns:
        保存的文件路径
        
    Raises:
        HTTPException: 文件保存失败时抛出异常
    """
    try:
        file_path = os.path.join(settings.UPLOAD_DIR, filename)
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        logger.info(f"文件已保存: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"保存文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail="文件保存失败")


async def validate_and_save_file(upload_file: UploadFile) -> Tuple[str, str, int]:
    """
    验证并保存上传的文件
    
    Args:
        upload_file: 上传的文件对象
        
    Returns:
        元组包含 (文件名, 文件路径, 文件大小)
        
    Raises:
        HTTPException: 验证或保存失败时抛出异常
    """
    # 检查文件名是否存在
    if not upload_file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    # 验证文件扩展名
    if not validate_file_extension(upload_file.filename):
        raise HTTPException(
            status_code=400, 
            detail=f"不支持的文件类型。允许的类型: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    # 读取文件内容以获取大小
    content = await upload_file.read()
    file_size = len(content)
    # 验证文件大小
    if not validate_file_size(file_size):
        max_size_mb = settings.MAX_FILE_SIZE // (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制。最大允许: {max_size_mb}MB"
        )
    # 生成唯一文件名
    unique_filename = generate_unique_filename(upload_file.filename)
    # 保存文件
    file_path = await save_uploaded_file(content, unique_filename)
    return unique_filename, file_path, file_size


def get_file_type(filename: str) -> str:
    """
    根据文件名获取文件类型
    
    Args:
        filename: 文件名
        
    Returns:
        文件类型（扩展名，不包含点）
    """
    return Path(filename).suffix.lower().lstrip('.')


async def convert_docx_to_pdf(docx_file_path: str, output_filename: str) -> str:
    """
    将DOCX文件转换为PDF
    
    Args:
        docx_file_path: DOCX文件路径
        output_filename: 输出PDF文件名
        
    Returns:
        生成的PDF文件路径
        
    Raises:
        HTTPException: 转换失败时抛出异常
    """
    try:
        from docx2pdf import convert
        
        # 构建输出PDF文件路径
        pdf_file_path = os.path.join(settings.OUTPUT_DIR, output_filename)
        
        # 执行转换
        convert(docx_file_path, pdf_file_path)
        
        logger.info(f"DOCX转PDF成功: {docx_file_path} -> {pdf_file_path}")
        return pdf_file_path
        
    except ImportError:
        logger.error("docx2pdf库未安装")
        raise HTTPException(status_code=500, detail="PDF转换功能不可用")
        
    except Exception as e:
        logger.error(f"DOCX转PDF失败: {str(e)}")
        raise HTTPException(status_code=500, detail="文件转换失败")


def get_file_size(file_path: str) -> int:
    """
    获取文件大小
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件大小（字节）
    """
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0


def file_exists(file_path: str) -> bool:
    """
    检查文件是否存在
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件是否存在
    """
    return os.path.exists(file_path)


def cleanup_file(file_path: str) -> bool:
    """
    清理文件
    
    Args:
        file_path: 要删除的文件路径
        
    Returns:
        删除是否成功
    """
    try:
        if file_exists(file_path):
            os.remove(file_path)
            logger.info(f"文件已删除: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        return False 