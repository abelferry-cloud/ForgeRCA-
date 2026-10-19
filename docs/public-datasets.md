# ForgeRCA 公开数据清单与下载指引

> 首次核查 2026-10-13；2026-10-19 完成实测下载与结构校验（见《实测下载与结构校验》）。这里是**候选或独立实验数据**，不能自动认定已被现有 ABB 主知识库使用。以数据提供者的最新许可条款为准。

## 先明确数据责任边界

主线采用仓库现有的 **ABB ACS580-01** 官方手册与 `data/sources/manifest.json`。其下载脚本是 `scripts/download_sources.py`，目标目录是 `data/raw/abb/`，并有固定 SHA-256 检验。下面的数据只用来支持信息抽取、额外实验或可选的时序拓展，**不应拼凑为属于同一真实设备的跨文档事件链**。

### 数据选型表

| 数据源 | 规模 / 类型 | 许可证 / 版权 | 适合做什么 | 不适合做什么 | 获取 |
| --- | --- | --- | --- | --- | --- |
| **ABB ACS580-01 官方固件 / 硬件手册** | 现有 2 份已锁定修订 PDF | 厂商版权，原文再分发**未获核实** | 故障码、维修措施、PDF 证据页码、主 GraphRAG | 直接入 Git、跨型号混用 | [仓库既有来源清单](../data/sources/README.md)；`python scripts/download_sources.py` |
| **MaintIE gold** | 约 1,076 条细粒度维修短文本及实体/关系标注 | 上游仓库声明 **MIT** | 测试实体抽取、关系识别与规范化 | 当 ABB ACS580 实际闭环工单和根因真值 | [GitHub](https://github.com/nlp-tlp/maintie) / [原始 JSON](https://raw.githubusercontent.com/nlp-tlp/maintie/main/data/gold_release.json) |
| **MaintIE silver** | 约 7,000 条粗粒度标注短文本 | 上游仓库声明 **MIT** | 数据增强、抽取算法探索 | 混充人工专家标签或同型号历史工单 | [原始 JSON](https://raw.githubusercontent.com/nlp-tlp/maintie/main/data/silver_release.json) |
| **AI4I 2020** | 10,000 行**合成**设备工况表格 | [**CC BY 4.0**](https://creativecommons.org/licenses/by/4.0/) | 表格字段、异常上下文模拟、结构化分类扩展 | 当真实工业告警、维修文本或 RAG 根因评测 | [UCI 数据页](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset) |
| **MetroPT-3** | 约 151.7 万行真实压缩机传感器数据，压缩下载约 208 MB | [**CC BY 4.0**](https://creativecommons.org/licenses/by/4.0/) | 时序故障上下文、异常检测扩展 | 当逐行已核实根因标签；不是 ABB 数据 | [UCI 数据页](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset) |
| **Schneider ATV320 编程 / 安装手册** | PDF，修订随官方更新 | 厂商版权，**再分发未核实** | 第二阶段跨品牌测试、额外故障码词典 | 和 ABB 适用性混用，或将 PDF 上传 Git | [中文版编程手册](https://www.schneider-electric.cn/zh/download/document/NVE41300/) / [安装手册](https://www.schneider-electric.cn/zh/download/document/NVE41294/) |

**许可须知**：MaintIE GitHub 仓库的 MIT 说明见其 README / LICENSE；UCI AI4I 和 MetroPT-3 数据页明确为 CC BY 4.0。数据最终使用时还应保留引用文献、版本来源、改动声明。厂商 PDF “网页可下载”不等于“可在 GitHub 再分发”。

## 一键下载（使用 Python 标准库）

在仓库根目录运行：

```bash
# 查看名称、规模、官方链接，不联网
python scripts/download_public_data.py --list

# 下载 MaintIE gold（优先推荐）
python scripts/download_public_data.py --dataset maintie-gold

# 可选：MaintIE silver
python scripts/download_public_data.py --dataset maintie-silver

# 可选：AI4I，下载 ZIP 之后只提取 ai4i2020.csv
python scripts/download_public_data.py --dataset ai4i

# 大文件：MetroPT-3（约 208 MB，显式授权大文件下载；ZIP 默认不解压）
python scripts/download_public_data.py --dataset metropt3 --allow-large
```

结果统一写入 `data/raw/public/{dataset_key}/`，例如：

```text
data/raw/public/
├── maintie-gold/
│   ├── gold_release.json
│   └── PROVENANCE.json
├── ai4i/
│   ├── ai4i2020.csv
│   └── PROVENANCE.json
└── metropt3/
    ├── metropt+3+dataset.zip
    └── PROVENANCE.json
```

**安全策略**：下载器限定来源 URL 白名单、有限超时和下载体积上限；写入临时文件、通过校验后原子替换，遇到现存数据默认不覆盖；ZIP 仅按文件名定位 CSV，不进行任意路径解压。每次保存来源 URL、下载 UTC 时间、SHA-256 与许可证。上游数据可能更新，首次运行的 SHA 需记录而不是硬编码一个未经验证的哈希。

> 本仓库**不提交任何第三方原始文件**：下载结果写入被 `.gitignore` 忽略的 `data/raw/public/`，只在 `data/sources/public-datasets.json` 记录核验快照。2026-10-19 已在本机完成 MaintIE gold 与 AI4I 的下载和结构校验；若你的网络无法访问上游，可按《手动下载方法》从官方页面获取，存入相同位置后再做本地校验。

## 实测下载与结构校验（2026-10-19）

在仓库根目录执行（仅用 Python 标准库，无第三方依赖）：

```bash
python scripts/download_public_data.py --list
python scripts/download_public_data.py --dataset maintie-gold
python scripts/download_public_data.py --dataset ai4i
```

| 数据集 | 文件 | 大小（字节） | 记录数 | SHA-256（处理后文件） |
| --- | --- | ---: | ---: | --- |
| MaintIE gold | `gold_release.json` | 817,880 | 1,076 | `ef811cf4ffd0c90e6a13b1369e24e9d1d08f9a294d873ab4fb1a580096d7d6e0` |
| AI4I 2020 | `ai4i2020.csv` | 522,170 | 10,000 | `dc6630cd9b1f0f853922fad78a1b6436570d3f1ec863f1dd5c4340ac56bc8a8e` |

完整哈希、下载 UTC 时间与 AI4I 归档哈希记录在 [公开数据清单](../data/sources/public-datasets.json) 的 `verified_snapshot` 字段；本地 `PROVENANCE.json` 由下载器自动生成，不入 Git。`--list` 在断网条件下也返回 0，不发起网络请求。

**MaintIE gold 结构校验**

- 1,076 条记录，全部含非空 `text`、`tokens`、`entities`、`relations`，且每条至少有一个实体。
- 共 3,397 个实体、2,341 条关系；155 种层级实体类型（如 `State/UndesirableState/FailedState`）、6 种关系类型（`hasPart`、`isA`、`contains`、`hasProperty`、`hasParticipant/hasAgent`、`hasParticipant/hasPatient`）。
- 实体的 `start`/`end` 是 **token 下标**（半开区间），全部落在 `0 <= start < end <= len(tokens)` 内；按 token 复原的实体片段与原文一致，没有越界或断词。
- 关系的 `head`/`tail` 是 **`entities` 数组下标**，不是字符或 token 偏移；2,341 条关系全部能用该下标索引到实体。这一点极易被误读成 token 偏移——M3-12 用该数据评测抽取时，必须按下标读取，否则会把关系错连到无关实体。
- 每条记录最多 12 个 token，属于单句短文本基准；不能替代跨文档、长上下文或 ABB 故障表的样本。

**AI4I 2020 结构校验**

- 10,000 行 × 14 列，`UDI` 为 1–10,000 的连续唯一整数；不存在 `WO`、`ABB` 或其他工单编号字段。
- `Machine failure=1` 共 339 行；子模式 TWF 46、HDF 115、PWF 95、OSF 98、RNF 19。
- 产品类型分布 L 6,000 / M 2,997 / H 1,003，类别明显不均衡。
- 上游明确声明该数据为**合成**表格数据；本项目只把它当表格特征与异常上下文的实验素材，不映射到 ABB 故障码，也不为它生成工单 ID。

未做的部分：MaintIE silver 与 MetroPT-3 本次未下载（前者与 gold 同源，后者约 208 MB），因此不对其内容作任何断言。

## 数据卡

数据卡格式见[数据卡模板](data-card-template.md)；种子语料的数据卡见 [data/README.md](../data/README.md)。

### MaintIE gold

| 项 | 内容 |
| --- | --- |
| 标识 / 版本 | `maintie-gold`，核验于 2026-10-19T06:07:19Z |
| 来源 | nlp-tlp/maintie，GitHub `main` 分支 raw 文件；SHA-256 `ef811cf4…d7d6e0` |
| 字段 | `text`（字符串）、`tokens`（字符串数组）、`entities`（`start`/`end` token 下标 + `type`）、`relations`（`head`/`tail` 实体下标 + `type`） |
| 规模 | 1,076 条 / 3,397 实体 / 2,341 关系 |
| 合成标记 | 无合成字段；上游人工标注的维修短文本，来源领域混杂（暖通、泵、车辆等），本项目未核对其采集来源与脱敏方式 |
| 授权 | 上游仓库声明 MIT，以官方 LICENSE 为准；引用 LREC-COLING 2024 论文 |
| 已知偏差 | 单句短文本；155 类层级标签长尾；不含 ACS580 或任何 ABB 型号语境 |
| 标注状态 | 上游 gold 标注，本项目未逐条复核 |
| 预处理版本 | 无，原始 JSON 原样保存 |
| 使用边界 | 仅用于实体/关系抽取评测；不得写入 ABB 语料或当作 ABB 根因真值 |

### AI4I 2020

| 项 | 内容 |
| --- | --- |
| 标识 / 版本 | `ai4i`，核验于 2026-10-19T06:07:23Z |
| 来源 | UCI ID 601，DOI 10.24432/C5HS5C；归档 SHA-256 `f601f142…26b252`，提取后 CSV `dc6630cd…bc8a8e` |
| 字段 | `UDI`、`Product ID`、`Type`、气温/工艺温度/转速/扭矩/刀具磨损、`Machine failure` 与 5 个子模式标志 |
| 规模 | 10,000 行 × 14 列，339 条故障 |
| 合成标记 | 上游声明为合成数据；无独立合成字段，按来源标注识别 |
| 授权 | CC BY 4.0，需署名 |
| 已知偏差 | 类别不均衡（H 型仅 1,003 行）；工况为模拟生成；无维修文本、无根因标注 |
| 标注状态 | 上游合成标签，非现场复核 |
| 预处理版本 | 仅从 ZIP 提取 `ai4i2020.csv`，内容未改动 |
| 使用边界 | 仅用于表格特征与异常上下文实验；不映射 ABB 故障码，不生成工单 ID |

## 手动下载方法

**MaintIE**：打开 [nlp-tlp/maintie](https://github.com/nlp-tlp/maintie) → `data` → `gold_release.json` → Download raw；或直接下载上表中的原始 JSON。下载后查看 `text`、`tokens`、`entities`、`relations` 字段：`entities` 的 `start`/`end` 是 token 下标，`relations` 的 `head`/`tail` 是 `entities` 数组下标，二者不是同一种偏移。

**AI4I**：打开 [UCI ID 601](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset) → Download → 解压 → `ai4i2020.csv`；字段涉及转速、温度、扭矩和故障模式，其中 failure mode 由数据集作者合成，不代表设备现场复核。

**MetroPT-3**：打开 [UCI ID 791](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset) → Download；内含 `MetroPT3(AirCompressor).csv` 和数据描述文档。该数据虽有故障时间窗报告，但 UCI 页面说明主体序列**不是逐行标签数据**，不得直接计算文本根因 Top-1。

**ABB**：不要使用本站下载器替代现有受控的 `download_sources.py`，也不要把不同日期的官方新修订覆盖旧文件；现有页码与来源 ID 已绑定固定 SHA-256。先按照 `data/sources/README.md` 校验再更新来源元数据。

## 公开数据如何组合？

| 实验 | 文本来源 | 标签真值来源 | 是否主线 |
| --- | --- | --- | --- |
| ABB 证据检索 / GraphRAG | 固定版 ABB 官方 PDF、项目编写的可溯源注释、合成工单 | 独立人工核验的 ABB 证据 ID / 候选根因 | **是** |
| 维修文本实体关系抽取 | MaintIE gold / silver | MaintIE 原标注 | 独立子实验 |
| 表格工况与告警原型 | AI4I | 上游合成模式标签 | 备选 |
| 时序异常背景 | MetroPT-3 | 上游故障事件时间窗（有限） | 备选 |
| 跨品牌适用性 | Schneider ATV320 官方资料 | 针对 ATV320 的独立新建答案 | 第二阶段 |

**绝对不要**：将 MaintIE 的工单归给 ABB 某个真实设备、把 AI4I 的类别直接映射到 ABB 故障码、把 MetroPT 的压缩机故障报表当作 ATV320 维修结论。

## 推荐的数据落地流程

1. 在 `data/sources/` 登记数据集名称、发布者、链接、许可证、引用要求、使用目的。
2. 所有第三方原始内容保存在 `data/raw/`，通过 `.gitignore` 避免无意推送。
3. 根据来源将公开数据转为独立 `data/processed/public/` 的类型化结构；不要修改仓库已有 ABB `data/corpus/` 协议。
4. 后续若选择把某些真实文本作为背景检索语料，需要人工复核作用域、授权、偏差和时间可用性。
5. 对 200 条正式诊断评测，另建冻结的数据版本并记录审核人；合成数据必须显式标记。

## 学术引用

- **MaintIE**：Bikaun et al., *MaintIE: A Fine-Grained Annotation Schema and Benchmark for Information Extraction from Maintenance Short Texts*, LREC-COLING 2024. [ACL Anthology](https://aclanthology.org/2024.lrec-main.954/)。
- **AI4I 2020**：UCI Machine Learning Repository, DOI: [10.24432/C5HS5C](https://doi.org/10.24432/C5HS5C)。
- **MetroPT-3**：Davari et al., UCI Machine Learning Repository, DOI: [10.24432/C5VW3R](https://doi.org/10.24432/C5VW3R)。

## 数据更新检查清单

- [ ] 来源 URL 与许可页面在下载当天可访问。
- [ ] 文件哈希、大小、来源及时间记录完整；上游更新时新增 `verified_snapshot`，不覆盖旧记录。
- [ ] 无第三方版权文件或真实敏感工单进入 Git。
- [ ] 当前实验没有错误跨设备/跨数据集关联。
- [ ] 评测标准答案从未进入在线检索索引。
- [ ] README 的“已实现”描述与实际下载 / 处理结果一致。
