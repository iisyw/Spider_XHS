FROM python:3.9-slim

# 设置代理地址变量（只需修改此处）
ARG PROXY_URL=http://proxy-server:port

# 配置系统级代理环境变量
ENV http_proxy=${PROXY_URL}
ENV https_proxy=${PROXY_URL}
ENV HTTP_PROXY=${PROXY_URL}
ENV HTTPS_PROXY=${PROXY_URL}

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

# 配置npm使用代理
RUN npm config set proxy ${PROXY_URL} && \
    npm config set https-proxy ${PROXY_URL}

# 复制项目并安装依赖
COPY . .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt
RUN npm install

# 构建完成后清除代理设置
ENV http_proxy=
ENV https_proxy=
ENV HTTP_PROXY=
ENV HTTPS_PROXY=

# 启动程序
CMD ["python", "main.py"]

# 构建说明
# 直接使用默认代理：docker build -t spider_xhs:latest .
# 或指定代理：docker build -t spider_xhs:latest --build-arg PROXY_URL=http://your-proxy:port .