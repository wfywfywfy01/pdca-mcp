# pdca-mcp

PDCA 经销商数据 MCP 服务 —— 独立于 `pdca-workbench` 看板，只读查询生产 PostgreSQL，供团队成员的 AI 助手（Claude Desktop / Cursor / opencode）调用。

## 能力（只读查询）

| tool | 说明 | 口径 |
|---|---|---|
| `query_stores(region)` | 活跃门店列表 | — |
| `query_sell_in(month)` | 经销商进货金额 | 万 CNY |
| `query_sell_out(month)` | 经销商终销金额 | USD |
| `query_five_kit(month, dealer_id)` | 门店五件套明细 | 客流来源 + 成交漏斗 |
| `query_meetings(date)` | 会议记录 + 待办 | — |
| `query_monthly_targets(month)` | 月度目标 | — |

## 安装

```bash
cd pdca-mcp
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
cp .env.example .env            # 填 PDCA_MCP_DATABASE_URL 和 PDCA_MCP_API_KEYS
```

## 配置到别人的 AI

### Claude Desktop

在 `claude_desktop_config.json` 里加：

```json
{
  "mcpServers": {
    "pdca": {
      "command": "python",
      "args": ["-m", "pdca_mcp.server"],
      "cwd": "D:\\pdca-mcp"
    }
  }
}
```

### Cursor / opencode

在 MCP 配置里加同样的 stdio 命令（`python -m pdca_mcp.server`），工作目录指向 `pdca-mcp`。

### 远程团队共享（HTTP + API Key）

在服务器上跑：

```bash
python -m pdca_mcp.server --transport http --port 8765
```

其他人在 AI 客户端配 SSE/HTTP URL：

```
http://<host>:8765/mcp
```

并在请求里带 `Authorization: Bearer <PDCA_MCP_API_KEYS 中的一把 key>`。

## 认证

- **stdio（本地）**：靠本机信任，`.env` 里的数据库连接即凭证。
- **HTTP（远程）**：`PDCA_MCP_API_KEYS` 里配置的 key 作为 Bearer token（多个 key 逗号分隔，分发给不同使用者）。

> 当前第一版为只读查询，连接建议用只读数据库账号，不要用 postgres 超级用户。
