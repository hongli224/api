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
        pdf_prefix = original_file.original_filename.replace(".docx", "")
        pdf_filename = generate_unique_filename(pdf_prefix, original_file.original_filename.replace(".docx", ".pdf"))
        
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
        # 读取播客样例
        with open("播客样例1.txt", "r", encoding="utf-8") as f:
            podcast_example_1 = f.read()
        with open("播客样例2.txt", "r", encoding="utf-8") as f:
            podcast_example_2 = f.read()
        # 构造优化后的 prompt
        prompt = f"""
# 角色设定
你是一名专业科技播客编剧，擅长将新闻稿转化为流畅的双人对话。

# 核心要求
1. **对话格式**
   - 严格使用「女生:」「男生:」作为发言标识（输出时加粗，如：**女生:** **男生:**）。
   - 保持自然对话节奏，一方引导话题，另一方技术解读，男生担任技术解读多一些，但女生也可以技术解读，不要过于固定。

2. **开场白规范**
   - 女生开场必须包含：“哈喽大家好！欢迎收听我们的博客。今天是YYYY年M月D日，咱们来聊最近的AI动态，比如[新闻稿要点1]、[要点2]、[要点3]等新鲜事，咱们一个个来看！”

3. **内容转换规则**
   - 技术首现时，需写出缩写+全称（如“RecGPT→推荐大模型RecGPT”）。
   - 所有数据需口语化表达（如“38206”→“三万八千两百零六次”）。
   - 每项新闻内容都要植入合适的自然反应词（如“哇”“厉害”“有意思”“哦？”等）。
   - 禁止添加虚构信息。
   - 禁用被动语态，禁止出现主持人自我介绍名字和公司名字。

4. **对话内容要求**
   - 每条新闻稿要点都要有互动讨论，不要只单向陈述。
   - 对于专业名词或新产品，主持人可互相解释、举例或表达看法。
   - 语言口语化、自然、有情感，避免照搬新闻稿原文。
   - 适当穿插观点、解释、场景化描述，避免流水账。
   - 结尾有总结或引发听众思考。

5. **结构要求**
   - 以“女生: … 男生: …”轮流对话展开，内容分段清晰。
   - 参考下方【播客样例1】【播客样例2】的风格和结构。

【新闻稿】
{news_text}

【播客样例1】
{podcast_example_1}

【播客样例2】
{podcast_example_2}

请严格按照上述要求生成完整的播客对话文稿。
"""
        # 调用大模型生成播客稿
        podcast_text = call_deepseek(prompt)
        # 生成输出 docx 文件名
        base_name = os.path.splitext(file.filename)[0] if file.filename else "output"
        original_filename = file.filename or "input.docx"
        output_filename = generate_unique_filename(base_name + '_播客稿', original_filename)
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
        write_docx_text(podcast_text, output_path)
        # 读取生成的 docx 文件内容为二进制
        with open(output_path, "rb") as f:
            file_bytes = f.read()
        # 构造数据库存储信息
        file_data = {
            "filename": output_filename,
            "original_filename": file.filename,
            "file_path": output_path,
            "file_size": len(file_bytes),
            "file_type": "docx",
            "status": "generated"
        }
        # 保存到数据库（假设 database.create_file 支持二进制内容存储）
        file_model = await database.create_file(file_data)
        if not file_model:
            raise HTTPException(status_code=500, detail="保存播客文稿到数据库失败")
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
        return {
            "file": response,
            "podcast_text": podcast_text
        }
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