"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import {
  Background, BaseEdge, Controls, EdgeLabelRenderer, getSmoothStepPath, MarkerType,
  Position, ReactFlow, type Edge, type EdgeProps, type Node,
} from "@xyflow/react";
import ELK from "elkjs/lib/elk.bundled.js";
import { evidenceTitle, label, type Schema } from "./api";
import "@xyflow/react/dist/style.css";

type Branch = Schema["EvidenceBranch"];

function FlowEdge(props: EdgeProps) {
  const [path, x, y] = getSmoothStepPath(props);
  return (
    <>
      <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} style={props.style} />
      <EdgeLabelRenderer>
        <span className="evidence-edge-label" style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }}>
          {props.label}
        </span>
      </EdgeLabelRenderer>
      {props.selected && (
        <circle className="evidence-particle" r={4} fill="#2274ff" aria-hidden="true">
          <animateMotion dur="2s" repeatCount="indefinite" path={path} />
        </circle>
      )}
    </>
  );
}

const edgeTypes = { evidence: FlowEdge };
const width = 222;
const height = 82;
const wideCanvas = "(min-width: 1001px)";

function watchCanvasWidth(change: () => void) {
  const media = window.matchMedia(wideCanvas);
  media.addEventListener("change", change);
  return () => media.removeEventListener("change", change);
}

function canvasIsWide() {
  return window.matchMedia(wideCanvas).matches;
}

function branchId(branch: Branch) {
  if (branch.evidence) return `source-${branch.evidence.revision_id}`;
  if (branch.related_claim) return `claim-${branch.related_claim.claim.id}`;
  return null;
}

function branchTitle(branch: Branch) {
  const source = branch.evidence;
  if (!source) return branch.related_claim?.claim.statement ?? "Related claim";
  const issue = /^https:\/\/github\.com\/[^/]+\/[^/]+\/issues\/(\d+)$/.exec(source.reference);
  if (issue) return `GitHub Issue #${issue[1]}`;
  return evidenceTitle(source.original_id, source.excerpt);
}

export function EvidenceGraph({ tree, large = false, renderDetails }: {
  tree: Schema["EvidenceTree"];
  large?: boolean;
  renderDetails?: (branches: Branch[]) => React.ReactNode;
}) {
  const [layout, setLayout] = useState<{ key: string; nodes: Node[]; failed?: boolean }>();
  const [selected, setSelected] = useState("claim");
  const [expanded, setExpanded] = useState(true);
  const [filter, setFilter] = useState("");
  const [reset, setReset] = useState(0);
  const wide = useSyncExternalStore(watchCanvasWidth, canvasIsWide, () => false);
  const horizontal = large && wide;
  const relationships = useMemo(() => {
    const unique = new Map<string, Edge>();
    for (const branch of tree.branches) {
      const id = branchId(branch);
      const relation = branch.evidence?.relation ?? branch.related_claim?.relation;
      if (!id || !relation) continue;
      const outgoing = branch.related_claim?.direction === "outgoing";
      const source = outgoing ? "claim" : id;
      const target = outgoing ? id : "claim";
      const key = `${source}:${relation}:${target}`;
      unique.set(key, {
        id: key, source, target, type: "evidence", label: label(relation),
        markerEnd: { type: MarkerType.ArrowClosed, color: "#506cb3" },
        style: { stroke: relation === "contradicts" ? "#ac4d45" : "#506cb3", strokeWidth: 1.7 },
      });
    }
    return Array.from(unique.values());
  }, [tree.branches]);
  const edges = relationships.filter((edge) => expanded && (!filter || edge.label === filter));
  const visible = new Set(edges.flatMap(({ source, target }) => [source, target]));
  const branches = useMemo(() => {
    const unique = new Map<string, Branch>();
    for (const branch of tree.branches) {
      const id = branchId(branch);
      if (id && !unique.has(id)) unique.set(id, branch);
    }
    return [...unique];
  }, [tree.branches]);
  const layoutKey = `${tree.root.revision_id}:${horizontal}:${branches.map(([id]) => id).join(",")}`;

  useEffect(() => {
    let active = true;
    const elk = new ELK();
    const ids = ["claim", ...branches.map(([id]) => id)];
    void elk.layout({
      id: "evidence",
      layoutOptions: {
        "elk.algorithm": "layered", "elk.direction": horizontal ? "RIGHT" : "DOWN",
        "elk.spacing.nodeNode": "30", "elk.layered.spacing.nodeNodeBetweenLayers": "100",
      },
      children: ids.map((id) => ({ id, width, height })),
      edges: ids.slice(1).map((id) => ({ id, sources: ["claim"], targets: [id] })),
    }).then((result) => {
      if (!active) return;
      const nodes = (result.children ?? []).map((node): Node => {
        const branch = branches.find(([id]) => id === node.id)?.[1];
        const title = branch ? branchTitle(branch) : tree.root.statement;
        const type = branch?.evidence
          ? (branch.evidence.provider === "manual" ? "Manual summary" : "Source snapshot")
          : branch ? label(branch.related_claim?.claim.kind ?? "claim") : label(tree.root.kind);
        const side = horizontal
          ? (branch ? Position.Left : Position.Right)
          : (branch ? Position.Top : Position.Bottom);
        return {
          id: node.id, ariaLabel: `${type}: ${title}`,
          data: { label: <><small>{type}</small><strong>{title}</strong></> },
          position: { x: node.x ?? 0, y: node.y ?? 0 },
          style: { width, height }, className: branch?.evidence ? "source-node" : "claim-node",
          sourcePosition: side, targetPosition: side,
        };
      });
      setLayout({ key: layoutKey, nodes });
    }).catch(() => { if (active) setLayout({ key: layoutKey, nodes: [], failed: true }); });
    return () => { active = false; };
  }, [branches, horizontal, layoutKey, tree.root.kind, tree.root.statement]);

  if (layout?.key !== layoutKey) return <p role="status">Laying out evidence…</p>;
  if (layout.failed) return <p>The diagram is unavailable. Use the evidence outline below.</p>;
  const active = visible.has(selected) ? selected : "claim";
  const selectedBranches = tree.branches.filter((branch) => branchId(branch) === active);
  return (
    <div className={`evidence-graph-layout ${large ? "is-large" : ""}`}>
      <section className="flow" aria-label="Evidence graph">
        <div className="row">
          <button className="button button-quiet" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
            {expanded ? "Collapse branches" : "Expand branches"}
          </button>
          {large && <>
            <button className="button button-quiet" onClick={() => { setSelected("claim"); setExpanded(true); setFilter(""); setReset(reset + 1); }}>Reset view</button>
            <select aria-label="Relationship filter" value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="">All relationships</option>
              {[...new Set(relationships.map((edge) => String(edge.label)))].map((relation) => <option key={relation}>{relation}</option>)}
            </select>
          </>}
        </div>
        <div className="evidence-diagram" aria-label="Evidence diagram">
          <ReactFlow
            key={`${layoutKey}:${expanded}:${filter}:${reset}`}
            nodes={layout.nodes.filter((node) => node.id === "claim" || visible.has(node.id)).map((node) => ({ ...node, selected: node.id === active }))}
            edges={edges.map((edge) => ({ ...edge, selected: active !== "claim" && [edge.source, edge.target].includes(active) }))}
            edgeTypes={edgeTypes}
            onNodeClick={(_, node) => setSelected(node.id)}
            onNodesChange={(changes) => {
              for (const change of changes) {
                if (change.type === "select" && change.selected) setSelected(change.id);
              }
            }}
            nodesDraggable={false}
            nodesConnectable={false}
            zoomOnScroll={false}
            fitView
            fitViewOptions={{ padding: 0.16, maxZoom: 1.05 }}
            minZoom={0.12}
          >
            <Controls showInteractive={false} />
            <Background gap={22} />
          </ReactFlow>
        </div>
      </section>
      {renderDetails?.(selectedBranches)}
    </div>
  );
}
