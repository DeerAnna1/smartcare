"use client";

import { useCallback, useMemo, useRef, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import type { Node, Edge } from "@xyflow/react";
import type { ForceGraphMethods } from "react-force-graph-2d";

// 必须用 d3-force-3d（force-graph 内部使用的模块），不能用 d3-force
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { forceCollide } = require("d3-force-3d");

// 该库的泛型 ref 声明不支持 callback ref，运行时支持；实例本身在下方保持强类型。
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D: any = dynamic(() => import("react-force-graph-2d"), { ssr: false });

// ---------- 节点类型配置 ----------

export const NODE_COLORS: Record<string, string> = {
  disease: "#f59e0b",
  symptom: "#ef4444",
  drug: "#8b5cf6",
  food: "#22c55e",
  check: "#3b82f6",
  department: "#6b7280",
};

// ---------- 组件 Props ----------

interface KnowledgeGraphProps {
  initialNodes?: Node[];
  initialEdges?: Edge[];
  onNodeClick?: (nodeType: string, nodeName: string) => void;
  className?: string;
  fitView?: boolean;
}

interface GraphNode {
  id: string;
  name: string;
  nodeType: string;
  color: string;
  val: number;
  x?: number;
  y?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  label: string;
  edgeType: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

type GraphInstance = ForceGraphMethods<GraphNode, GraphLink>;

const LINK_DISTANCE = 190;

/**
 * 节点是带文字的矩形，而 d3 的碰撞检测使用圆形半径。
 * 按标签长度估算外接圆，避免只按一个固定的小圆碰撞导致文字仍然重叠。
 */
function getCollisionRadius(node: GraphNode): number {
  const estimatedWidth = Math.min(160, Math.max(42, node.name.length * 10 + 20));
  return estimatedWidth / 2 + 24;
}

function configureGraphForces(graph: GraphInstance) {
  const linkForce = graph.d3Force("link");
  const chargeForce = graph.d3Force("charge");

  linkForce?.distance(LINK_DISTANCE).strength(0.35);
  chargeForce?.strength(-900).distanceMin(40).distanceMax(900);
  graph.d3Force(
    "collide",
    forceCollide((node: GraphNode) => getCollisionRadius(node))
      .strength(1)
      .iterations(3)
  );

  // 配置发生在默认 simulation 创建之后，必须重新加热才能让新参数参与布局。
  graph.d3ReheatSimulation();
}

export default function KnowledgeGraph({
  initialNodes = [],
  initialEdges = [],
  onNodeClick,
  className = "",
  fitView = true,
}: KnowledgeGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<GraphInstance | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // dynamic import 可能晚于首个 effect 完成。使用 callback ref 可保证实例一就绪就配置力。
  const setGraphRef = useCallback((graph: GraphInstance | null) => {
    fgRef.current = graph;
    if (graph) configureGraphForces(graph);
  }, []);

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: containerRef.current.offsetHeight,
        });
      }
    };
    updateDimensions();
    const observer = new ResizeObserver(updateDimensions);
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const graphData: GraphData = useMemo(() => {
    const nodes: GraphNode[] = initialNodes.map((n) => ({
      id: n.id,
      name: (n.data?.label as string) || n.id,
      nodeType: (n.data?.nodeType as string) || "disease",
      color: NODE_COLORS[(n.data?.nodeType as string) || "disease"] || "#6b7280",
      val: 1,
    }));
    const links: GraphLink[] = initialEdges.map((e) => ({
      source: e.source,
      target: e.target,
      label: (e.label as string) || "",
      edgeType: (e.type as string) || "",
    }));
    return { nodes, links };
  }, [initialNodes, initialEdges]);

  // react-force-graph 会在 graphData 变化时重建默认力，因此每次数据变化后重新配置。
  useEffect(() => {
    if (!fgRef.current) return;
    configureGraphForces(fgRef.current);
  }, [graphData]);

  // 数据或容器尺寸变化后先做一次适配；模拟结束时还会再次适配最终位置。
  useEffect(() => {
    if (fitView && fgRef.current && graphData.nodes.length > 0) {
      const timer = setTimeout(() => {
        fgRef.current?.zoomToFit(400, 80);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [fitView, graphData, dimensions]);

  const handleEngineStop = useCallback(() => {
    if (fitView) fgRef.current?.zoomToFit(400, 80);
  }, [fitView]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      if (onNodeClick) onNodeClick(node.nodeType, node.name);
    },
    [onNodeClick]
  );

  const nodeCanvasObject = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const x = node.x || 0;
    const y = node.y || 0;
    const label = node.name;
    const color = node.color;

    const fontSize = Math.max(6, 8 / globalScale);
    ctx.font = `bold ${fontSize}px 'PingFang SC', 'Microsoft YaHei', sans-serif`;
    const textWidth = ctx.measureText(label).width;
    const radius = node.nodeType === "disease" ? 11 : 9;

    // 所有节点统一使用圆形主体。
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fillStyle = color + "e6";
    ctx.fill();
    ctx.strokeStyle = "#ffffff80";
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // 标签放在圆形下方，避免长名称把节点视觉重新变成胶囊形。
    const labelY = y + radius + fontSize / 2 + 4;
    const labelPadding = 3;
    ctx.fillStyle = "#1a1a2ed9";
    ctx.fillRect(
      x - textWidth / 2 - labelPadding,
      labelY - fontSize / 2 - 1,
      textWidth + labelPadding * 2,
      fontSize + 2
    );
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#ffffff";
    ctx.fillText(label, x, labelY);
  }, []);

  const nodePointerAreaPaint = useCallback((node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
    const x = node.x || 0;
    const y = node.y || 0;
    const label = node.name || "";
    const fontSize = 8;
    ctx.font = `bold ${fontSize}px 'PingFang SC', 'Microsoft YaHei', sans-serif`;
    const textWidth = ctx.measureText(label).width;
    const radius = node.nodeType === "disease" ? 11 : 9;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, radius + 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillRect(x - textWidth / 2 - 3, y + radius + 3, textWidth + 6, fontSize + 4);
  }, []);

  const linkCanvasObject = useCallback((link: GraphLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const start = link.source as GraphNode;
    const end = link.target as GraphNode;
    if (!start || !end || typeof start !== "object" || typeof end !== "object") return;
    const sx = start.x || 0;
    const sy = start.y || 0;
    const ex = end.x || 0;
    const ey = end.y || 0;

    const midX = (sx + ex) / 2;
    const midY = (sy + ey) / 2;

    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(ex, ey);
    ctx.strokeStyle = "#ffffff15";
    ctx.lineWidth = 0.8;
    ctx.stroke();

    if (link.label) {
      const fontSize = Math.max(6, 8 / globalScale);
      ctx.font = `${fontSize}px 'PingFang SC', 'Microsoft YaHei', sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const textWidth = ctx.measureText(link.label).width;
      ctx.fillStyle = "#1a1a2ecc";
      ctx.fillRect(midX - textWidth / 2 - 2, midY - fontSize / 2 - 1, textWidth + 4, fontSize + 2);
      ctx.fillStyle = "#a8a29e";
      ctx.fillText(link.label, midX, midY);
    }
  }, []);

  if (graphData.nodes.length === 0) {
    return (
      <div className={`flex items-center justify-center h-full text-on-surface-variant ${className}`}>
        <div className="text-center">
          <span className="material-symbols-outlined text-6xl mb-4 opacity-30">account_tree</span>
          <p className="text-lg font-medium">暂无图谱数据</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={`w-full h-full bg-[#1a1a2e] rounded-xl overflow-hidden ${className}`}>
      {typeof window !== "undefined" && (
        <ForceGraph2D
          ref={setGraphRef}
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          nodeCanvasObject={nodeCanvasObject}
          nodePointerAreaPaint={nodePointerAreaPaint}
          linkCanvasObject={linkCanvasObject}
          onNodeClick={handleNodeClick}
          onEngineStop={handleEngineStop}
          backgroundColor="#1a1a2e"
          linkDirectionalParticles={1}
          linkDirectionalParticleWidth={1.5}
          linkDirectionalParticleColor={() => "#f59e0b60"}
          linkDirectionalParticleSpeed={0.002}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.4}
          warmupTicks={150}
          cooldownTicks={500}
          enableNodeDrag={true}
          enableZoomPanRotate={true}
          cooldownTime={8000}
        />
      )}
    </div>
  );
}

// ---------- 工具函数 ----------

export function toFlowNodes(apiNodes: { id: string; type: string; label: string; data?: Record<string, unknown> }[]): Node[] {
  return apiNodes.map((n) => ({
    id: n.id,
    type: "kgNode",
    position: { x: 0, y: 0 },
    data: { label: n.label, nodeType: n.type, ...n.data },
  }));
}

export function toFlowEdges(apiEdges: { id: string; source: string; target: string; label: string; type: string }[]): Edge[] {
  return apiEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label,
    type: "smoothstep",
    animated: false,
    style: { stroke: "#a8a29e" },
    labelStyle: { fontSize: 11, fill: "#78716c" },
    labelBgStyle: { fill: "#fafaf9", fillOpacity: 0.9 },
    labelBgPadding: [4, 2] as [number, number],
    labelBgBorderRadius: 4,
  }));
}
