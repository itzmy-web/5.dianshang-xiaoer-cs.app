# 电商小二 · 智能客服（SQLite 单容器版）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先装依赖（利用 Docker 层缓存：代码改动不用重装依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 再拷贝代码
COPY main.py .
COPY api/ ./api/
COPY service/ ./service/
COPY engine/ ./engine/
COPY plan/ ./plan/
COPY clarify/ ./clarify/
COPY knowledge/ ./knowledge/
COPY chitchat/ ./chitchat/
COPY task/ ./task/
COPY domain/ ./domain/
COPY repository/ ./repository/
COPY models/ ./models/
COPY infrastructure/ ./infrastructure/
COPY conf/ ./conf/
COPY prompts/ ./prompts/
COPY flow_config/ ./flow_config/
COPY web/ ./web/

# 数据库文件目录（docker-compose 挂卷持久化）
VOLUME ["/app/data"]

EXPOSE 18082

CMD ["sh", "-c", "python main.py"]
