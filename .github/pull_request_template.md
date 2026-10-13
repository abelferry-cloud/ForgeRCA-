<!--
提交前请先阅读 CONTRIBUTING.md 的《分支与合并规范》：
本改动必须来自功能分支，不得直接提交或推送到 main。
计划、目标数字与未运行的功能不要写成已实现结果。
-->

## 关联任务

<!-- 例如 M0-08、M1-21。若为计划外修复，请说明触发问题的现象与来源。 -->

## 背景

<!-- 修复什么问题？对应哪份来源、哪个错误案例或哪处数据缺口？ -->

## 变更摘要

<!-- 数据结构 / API / 行为的前后区别。涉及字段变更时请同步更新 docs/data-spec.md 与数据卡。 -->

## 证据

<!-- 粘贴真实可运行的命令与输出摘要。不要粘贴未执行的预期结果。 -->

```
python scripts/validate_data.py
python scripts/check_sensitive_files.py
python -m unittest discover -s tests -v
```

## 影响

<!-- 数据授权、模型与文档版本、评测泄漏、执行安全，以及是否为破坏性变更。 -->

## 待办

<!-- 本 PR 未覆盖的边界条件，以及后续任务 ID。 -->

## 自检

- [ ] 改动来自功能分支，未直接提交或推送到 `main`
- [ ] `python scripts/validate_data.py` 通过
- [ ] `python scripts/check_sensitive_files.py` 通过
- [ ] `python -m unittest discover -s tests -v` 通过
- [ ] 未提交密钥、客户数据、厂商原文 PDF、本地索引或实验产物
- [ ] `data/evaluation/` 与人工 gold label 未被加入索引、训练语料或模型上下文
- [ ] 涉及来源、字段或评测口径的改动已同步更新对应文档
- [ ] 若勾选了 TODO 中的任务，勾选状态与实际完成情况一致
- [ ] 未把计划中的能力、目标指标描述为已运行结果
