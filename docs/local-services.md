# 本地数据库服务（M1-04）

`compose.yaml` 提供 PostgreSQL、OpenSearch 和 Neo4j 三个独立服务，用于后续里程碑开发。当前没有应用表结构、索引、图谱入库或诊断 API。

## 前置条件

- Docker Engine / Docker Desktop 正常运行，使用 Linux 容器；Docker Compose v2 支持 `up --wait`。
- OpenSearch 所在 Linux 虚拟机的 `vm.max_map_count` 至少为 `262144`，Docker 可用内存至少 4 GiB。Windows 的对应设置见 [OpenSearch 2.17 Docker 指南](https://docs.opensearch.org/2.17/install-and-configure/install-opensearch/docker/)。
- 将 `.env.example` 复制为 `.env`，填写非空 `POSTGRES_PASSWORD` 和至少 8 个字符的 `NEO4J_PASSWORD`。已有 `.env` 时直接编辑，不覆盖原配置；`.env` 不提交 Git。密码包含 `$` 或 `#` 时，用单引号包围整个值以保持字面量。
- Neo4j 初始用户固定为 `neo4j`，本地连接的 `NEO4J_USER` 保持该值。官方镜像不支持通过 `NEO4J_AUTH` 改初始用户名，见 [Neo4j 初始化说明](https://neo4j.com/docs/operations-manual/current/docker/introduction/)。

本次选用的镜像标签为 `postgres:16.4-alpine`、`opensearchproject/opensearch:2.17.1`、`neo4j:5.26-community`；不是最新版本或安全审计结论，也尚未按镜像 digest 锁定。完整版本复现清单属于 M1-06。

## 启动与停止

在仓库根目录执行：

```bash
# 只验证配置，不输出含凭据的展开结果
docker compose config --quiet
docker compose up -d --wait --wait-timeout 300
docker compose ps

# 删除容器和网络，保留三个命名数据卷
docker compose down
```

`up --wait` 必须成功退出且三个服务均为 `healthy`，才算启动通过。端口默认值与覆盖项：

| 服务 | 默认本机端口 | `.env` 覆盖项 |
| --- | --- | --- |
| PostgreSQL | 5432 | `POSTGRES_PORT` |
| OpenSearch HTTP | 9200 | `OPENSEARCH_PORT` |
| Neo4j HTTP | 7474 | `NEO4J_HTTP_PORT` |
| Neo4j Bolt | 7687 | `NEO4J_BOLT_PORT` |

改变 Neo4j Bolt 端口时，还要同步 `NEO4J_URI`。`POSTGRES_HOST`、`OPENSEARCH_HOST` 和 `NEO4J_URI` 是宿主机上的应用连接地址，不改变容器内部监听地址。

所有发布端口固定绑定 `127.0.0.1`。OpenSearch 为本地开发关闭认证与 TLS，`OPENSEARCH_USER` / `OPENSEARCH_PASSWORD` 当前不用于容器启动；不要用于共享服务器或生产环境。

健康检查分别是 PostgreSQL `pg_isready`、OpenSearch cluster health HTTP 请求、Neo4j `cypher-shell RETURN 1`。前两者只检查服务就绪/接口可达，不证明业务 schema、索引已建立或 OpenSearch 分片全部正常。PostgreSQL 的凭据是否正确也不能仅凭 `pg_isready` 判定。

修改 `.env` 的初始密码不会更新已有数据卷中的数据库密码。需要按数据库自身的改密流程处理；不要为了试错删除已有数据。`docker compose down --volumes` 会删除本项目三个数据卷，只适合主动丢弃一次性测试数据时使用。

## 验证范围与记录

```bash
# 只需 Compose CLI，不依赖 daemon，也不会读取本地 .env
python -m unittest discover -s tests -p test_compose.py -v
```

配置测试覆盖默认/自定义端口的回环绑定、空/缺失凭据失败、密码插值与健康检查隔离、Neo4j 初始用户名约束。没有 Compose CLI 时明确跳过；现有标准库测试不因此强制安装 Docker。

`.github/workflows/compose.yml` 在独立 GitHub Actions runner 中生成临时凭据、启动三个容器、写入一次性记录、执行 `down` 后重新创建容器并回读记录，最后删除测试卷。测试内容仅为 `persisted` 标记，不导入任何语料或评测数据。

2026-10-22 本地配置测试通过；Docker Desktop 4.43.1 在初始化 `dockerInference` 时因文件访问错误退出，无法进行本地运行时验收。CI 运行结果待本 PR 验证，不将静态校验描述为服务已经启动。
