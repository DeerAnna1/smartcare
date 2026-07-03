---
name: drug-safety
display-name: 用药安全检查
description: 基于药品标签与相互作用工具执行可追溯的用药安全检查（通过 MCP openfda-drug-safety 服务）
version: 1.0.0
license: Proprietary
allowed-tools: []
agents:
  - collector
  - risk
risk-level: medium
trigger-examples:
  - 这两种药可以一起服用吗
---
# 用药安全检查

先确认用户提供的药名，再调用 openfda-drug-safety MCP 工具（如 openfda_search_adverse_events、openfda_get_drug_label 等）。
必须区分”未发现相互作用”和”数据不足”。不得给出处方级剂量调整建议；信息不足时建议咨询医生或药师。
