

FROM python:3.13-slim

WORKDIR /app

# 先单独拷贝依赖，装依赖层可以复用缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 只拷贝后端代码
COPY toutiao_backend/ ./toutiao_backend/
WORKDIR /app/toutiao_backend

EXPOSE 8000

# 以 toutiao_backend 为工作目录，用 uvicorn 启动 main.py 里的 app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]