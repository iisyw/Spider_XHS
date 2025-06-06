FROM python:3.9-slim

# 安装 tzdata 设置时区
RUN apt-get update && apt-get install -y tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 安装Node.js
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制项目并安装依赖
COPY . .

# 使用 Aliyun 镜像源加速 pip
RUN pip install -i https://mirrors.aliyun.com/pypi/simple/ -U pip \
    && pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

RUN pip install --no-cache-dir -r requirements.txt
RUN npm install

# 启动程序
CMD ["python", "main.py"]

# 构建说明
# docker build -t spider_xhs:latest .
# docker run -it --name spider_xhs -v $(pwd)/datas:/app/datas -v $(pwd)/.env:/app/.env spider_xhs