"""
API路由模块
定义所有的RESTful API端点
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse as FastAPIFileResponse
from typing import List
from loguru import logger
import os

from database import (
    database, 
    FileModel, 
    FileResponse, 
    ConversionRequest, 
    ConversionResponse
)
from utils import (
    validate_and_save_file, 
    get_file_type, 
    convert_docx_to_pdf, 
    generate_unique_filename,
    get_file_size,
    file_exists,
    read_docx_text,
    write_docx_text,
    call_deepseek
)
from config import settings

# 创建API路由器
router = APIRouter(prefix="/api", tags=["文件转换API"])


@router.post("/file_upload", response_model=FileResponse, status_code=201)
async def upload_file(file: UploadFile = File(...)):
    """
    文件上传接口
    
    功能：
    - 接收上传的文件
    - 验证文件类型和大小
    - 保存文件到本地存储
    - 将文件信息保存到数据库
    
    Args:
        file: 上传的文件对象
        
    Returns:
        文件信息响应对象
        
    Raises:
        HTTPException: 文件验证或保存失败时抛出异常
    """
    try:
        logger.info(f"开始处理文件上传: {file.filename}")
        
        # 验证并保存文件
        filename, file_path, file_size = await validate_and_save_file(file)
        
        # 获取文件类型
        file_type = get_file_type(filename)
        
        # 准备文件数据
        file_data = {
            "filename": filename,
            "original_filename": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "file_type": file_type,
            "status": "uploaded"
        }
        
        # 保存到数据库
        file_model = await database.create_file(file_data)
        
        if not file_model:
            raise HTTPException(status_code=500, detail="保存文件信息到数据库失败")
        
        # 构建响应
        response = FileResponse(
            id=str(file_model.id),
            filename=file_model.filename,
            original_filename=file_model.original_filename,
            file_size=file_model.file_size,
            file_type=file_model.file_type,
            status=file_model.status,
            created_at=file_model.created_at
        )
        
        logger.info(f"文件上传成功: {filename}, ID: {file_model.id}")
        return response
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail="文件上传失败")


@router.post("/convert_docx_to_pdf", response_model=ConversionResponse, status_code=201)
async def convert_docx_to_pdf_api(request: ConversionRequest):
    """
    DOCX转PDF接口
    
    功能：
    - 根据文件ID获取DOCX文件
    - 将DOCX文件转换为PDF
    - 保存PDF文件到输出目录
    - 将PDF文件信息保存到数据库
    
    Args:
        request: 转换请求对象，包含要转换的文件ID
        
    Returns:
        转换结果响应对象
        
    Raises:
        HTTPException: 文件不存在或转换失败时抛出异常
    """
    try:
        logger.info(f"开始处理DOCX转PDF请求: 文件ID {request.file_id}")
        
        # 获取原始文件信息
        original_file = await database.get_file_by_id(request.file_id)
        
        if not original_file:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 检查文件类型
        if original_file.file_type.lower() != "docx":
            raise HTTPException(status_code=400, detail="只能转换DOCX文件")
        
        # 检查文件是否存在
        if not file_exists(original_file.file_path):
            raise HTTPException(status_code=404, detail="文件在服务器上不存在")
        
        # 生成PDF文件名
        pdf_filename = generate_unique_filename(original_file.original_filename.replace(".docx", ".pdf"))
        
        # 执行转换
        pdf_file_path = await convert_docx_to_pdf(original_file.file_path, pdf_filename)
        
        # 获取PDF文件大小
        pdf_file_size = get_file_size(pdf_file_path)
        
        # 准备PDF文件数据
        pdf_file_data = {
            "filename": pdf_filename,
            "original_filename": original_file.original_filename.replace(".docx", ".pdf"),
            "file_path": pdf_file_path,
            "file_size": pdf_file_size,
            "file_type": "pdf",
            "status": "converted"
        }
        
        # 保存PDF文件信息到数据库
        pdf_file_model = await database.create_file(pdf_file_data)
        
        if not pdf_file_model:
            raise HTTPException(status_code=500, detail="保存PDF文件信息到数据库失败")
        
        # 更新原始文件状态
        await database.update_file_status(request.file_id, "converted")
        
        # 构建响应
        response = ConversionResponse(
            file_id=request.file_id,
            pdf_file_id=str(pdf_file_model.id),
            pdf_filename=pdf_file_model.filename,
            pdf_file_path=pdf_file_model.file_path,
            status="success",
            created_at=pdf_file_model.created_at
        )
        
        logger.info(f"DOCX转PDF成功: {original_file.filename} -> {pdf_filename}")
        return response
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"DOCX转PDF失败: {str(e)}")
        raise HTTPException(status_code=500, detail="文件转换失败")


@router.post("/files/convert_to_podcast")
async def convert_to_podcast(file: UploadFile = File(...)):
    """
    上传新闻稿 docx，自动转换为播客对话 docx，返回下载链接。
    """
    try:
        # 验证并保存上传文件
        filename, file_path, file_size = await validate_and_save_file(file)
        # 读取新闻稿内容
        news_text = read_docx_text(file_path)
        # few-shot 示例（可用播客样例1/2内容，实际可优化为读取本地样例文件）
        podcast_example = (
            "女生: 哈喽大家好欢迎收听，我们的播客。然后今天呢我们要一起来聊一聊，在二零二五年七月初啊科技领域都有哪些比较新鲜的。值得大家关注的一些动态，嗯比如说有哪些新的技术发布了。有哪些新的产品上线了或者说有哪些我们之前一直在关注的项目，有了一些新的进展。\n"
            "男生: 听起来就很令人期待，那我们就直接开始吧看看都有什么大霹雳。\n"
            "女生: 那咱们就开始吧嗯，咱们第一个要聊的呢是这个字节跳动刚刚发布的一个图像合成技术。叫 XVerse 啊，这个东西有什么亮点，未来可能会往哪些方向发展？\n"
            "男生: 这个技术我觉得还是非常炸的，就是它可以通过文字描述。生成非常高保真的图像，而且它的特别之处在于它可以，通过 DiT 调制。对多个主体进行独立的控制，然后它也支持 Gradio 的互动演示。就是你可以去调一些参数去优化它的生成效果。\n"
        )
        # 构造 prompt
        prompt = f"请将以下新闻稿内容，改写为两位主持人（女生、男生）互相对话的播客文稿，风格参考下方示例。\n【新闻稿内容】\n{news_text}\n【播客样例】\n{podcast_example}"
        # 调用 DeepSeek 大模型生成播客对话
        podcast_text = call_deepseek(prompt)
        # 生成输出 docx 文件名
        base_name = os.path.splitext(file.filename)[0] if file.filename else "output"
        output_filename = generate_unique_filename(base_name + '_podcast.docx')
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
        write_docx_text(podcast_text, output_path)
        # 返回下载链接（直接返回文件）
        return FileResponse(
            path=output_path,
            filename=output_filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"新闻稿转播客失败: {str(e)}")
        raise HTTPException(status_code=500, detail="新闻稿转播客失败")


@router.get("/files", response_model=List[FileResponse])
async def get_files(skip: int = 0, limit: int = 100):
    """
    获取文件列表接口
    
    功能：
    - 获取数据库中所有文件的列表
    - 支持分页查询
    
    Args:
        skip: 跳过的记录数（用于分页）
        limit: 返回的记录数限制
        
    Returns:
        文件信息列表
    """
    try:
        logger.info(f"获取文件列表: skip={skip}, limit={limit}")
        
        files = await database.get_files(skip=skip, limit=limit)
        
        # 转换为响应格式
        response_files = []
        for file_model in files:
            response_file = FileResponse(
                id=str(file_model.id),
                filename=file_model.filename,
                original_filename=file_model.original_filename,
                file_size=file_model.file_size,
                file_type=file_model.file_type,
                status=file_model.status,
                created_at=file_model.created_at
            )
            response_files.append(response_file)
        
        logger.info(f"成功获取 {len(response_files)} 个文件")
        return response_files
        
    except Exception as e:
        logger.error(f"获取文件列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取文件列表失败")


@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(file_id: str):
    """
    获取单个文件信息接口
    
    功能：
    - 根据文件ID获取特定文件的详细信息
    
    Args:
        file_id: 文件ID
        
    Returns:
        文件信息响应对象
        
    Raises:
        HTTPException: 文件不存在时抛出异常
    """
    try:
        logger.info(f"获取文件信息: {file_id}")
        
        file_model = await database.get_file_by_id(file_id)
        
        if not file_model:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 构建响应
        response = FileResponse(
            id=str(file_model.id),
            filename=file_model.filename,
            original_filename=file_model.original_filename,
            file_size=file_model.file_size,
            file_type=file_model.file_type,
            status=file_model.status,
            created_at=file_model.created_at
        )
        
        logger.info(f"成功获取文件信息: {file_id}")
        return response
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"获取文件信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取文件信息失败")


@router.get("/files/download/{file_id}")
async def download_file(file_id: str):
    """
    文件下载接口
    根据文件ID下载已上传或已转换的文件
    """
    file = await database.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    # 检查文件是否存在于磁盘
    import os
    if not os.path.exists(file.file_path):
        raise HTTPException(status_code=404, detail="文件在服务器上不存在")
    return FastAPIFileResponse(
        path=file.file_path,
        filename=file.original_filename,
        media_type="application/octet-stream"
    )


@router.delete("/files/{file_id}")
async def delete_file(file_id: str):
    """
    删除文件接口
    
    功能：
    - 根据文件ID删除文件
    - 从数据库中删除文件记录
    - 删除本地文件
    
    Args:
        file_id: 文件ID
        
    Returns:
        删除结果
        
    Raises:
        HTTPException: 文件不存在或删除失败时抛出异常
    """
    try:
        logger.info(f"删除文件: {file_id}")
        
        # 获取文件信息
        file_model = await database.get_file_by_id(file_id)
        
        if not file_model:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 删除本地文件
        from utils import cleanup_file
        cleanup_file(file_model.file_path)

        # 从数据库中删除记录
        deleted = await database.delete_file(file_id)
        if not deleted:
            raise HTTPException(status_code=500, detail="数据库记录删除失败")
        
        logger.info(f"文件删除成功: {file_id}")
        return {"message": "文件删除成功", "file_id": file_id}
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"删除文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除文件失败") 