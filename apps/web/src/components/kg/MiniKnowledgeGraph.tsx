"use client";

import { useState, useCallback, useEffect } from "react";
import { api } from "@/lib/api-client";
import KnowledgeGraph, { toFlowNodes, toFlowEdges, NODE_COLORS } from "./KnowledgeGraph";
import NodeDetailPanel from "./NodeDetailPanel";
import type { Node, Edge } from "@xyflow/react";

interface MiniKnowledgeGraphProps {
  symptoms?: string[];
  diseases?: string[];
  className?: string;
}

const NODE_TYPE_LABELS: Record<string, string> = {
  disease: "疾病",
  symptom: "症状",
  drug: "药物",
  food: "食物",
  check: "检查",
  department: "科室",
};

function NodeLegend() {
  return (
    <div className="absolute bottom-3 right-3 z-10 bg-[#1a1a2e]/90 backdrop-blur-sm rounded-lg px-3 py-2 border border-white/10">
      <p className="text-[10px] text-white/50 mb-1.5">节点类型</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
            <span className="text-[10px] text-white/70">{NODE_TYPE_LABELS[type] || type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MiniKnowledgeGraph({ symptoms = [], diseases = [], className = "" }: MiniKnowledgeGraphProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeType, setSelectedNodeType] = useState<string | null>(null);
  const [selectedNodeName, setSelectedNodeName] = useState<string | null>(null);
  const [nodeDetail, setNodeDetail] = useState<Record<string, unknown> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadGraph = useCallback(async () => {
    if (symptoms.length === 0 && diseases.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.kgConsultationContext(symptoms.join(","), diseases.join(","));
      setNodes(toFlowNodes(data.nodes));
      setEdges(toFlowEdges(data.edges));
    } catch {
      setError("加载知识图谱失败");
    } finally {
      setLoading(false);
    }
  }, [symptoms, diseases]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadGraph(), 0);
    return () => window.clearTimeout(timer);
  }, [loadGraph]);

  const handleNodeClick = useCallback(async (nodeType: string, nodeName: string) => {
    setSelectedNodeType(nodeType);
    setSelectedNodeName(nodeName);
    setDetailLoading(true);
    setNodeDetail(null);
    try {
      const detail = await api.kgNodeDetail(nodeType, nodeName);
      // API 返回 { type, name, data }，NodeDetailPanel 需要 data 字段
      setNodeDetail(detail?.data || detail);
    } catch {
      setNodeDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedNodeType(null);
    setSelectedNodeName(null);
    setNodeDetail(null);
  }, []);

  if (symptoms.length === 0 && diseases.length === 0) return null;

  // 全屏模式
  if (expanded) {
    return (
      <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex">
        {/* 图谱区域 */}
        <div className="flex-1 relative">
          <div className="absolute top-3 left-3 z-10 flex items-center gap-2">
            <button
              onClick={() => setExpanded(false)}
              className="px-3 py-1.5 rounded-lg bg-surface-container-lowest/90 backdrop-blur-sm text-sm text-on-surface hover:bg-surface-container transition-colors flex items-center gap-1.5"
            >
              <span className="material-symbols-outlined text-[18px]">fullscreen_exit</span>
              收起
            </button>
            <button
              onClick={loadGraph}
              className="px-3 py-1.5 rounded-lg bg-surface-container-lowest/90 backdrop-blur-sm text-sm text-on-surface hover:bg-surface-container transition-colors flex items-center gap-1.5"
            >
              <span className="material-symbols-outlined text-[18px]">refresh</span>
              刷新
            </button>
            {nodes.length > 0 && (
              <span className="text-xs px-2 py-1 rounded-full bg-amber-400/20 text-amber-400">
                {nodes.length} 节点
              </span>
            )}
          </div>
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <>
              <KnowledgeGraph
                initialNodes={nodes}
                initialEdges={edges}
                fitView
                onNodeClick={handleNodeClick}
              />
              <NodeLegend />
            </>
          )}
        </div>
        {/* 详情面板 */}
        {selectedNodeType && selectedNodeName && (
          <div className="w-80 flex-shrink-0">
            {detailLoading ? (
              <div className="h-full flex items-center justify-center bg-surface-container-low">
                <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (
              <NodeDetailPanel
                nodeType={selectedNodeType}
                nodeName={selectedNodeName}
                data={nodeDetail}
                onClose={handleCloseDetail}
              />
            )}
          </div>
        )}
      </div>
    );
  }

  // 内嵌模式
  return (
    <div className={`rounded-xl border border-outline/20 bg-[#1a1a2e] overflow-hidden ${className}`}>
      {/* 标题栏 */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#16162a] border-b border-white/10">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-amber-400 text-lg">account_tree</span>
          <span className="text-sm font-medium text-white">相关知识图谱</span>
          {nodes.length > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-400/20 text-amber-400">
              {nodes.length} 节点
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded(true)}
            className="p-1 rounded hover:bg-white/10 transition-colors"
            title="全屏展开"
          >
            <span className="material-symbols-outlined text-base text-white/60">fullscreen</span>
          </button>
          <button
            onClick={loadGraph}
            className="p-1 rounded hover:bg-white/10 transition-colors"
            title="刷新"
          >
            <span className="material-symbols-outlined text-base text-white/60">refresh</span>
          </button>
        </div>
      </div>

      {/* 图谱区域 */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <div className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : error ? (
        <div className="flex items-center justify-center h-40 text-sm text-white/60">{error}</div>
      ) : nodes.length > 0 ? (
        <div className="h-64 relative">
          <KnowledgeGraph
            initialNodes={nodes}
            initialEdges={edges}
            fitView
            onNodeClick={handleNodeClick}
          />
          <NodeLegend />
        </div>
      ) : (
        <div className="flex items-center justify-center h-40 text-sm text-white/60">
          暂无相关图谱数据
        </div>
      )}

      {/* 内嵌节点详情（点击节点时在图谱下方显示） */}
      {selectedNodeType && selectedNodeName && !expanded && (
        <div className="border-t border-white/10 bg-[#16162a] max-h-48 overflow-y-auto">
          {detailLoading ? (
            <div className="flex items-center justify-center py-4">
              <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : nodeDetail ? (
            <div className="p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-amber-400/20 text-amber-400">{selectedNodeType}</span>
                  <span className="text-sm font-medium text-white">{selectedNodeName}</span>
                </div>
                <button onClick={handleCloseDetail} className="p-0.5 rounded hover:bg-white/10">
                  <span className="material-symbols-outlined text-sm text-white/60">close</span>
                </button>
              </div>
              <p className="text-xs text-white/60 line-clamp-3">
                {(nodeDetail.desc as string) || (nodeDetail.cause as string) || JSON.stringify(nodeDetail).slice(0, 200)}
              </p>
              <button
                onClick={() => setExpanded(true)}
                className="mt-2 text-xs text-amber-400 hover:text-amber-300 transition-colors"
              >
                全屏查看详情 →
              </button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
