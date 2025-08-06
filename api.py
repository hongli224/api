"""
API路由模块
定义所有的RESTful API端点
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Body
from fastapi.responses import JSONResponse, FileResponse as FastAPIFileResponse
from typing import List
from loguru import logger
import os
import uuid
from datetime import datetime

from database import (
    database, 
    FileModel, 
    FileResponse, 
    ConversionRequest, 
    ConversionResponse,
    WeeklyReportRequest
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
    call_deepseek,
    text_to_speech_edge_tts,
    split_dialogue,
    concat_audios,
    clean_markdown,
    split_daily_report_by_date,
    normalize_date,
    summarize_content_with_deepseek,
    generate_wordcloud,
    generate_timeline_with_llm
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
        # await database.update_file_status(request.file_id, "converted")
        
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
   - 对于专业名词或新产品，主持人可互相解释、举例或表达看法，但是禁止相互打断。
   - 语言口语化、自然、有情感，避免照搬新闻稿原文。
   - 适当穿插观点、定性解释、场景化描述，避免流水账，但是对话内容必须严格遵守新闻稿原文，不要虚构任何自己的体验和观点，尤其禁止虚构新闻稿原文中没有提到的内容。
   - 结尾有总结，例如一方说：对，今天聊了这么多，无论是……如何……，还是……，其实都让我们看到了……生活带来的深刻变化。  另一方说OK了以上就是这期播客的全部内容啦，然后咱们下期再见拜拜！当然总结内容要基于新闻稿原文，严禁虚构。
   - 接茬要自然，例如使用：
        “听起来就很令人期待，那”
        “这个应用它就是在”
        “听起来真的很厉害啊，那”
        “这个技术我觉得还是非常炸的”
        “听起来确实很智能，那”
        “没错没错比如说”
        “听起来确实很有特点，那”
        “就是它特别适合于，比如说”
        “就是非常亮眼”
        “有哪些其他的值得关注的，科技方面的消息呢？”
        “嗯还有很多啊比如说”
        “哇哦那这个确实是非常火热啊！”
        “嗯当然比如说还有这个”
        “哦，这么看的话确实数据很亮眼啊”
        “这个应用其实蛮特别的”
   - 不必完全按照我给的例句生成文稿，可以在例句的基础上进行适当的发挥，但是不要出现重复的接茬，以及要符合新闻稿原文，禁止虚构。

5. **结构要求**
   - 以“女生: … 男生: …”轮流对话展开，内容分段清晰。
   - 参考下方【播客样例1】【播客样例2】的风格和结构。

6.**内容锚定规则**
   - 数据锁定：仅使用新闻稿明确数据（缺失数据时用“表现亮眼”等中性表述）
   - 零体验虚构：禁用“用户反馈”/“我用过”等主观表述
   - 技术描述：直接复制新闻稿术语，不要进行任何技术性解释。

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


@router.post("/files/convert_to_audio")
async def convert_docx_to_audio(file_id: str):
    """
    多角色分段配音：解析播客文稿，按“**女生：**”“**男生：**”分段，分别用不同 voice 合成音频，拼接为完整 mp3，写入数据库并返回。
    """
    # 1. 获取文件信息
    file_model = await database.get_file_by_id(file_id)
    if not file_model:
        raise HTTPException(status_code=404, detail="文件不存在")
    if file_model.file_type.lower() != "docx":
        raise HTTPException(status_code=400, detail="仅支持 docx 文件转音频")
    if not os.path.exists(file_model.file_path):
        raise HTTPException(status_code=404, detail="文件在服务器上不存在")
    # 2. 提取文本
    text = read_docx_text(file_model.file_path)
    if not text.strip():
        raise HTTPException(status_code=400, detail="docx 内容为空")
    # 3. 分段解析
    segments = split_dialogue(text)
    if not segments:
        raise HTTPException(status_code=400, detail="未检测到有效的对话分段")
    ROLE_VOICE = {
        "女生": "zh-CN-XiaoyiNeural",
        "男生": "zh-CN-YunyangNeural"
    }
    temp_audio_paths = []
    try:
        for idx, (role, content) in enumerate(segments):
            voice = ROLE_VOICE.get(role, "zh-CN-XiaoxiaoNeural")
            clean_content = clean_markdown(content)
            temp_path = os.path.join("audio_files", f"temp_{file_id}_{idx}.mp3")
            await text_to_speech_edge_tts(clean_content, temp_path, voice=voice)
            temp_audio_paths.append(temp_path)
        # 4. 拼接音频
        audio_filename = f"{os.path.splitext(file_model.filename)[0]}_{uuid.uuid4().hex}.mp3"
        audio_path = os.path.join("audio_files", audio_filename)
        concat_audios(temp_audio_paths, audio_path)
    finally:
        # 清理临时分段音频
        for p in temp_audio_paths:
            if os.path.exists(p):
                os.remove(p)
    # 5. 写入数据库
    audio_file_size = os.path.getsize(audio_path)
    audio_file_data = {
        "filename": audio_filename,
        "original_filename": file_model.original_filename.replace('.docx', '.mp3'),
        "file_path": audio_path,
        "file_size": audio_file_size,
        "file_type": "mp3",
        "status": "converted",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "source_file_id": str(file_model.id)
    }
    audio_file_model = await database.create_file(audio_file_data)
    if not audio_file_model:
        raise HTTPException(status_code=500, detail="音频文件信息写入数据库失败")
    # 6. 返回音频文件完整信息
    return {
        "audio_file": {
            "id": str(audio_file_model.id),
            "filename": audio_file_model.filename,
            "original_filename": audio_file_model.original_filename,
            "file_size": audio_file_model.file_size,
            "file_type": audio_file_model.file_type,
            "status": audio_file_model.status,
            "created_at": audio_file_model.created_at,
            "url": f"/api/files/audio_download/{audio_file_model.filename}"
        }
    }

@router.get("/files/audio_download/{filename}")
def download_audio_file(filename: str):
    """
    音频文件下载接口
    """
    file_path = os.path.join("audio_files", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")
    return FastAPIFileResponse(file_path, media_type="audio/mpeg", filename=filename)


@router.post("/daily_report/analyze")
async def analyze_daily_report(file: UploadFile = File(...)):
    """
    上传AI日报，自动按日期生成timeline摘要和词云图片
    """
    # 1. 保存并读取文本
    filename, file_path, file_size = await validate_and_save_file(file)
    if filename.endswith('.docx'):
        text = read_docx_text(file_path)
    elif filename.endswith('.pdf'):
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
    else:
        raise HTTPException(400, "仅支持docx/pdf")
    # 2. 按日期分割
    date_contents = split_daily_report_by_date(text)
    timeline = []
    for date, content in date_contents:
        summary = summarize_content_with_deepseek(date, content)
        timeline.append({"date": date, "summary": summary})
    timeline.sort(key=lambda x: x["date"])
    # 3. 生成词云
    import os
    from config import settings
    cloud_map_path = os.path.join(settings.OUTPUT_DIR, f"{filename}_cloudmap.png")
    generate_wordcloud(text, cloud_map_path)
    # 4. 返回
    return {
        "timeline": timeline,
        "cloud_map_url": f"/api/files/cloud_map/{os.path.basename(cloud_map_path)}"
    }

@router.get("/daily_report/selectable")
async def get_selectable_daily_reports():
    """
    获取所有可用于日报分析的docx文件（status=uploaded）
    """
    files = await database.get_files_by_filter({"status": "uploaded", "file_type": "docx"})
    return [
        {
            "id": str(f.get('id') or f.get('_id', '')),
            "filename": f.get('filename', ''),
            "original_filename": f.get('original_filename', ''),
            "created_at": f.get('created_at', '')
        }
        for f in files if f
    ]

@router.post("/daily_report/timeline_batch")
async def analyze_daily_report_timeline_batch(file_ids: List[str] = Body(...)):
    files = [await database.get_file_by_id(fid) for fid in file_ids]
    valid_files = []
    all_text = ""
    import os
    for f in files:
        if not f or getattr(f, 'file_type', '').lower() != 'docx':
            continue
        if not os.path.exists(f.file_path):
            await database.delete_file(str(f.id))
            continue
        valid_files.append(f)
        all_text += read_docx_text(f.file_path) + "\n"
    if not valid_files:
        raise HTTPException(400, "所有选择的文件都不存在")
    # 直接用大模型生成timeline
    timeline = generate_timeline_with_llm(all_text)
    return {"timeline": timeline}

@router.post("/daily_report/cloudmap_batch")
async def analyze_daily_report_cloudmap_batch(file_ids: List[str] = Body(...)):
    """
    批量分析多个日报docx，合并内容后仅生成词云图片
    """
    files = [await database.get_file_by_id(fid) for fid in file_ids]
    for f, fid in zip(files, file_ids):
        if not f or getattr(f, 'file_type', '').lower() != 'docx':
            raise HTTPException(400, f"文件不存在或类型错误: {fid}")
    from utils import read_docx_text
    import os
    all_text = ""
    valid_files = []
    for f in files:
        # 检查文件是否存在
        if not os.path.exists(f.file_path):
            # 文件不存在，删除数据库记录
            await database.delete_file(str(f.id))
            logger.warning(f"文件不存在，已删除数据库记录: {f.original_filename}")
            continue
        valid_files.append(f)
        all_text += read_docx_text(f.file_path) + "\n"
    
    # 检查是否还有有效文件
    if not valid_files:
        raise HTTPException(400, "所有选择的文件都不存在")
    import os
    import uuid
    from config import settings
    cloud_map_path = os.path.join(settings.OUTPUT_DIR, f"batch_{uuid.uuid4().hex}_cloudmap.png")
    generate_wordcloud(all_text, cloud_map_path)
    return {"cloud_map_url": f"/api/files/cloud_map/{os.path.basename(cloud_map_path)}"}

@router.get("/files/cloud_map/{filename}")
def download_cloud_map(filename: str):
    import os
    file_path = os.path.join("outputs", filename)
    if not os.path.exists(file_path):
        raise HTTPException(404, "词云图片不存在")
    return FastAPIFileResponse(file_path, media_type="image/png", filename=filename)


@router.get("/files")
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
        total = await database.get_files_count()
        response_files = [
            FileResponse(
                id=str(file_model.id),
                filename=file_model.filename,
                original_filename=file_model.original_filename,
                file_size=file_model.file_size,
                file_type=file_model.file_type,
                status=file_model.status,
                created_at=file_model.created_at
            )
            for file_model in files
        ]
        
        logger.info(f"成功获取 {len(response_files)} 个文件")
        return {"total": total, "items": response_files}
        
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


@router.post("/files/generate_weekly_report/{file_id}")
async def generate_weekly_report(file_id: str, request: WeeklyReportRequest = Body(...)):
    """
    生成周报接口
    
    功能：
    - 根据文件ID列表从数据库的"files"集合中找到文件
    - 读取所有文件内容并合并
    - 调用大模型总结内容生成周报
    - 返回生成的周报文件
    
    Args:
        file_id: 主文件ID（用于路径参数）
        request: 周报生成请求，包含文件ID列表、周次信息和期望的文件名
        
    Returns:
        生成的周报文件
        
    Raises:
        HTTPException: 文件不存在或生成失败时抛出异常
    """
    try:
        # 确定要处理的文件ID列表
        file_ids = request.file_ids if request.file_ids else [file_id]
        logger.info(f"开始生成周报，文件ID列表: {file_ids}")
        
        # 读取所有文件内容
        all_file_contents = []
        for current_file_id in file_ids:
            # 获取文件信息
            file_model = await database.get_file_by_id(current_file_id)
            
            if not file_model:
                raise HTTPException(status_code=404, detail=f"文件不存在: {current_file_id}")
            
            # 检查文件是否存在
            if not os.path.exists(file_model.file_path):
                raise HTTPException(status_code=404, detail=f"文件在服务器上不存在: {current_file_id}")
            
            # 读取文件内容
            file_content = ""
            if file_model.file_type == "docx":
                file_content = read_docx_text(file_model.file_path)
            elif file_model.file_type == "pdf":
                # 对于PDF文件，需要先转换为文本
                # 这里可以添加PDF文本提取功能
                raise HTTPException(status_code=400, detail="暂不支持PDF文件生成周报")
            else:
                raise HTTPException(status_code=400, detail="不支持的文件类型")
            
            if not file_content.strip():
                logger.warning(f"文件内容为空: {current_file_id}")
                continue
                
            all_file_contents.append(file_content)
        
        if not all_file_contents:
            raise HTTPException(status_code=400, detail="所有文件内容都为空")
        
        # 合并所有文件内容
        combined_content = "\n\n".join(all_file_contents)
        
        # 构建AI产品新闻周报生成提示词
        week_info = f"（周次：{request.week_key}）" if request.week_key else ""
        prompt = f"""
请根据以下{len(file_ids)}个日报文件的内容生成一份详细的AI产品新闻周报{week_info}：

{combined_content}

要求：
1. 周报应该聚焦于AI产品相关的新闻、动态和趋势
2. 按照时间顺序或重要性进行组织
3. 突出重要的AI产品发布、技术突破、市场动态
4. 使用清晰的结构和格式，包含以下部分：
   - 本周AI产品重要新闻
   - 技术突破与创新
   - 市场动态与趋势
   - 重要公司动态
   - 行业影响分析
5. 语言简洁明了，重点突出，适合专业人士阅读
6. 如果有具体数据、产品信息或技术细节，请详细列出
7. 分析新闻对行业的影响和未来趋势
8. 使用专业术语，保持客观中立的语调
9. 整合多个日报的内容，避免重复，突出本周的重要事件

请生成一份完整的AI产品新闻周报。
"""
        
        # 调用大模型生成周报
        weekly_report_content = call_deepseek(prompt)
        
        # 生成周报文件名
        # 使用前端传递的期望文件名，如果没有则使用默认格式
        if request.expected_filename:
            weekly_report_filename = request.expected_filename
            # 确保文件名有.docx扩展名
            if not weekly_report_filename.endswith('.docx'):
                weekly_report_filename += '.docx'
        else:
            # 默认文件名格式，优先使用周次信息
            if request.week_key:
                base_filename = f"周报_{request.week_key}"
            else:
                base_filename = f"周报_{file_id}"
            
            # 限制文件名最多15个字符（不包含扩展名）
            if len(base_filename) > 15:
                base_filename = base_filename[:15]
            weekly_report_filename = f"{base_filename}.docx"
        
        weekly_report_path = os.path.join(settings.OUTPUT_DIR, weekly_report_filename)
        
        # 将周报内容写入Word文档
        write_docx_text(weekly_report_content, weekly_report_path)
        
        # 获取生成的文件大小
        weekly_report_size = get_file_size(weekly_report_path)
        
        # 准备周报文件数据
        weekly_report_data = {
            "filename": weekly_report_filename,
            "original_filename": weekly_report_filename,
            "file_path": weekly_report_path,
            "file_size": weekly_report_size,
            "file_type": "docx",
            "status": "weekreport"
        }
        
        # 将周报文件保存到数据库
        weekly_report_model = await database.create_file(weekly_report_data)
        
        if not weekly_report_model:
            raise HTTPException(status_code=500, detail="保存周报文件到数据库失败")
        
        logger.info(f"周报生成成功: {weekly_report_path}, 数据库ID: {weekly_report_model.id}")
        
        # 返回周报文件
        return FastAPIFileResponse(
            path=weekly_report_path,
            filename=weekly_report_filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"生成周报失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成周报失败: {str(e)}")


@router.get("/files/generated_reports")
async def get_generated_reports(skip: int = 0, limit: int = 100):
    """
    获取所有生成的周报文件列表
    
    功能：
    - 查询数据库中status为"weekreport"的文件
    - 返回生成的周报文件列表
    
    Args:
        skip: 跳过的记录数
        limit: 返回的记录数限制
        
    Returns:
        生成的周报文件列表
    """
    try:
        logger.info(f"获取生成的周报文件列表: skip={skip}, limit={limit}")
        
        # 使用过滤器查询status为"weekreport"的文件
        filter_dict = {"status": "weekreport"}
        generated_files = await database.get_files_by_filter(filter_dict)
        
        # 转换为响应格式
        response_files = []
        for file_data in generated_files:
            response_files.append({
                "id": str(file_data["_id"]),
                "filename": file_data["filename"],
                "original_filename": file_data["original_filename"],
                "file_size": file_data["file_size"],
                "file_type": file_data["file_type"],
                "status": file_data["status"],
                "created_at": file_data["created_at"]
            })
        
        # 按创建时间倒序排列
        response_files.sort(key=lambda x: x["created_at"], reverse=True)
        
        # 应用分页
        paginated_files = response_files[skip:skip + limit]
        
        logger.info(f"成功获取生成的周报文件列表，共 {len(paginated_files)} 个文件")
        
        return {
            "files": paginated_files,
            "total": len(response_files),
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"获取生成的周报文件列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取生成的周报文件列表失败")


@router.get("/files/generated_reports/{report_id}/download")
async def download_generated_report(report_id: str):
    """
    下载生成的周报文件
    
    功能：
    - 根据周报文件ID下载生成的周报文件
    
    Args:
        report_id: 周报文件ID
        
    Returns:
        生成的周报文件
        
    Raises:
        HTTPException: 文件不存在时抛出异常
    """
    try:
        logger.info(f"下载生成的周报文件: {report_id}")
        
        # 获取周报文件信息
        report_model = await database.get_file_by_id(report_id)
        
        if not report_model:
            raise HTTPException(status_code=404, detail="周报文件不存在")
        
        # 检查文件状态
        if report_model.status != "weekreport":
            raise HTTPException(status_code=400, detail="该文件不是生成的周报文件")
        
        # 检查文件是否存在于磁盘
        if not os.path.exists(report_model.file_path):
            raise HTTPException(status_code=404, detail="周报文件在服务器上不存在")
        
        logger.info(f"成功下载周报文件: {report_model.filename}")
        
        # 返回周报文件
        return FastAPIFileResponse(
            path=report_model.file_path,
            filename=report_model.original_filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"下载周报文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail="下载周报文件失败")