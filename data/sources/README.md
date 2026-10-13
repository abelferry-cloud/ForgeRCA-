# 外部资料来源与获取

以下文件于 2026-10-13 从 ABB 官方域名下载并核验。`manifest.json` 是机器可读的版本锁定清单；本地文件名由项目命名，不改变厂商文档编号。

| source_id | 文档编号 / 修订 | 生效日期 | PDF 页数 | 核验位置 |
| --- | --- | --- | ---: | --- |
| ABB-FW-H-ZH | 3AXD50000016430 / H | 2024-03-30 | 614 | 第 3 页版本；13 页适用性；536–538、542 页故障条目 |
| ABB-HW-D-ZH | 3AXD50000044837 / D | 2023-02-07 | 316 | 第 3 页版本；25 页适用性；152 页散热器维护 |

下载链接：[中文固件手册 H](https://library.e.abb.com/public/2aca7fc08722463ca4969d62ae69893e/3AXD50000016430_ZH_ACS580_FW_H_A5.pdf)、[中文硬件手册 D](https://library.e.abb.com/public/e583e1b3d0444f1785df2b8330fd3498/ZH_ACS580-01_HW_D_A5.pdf)。

固件手册对应 ASCKX 2.16；硬件手册适用于 ACS580-01，不能把修订 H/D 当作设备固件版本。

## 获取和验证

在仓库根目录运行：

```sh
python scripts/download_sources.py
python scripts/validate_data.py --check-raw
```

也可以手动下载到清单中的 local_path 后运行验证。若下载失败，不改用来源不明的镜像。若官方文件更新导致哈希不符，核验文档编号、修订、页码后添加新来源版本，不覆盖旧来源记录以维持旧标注。

初始化使用本地 PDF 文本提取检查了相关页，页数和哈希均取自下载文件。当前工具不做全量 PDF 解析；后续解析需要独立依赖和抽样检查。

## 发布边界

厂商原文有版权，尚未确认允许在 GitHub 再分发，因此 `redistribution=not_verified`。只发布链接、指纹、定位信息和少量项目编写的事实注释。PDF、全量提取文本及索引保留在忽略目录，代码仓库的任何未来许可证不自动覆盖它们。

## 已调研但尚未导入的备选

| 来源 | 用途 | 当前状态 |
| --- | --- | --- |
| [MaintIE](https://github.com/nlp-tlp/maintie) | 维修短文本实体/关系抽取评测，仓库声明 MIT | 未下载、未混入本设备工单 |
| [IBM AssetOpsBench](https://github.com/IBM/AssetOpsBench) | 工业 Agent 运维场景参考，仓库标注 Apache-2.0 | 未导入，不当作本项目现场数据 |
| [PHM 2025 LMTV](https://github.com/sarahlukens/lukens_phm2025) | 300 条合成故障描述，仓库标注 GPL-3.0 | 与当前设备域不同，未导入 |

选用这些数据前需核对具体数据文件的授权与标注范围；本次没有声称已完成任何外部基准复现。
