import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "../api.js";

export default function MessageGraph({ refreshKey }) {
  const svgRef = useRef(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });

  const fetchGraph = useCallback(async () => {
    try {
      const data = await api.getMessageGraph();
      setGraph(data);
    } catch (e) {
      console.error("Failed to load message graph", e);
    }
  }, []);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph, refreshKey]);

  if (!graph.nodes.length) {
    return (
      <div className="empty-state" style={{ height: 220 }}>
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" strokeWidth="1.5">
          <circle cx="5" cy="12" r="3" /><circle cx="19" cy="5" r="3" /><circle cx="19" cy="19" r="3" />
          <line x1="8" y1="11" x2="16" y2="6" /><line x1="8" y1="13" x2="16" y2="18" />
        </svg>
        <span>No messages yet</span>
      </div>
    );
  }

  return (
    <svg
      ref={svgRef}
      className="message-graph"
      viewBox="0 0 400 220"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="var(--border)" />
        </marker>
      </defs>

      {graph.edges.map((edge, i) => {
        const src = graph.nodes.find((n) => n.id === edge.from);
        const dst = graph.nodes.find((n) => n.id === edge.to);
        if (!src || !dst) return null;
        const { x: x1, y: y1 } = getNodePos(src.id, graph.nodes);
        const { x: x2, y: y2 } = getNodePos(dst.id, graph.nodes);
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const thickness = Math.min(1 + edge.count * 0.5, 5);

        return (
          <g key={i}>
            {/* Edge line */}
            <line
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="var(--border)"
              strokeWidth={thickness}
              markerEnd="url(#arrowhead)"
              opacity={0.6}
            />
            {/* Edge label */}
            <text
              x={mx} y={my - 4}
              textAnchor="middle"
              fontSize={10}
              fill="var(--text-dim)"
            >
              {edge.count}
            </text>
          </g>
        );
      })}

      {graph.nodes.map((node) => {
        const { x, y } = getNodePos(node.id, graph.nodes);
        const outEdges = graph.edges.filter((e) => e.from === node.id).length;
        const inEdges = graph.edges.filter((e) => e.to === node.id).length;
        const r = Math.max(14, Math.min(22, 14 + outEdges * 2));

        return (
          <g
            key={node.id}
            className="graph-node"
            transform={`translate(${x}, ${y})`}
            onClick={() => {}}
          >
            <circle r={r} fill="var(--surface2)" stroke="var(--accent)" strokeWidth={1.5} />
            <text
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={11}
              fontWeight={600}
              fill="var(--text)"
            >
              {node.id.slice(0, 2).toUpperCase()}
            </text>
            <title>{node.id} ({node.type})</title>
          </g>
        );
      })}
    </svg>
  );
}

// Simple deterministic layout — circular with name-based offset
function getNodePos(id, nodes) {
  const idx = nodes.findIndex((n) => n.id === id);
  const n = nodes.length;
  if (n <= 3) {
    const positions = [
      [200, 110],
      [120, 70],
      [280, 70],
    ];
    return { x: positions[idx % positions.length][0], y: positions[idx % positions.length][1] };
  }
  const angle = (idx / n) * 2 * Math.PI - Math.PI / 2;
  const cx = 200, cy = 110, rx = 130, ry = 90;
  return {
    x: cx + rx * Math.cos(angle),
    y: cy + ry * Math.sin(angle),
  };
}
