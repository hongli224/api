# File Conversion API

一个基于Python FastAPI的文件转换后端服务，支持DOCX转PDF等功能。

## 功能特性

- 📁 **文件上传**: 支持DOCX和PDF文件上传
- 🔄 **格式转换**: DOCX转PDF转换功能
- 🗄️ **数据存储**: 使用MongoDB存储文件信息
- 📊 **文件管理**: 文件列表查询、删除等管理功能
- 🔒 **输入验证**: 完整的文件类型和大小验证
- 📝 **日志记录**: 详细的日志记录功能
- 🚀 **异步处理**: 使用async/await进行异步操作

## 技术栈

- **Web框架**: FastAPI
- **数据库**: MongoDB (Motor异步驱动)
- **文件处理**: python-docx2pdf, aiofiles
- **数据验证**: Pydantic
- **日志**: Loguru
- **服务器**: Uvicorn

## API接口

### 1. 文件上传
- **接口**: `POST /api/file_upload`
- **功能**: 上传文件到服务器
- **参数**: 文件对象 (multipart/form-data)
- **返回**: 文件信息

### 2. DOCX转PDF
- **接口**: `POST /api/convert_docx_to_pdf`
- **功能**: 将DOCX文件转换为PDF
- **参数**: 
  ```json
  {
    "file_id": "文件ID"
  }
  ```
- **返回**: 转换结果信息

### 3. 获取文件列表
- **接口**: `GET /api/files`
- **功能**: 获取所有文件列表
- **参数**: 
  - `skip`: 跳过的记录数 (可选)
  - `limit`: 返回的记录数限制 (可选)
- **返回**: 文件列表

### 4. 获取单个文件
- **接口**: `GET /api/files/{file_id}`
- **功能**: 获取指定文件的详细信息
- **参数**: `file_id` (路径参数)
- **返回**: 文件详细信息

### 5. 删除文件
- **接口**: `DELETE /api/files/{file_id}`
- **功能**: 删除指定文件
- **参数**: `file_id` (路径参数)
- **返回**: 删除结果

## 项目结构

```
project/
├── main.py              # 主应用程序入口
├── config.py            # 配置文件
├── database.py          # 数据库模型和连接
├── api.py              # API路由定义
├── utils.py            # 工具函数
├── requirements.txt    # 项目依赖
├── entrypoint.sh      # 启动脚本
├── README.md          # 项目说明
├── uploads/           # 上传文件存储目录
├── outputs/           # 转换输出目录
└── logs/              # 日志文件目录
```

## 安装和运行

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境
确保MongoDB连接字符串正确配置在 `config.py` 中。

### 3. 运行服务
```bash
# 使用启动脚本
./entrypoint.sh

# 或直接运行
python main.py
```

### 4. 访问服务
- 服务地址: http://localhost:5000
- API文档: http://localhost:5000/docs
- ReDoc文档: http://localhost:5000/redoc

## 配置说明

主要配置项在 `config.py` 中：

- `MONGODB_URL`: MongoDB连接字符串
- `DATABASE_NAME`: 数据库名称
- `UPLOAD_DIR`: 上传文件存储目录
- `OUTPUT_DIR`: 转换输出目录
- `MAX_FILE_SIZE`: 最大文件大小限制
- `ALLOWED_EXTENSIONS`: 允许的文件类型

## 数据库设计

### 文件集合 (files)
```json
{
  "_id": "ObjectId",
  "filename": "唯一文件名",
  "original_filename": "原始文件名",
  "file_path": "文件存储路径",
  "file_size": "文件大小(字节)",
  "file_type": "文件类型",
  "status": "文件状态",
  "created_at": "创建时间",
  "updated_at": "更新时间"
}
```

## 错误处理

API使用统一的错误处理机制：

- `400`: 请求参数错误
- `404`: 资源不存在
- `500`: 服务器内部错误

错误响应格式：
```json
{
  "error": "错误类型",
  "message": "错误描述"
}
```

## 日志记录

使用Loguru进行日志记录，支持：

- 控制台输出
- 文件轮转
- 不同级别的日志
- 结构化日志格式

## 开发说明

### 代码规范
- 所有函数都有详细的文档字符串
- 使用类型注解
- 遵循PEP 8代码风格
- 异步操作使用async/await

### 测试
建议添加单元测试和集成测试来确保代码质量。

### 部署
项目可以部署到各种云平台，如Docker、Kubernetes等。

## 许可证

MIT License 