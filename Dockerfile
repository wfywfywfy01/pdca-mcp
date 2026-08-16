# 基于服务器已有的 MCP 运行时镜像（含 mcp / psycopg2 / uvicorn 依赖），
# 只覆盖业务代码，避免在受限网络上重新 pip install。
FROM pdca-mcp:sse-fix

WORKDIR /app

COPY src ./src
ENV PYTHONPATH=/app/src

EXPOSE 8765

CMD ["python", "-m", "pdca_mcp.server", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
