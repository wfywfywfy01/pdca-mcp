# 使用已核验的服务器运行时摘要，不跟随可变标签升级依赖。
ARG MCP_RUNTIME_IMAGE=pdca-mcp@sha256:6a906dbfbaf2b1cb35a7482fc84cec40274aee2587319849397b8269e66b5531
FROM ${MCP_RUNTIME_IMAGE}
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.revision=$SOURCE_REVISION \
      org.opencontainers.image.source="https://github.com/wfywfywfy01/pdca-mcp"

WORKDIR /app

COPY src ./src
ENV PYTHONPATH=/app/src

EXPOSE 8765

CMD ["python", "-m", "pdca_mcp.server", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
