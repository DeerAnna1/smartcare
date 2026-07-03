---
name: medical-literature-review
display-name: 医学文献检索与综述
description: 检索医学文献并以来源、PMID和证据局限为核心生成简洁综述
version: 1.0.0
license: Proprietary
agents:
  - triage
  - collector
risk-level: low
trigger-examples:
  - 搜索高血压生活方式干预相关医学研究，返回3篇并标注 PMID
---
# 医学文献检索

优先选择已绑定的医学文献检索工具。先搜索，再在用户需要标题、作者或摘要时获取详情。输出必须保留 PMID 或 DOI，不得把文献结论表述为对用户的诊断。
