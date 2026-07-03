"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";
import KnowledgeGraph, { toFlowNodes, toFlowEdges, NODE_COLORS } from "@/components/kg/KnowledgeGraph";
import KGSearchBar from "@/components/kg/KGSearchBar";
import NodeDetailPanel from "@/components/kg/NodeDetailPanel";
import type { Node, Edge } from "@xyflow/react";

interface NavState {
  nodes: Node[];
  edges: Edge[];
  selectedNode: { type: string; name: string; data: Record<string, unknown> } | null;
}

export default function KnowledgeGraphPage() {
  const { t } = useLang();
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNode, setSelectedNode] = useState<{ type: string; name: string; data: Record<string, unknown> } | null>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<NavState[]>([]);

  const loadSubgraph = useCallback(async (type: string, name: string, addToHistory = true) => {
    // 如果是从节点点击触发，将当前状态压入历史栈
    if (addToHistory && (nodes.length > 0 || selectedNode)) {
      setHistory((prev) => [...prev, { nodes, edges, selectedNode }]);
    }
    setLoading(true);
    try {
      const data = await api.kgSubgraph(type, name, 1);
      setNodes(toFlowNodes(data.nodes));
      setEdges(toFlowEdges(data.edges));

      // 同时加载节点详情
      try {
        const detail = await api.kgNode(type, name);
        setSelectedNode({ type, name, data: detail.data || {} });
      } catch {
        setSelectedNode({ type, name, data: {} });
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [nodes, edges, selectedNode]);

  const handleSearchSelect = useCallback(
    (type: string, name: string) => {
      setHistory([]);
      loadSubgraph(type, name, false);
    },
    [loadSubgraph]
  );

  const handleNodeClick = useCallback(
    (nodeType: string, nodeName: string) => {
      loadSubgraph(nodeType, nodeName, true);
    },
    [loadSubgraph]
  );

  return (
    <div className="flex h-[calc(100vh-64px)] flex-col gap-3 bg-surface-container/35 px-3 pb-3 pt-2 md:px-5 md:pb-5">
      {/* 搜索栏 */}
      <KGSearchBar onSelect={handleSearchSelect} />

      {/* 返回按钮 - 点击节点后显示 */}
      {selectedNode && (
        <button
          onClick={() => {
            if (history.length > 0) {
              const prev = history[history.length - 1];
              setHistory((h) => h.slice(0, -1));
              setNodes(prev.nodes);
              setEdges(prev.edges);
              setSelectedNode(prev.selectedNode);
            } else {
              setSelectedNode(null);
              setNodes([]);
              setEdges([]);
            }
          }}
          className="flex self-start items-center gap-1.5 rounded-xl border border-outline-variant/10 bg-surface-container-lowest px-3 py-1.5 text-sm text-on-surface shadow-sm transition-colors hover:bg-surface-container"
        >
          <span className="material-symbols-outlined text-base">arrow_back</span>
          <span>{history.length > 0 ? t("返回上一级", "Go Back") : t("返回", "Back")}</span>
        </button>
      )}

      {/* 主内容区 */}
      <div className="flex-1 flex gap-4 min-h-0 relative">
        {/* 图谱区域 */}
        <div className="relative flex-1 overflow-hidden rounded-3xl border border-outline-variant/15 bg-surface-container-lowest shadow-sm">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface/60">
              <div className="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}
          {nodes.length > 0 ? (
            <>
              <KnowledgeGraph
                initialNodes={nodes}
                initialEdges={edges}
                onNodeClick={handleNodeClick}
              />
              {/* 节点颜色图例 */}
              <div className="absolute bottom-3 right-3 z-10 bg-surface-container-lowest/90 backdrop-blur-sm rounded-xl border border-outline/20 px-3 py-2 space-y-1">
                {[
                  { type: "disease", label: t("疾病", "Disease") },
                  { type: "symptom", label: t("症状", "Symptom") },
                  { type: "drug", label: t("药物", "Drug") },
                  { type: "food", label: t("食物", "Food") },
                  { type: "check", label: t("检查", "Check") },
                  { type: "department", label: t("科室", "Department") },
                ].map((item) => (
                  <div key={item.type} className="flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{ backgroundColor: NODE_COLORS[item.type] }}
                    />
                    <span className="text-xs text-on-surface-variant whitespace-nowrap">{item.label}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-on-surface-variant">
              <span className="material-symbols-outlined text-6xl mb-4 opacity-30">account_tree</span>
              <p className="text-lg font-medium mb-1">{t("搜索疾病、症状或药物", "Search diseases, symptoms, or drugs")}</p>
              <p className="text-sm opacity-70">{t("输入关键词开始探索医学知识图谱", "Enter keywords to explore the medical knowledge graph")}</p>
            </div>
          )}
        </div>

        {/* 节点详情面板 - 移动端覆盖显示，桌面端侧边显示 */}
        {selectedNode && (
          <div className="w-80 flex-shrink-0 md:relative absolute md:inset-auto inset-0 z-10 bg-surface-container-low">
            <NodeDetailPanel
              nodeType={selectedNode.type}
              nodeName={selectedNode.name}
              data={selectedNode.data}
              onClose={() => setSelectedNode(null)}
              onNavigate={handleNodeClick}
            />
          </div>
        )}
      </div>
    </div>
  );
}
