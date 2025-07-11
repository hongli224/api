#!/bin/bash
# 激活Python虚拟环境
. bin/activate

# 安装依赖包
echo "📦 安装项目依赖..."
pip install -r requirements.txt

# 创建日志目录
mkdir -p logs

# 启动File Conversion API服务
echo "🚀 启动File Conversion API服务..."
python3 main.py