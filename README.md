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

HTTP 的每次请求都必须携带 `Authorization: Bearer ...`，包括已有会话的
工具调用、列表和会话关闭；`Mcp-Session-Id` 不是身份凭据。会话内切换
有效 key 时，数据范围按当次请求的 key 重新计算，不继承原 key 的权限。
未知 key、未知角色以及没有 `owner_key` 的 sales/dealer key 均拒绝访问。
admin/viewer 可以查询全局数据；会议、月度目标暂未实现逐人过滤，因此
HTTP 下只允许 admin/viewer。建议显式配置 `key:role:owner_key`；旧的
单 key 配置仍按原契约视为 admin，不应分发给受限用户。

> 当前第一版为只读查询，连接建议用只读数据库账号，不要用 postgres 超级用户。

## 安全回归与发布

设置 `PYTHONPATH=src` 后运行 `python -m unittest discover -s tests -p "test_*.py"`。
这组测试只使用模拟身份、模拟数据和本地 MCP 协议，不连接数据库。
旧的 `e2e_*.py` 是显式测试环境检查，必须自行提供
`PDCA_MCP_TEST_DATABASE_URL`；远程检查另外需要 `PDCA_MCP_TEST_URL`、
`PDCA_MCP_TEST_ADMIN_KEY`、`PDCA_MCP_TEST_SALES_KEY`。不得配置生产数据库
或把凭据写入代码。删除当前文件的明文不能消除 Git 历史泄露，已暴露的
凭据仍需由所有者授权轮换。

镜像使用固定运行时摘要；发布时从已合并的明确 commit 构建，并传入
`--build-arg SOURCE_REVISION=<commit>`，镜像标签也使用该 commit。
通过 `org.opencontainers.image.revision` 标签核验版本，不发布 `latest`。
当前生产额外使用 `/app/data/start_mcp.py` 的域名防护配置及
`health_sidecar.py`，它们不在此仓库中。替换容器必须保留现有命令、挂载、
网络、端口和健康检查配置，只换镜像；旧容器先停止、改名保留回滚，
不得直接用 Dockerfile 默认命令覆盖现役启动包装脚本。
