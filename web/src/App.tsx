import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { CoupFEBackend } from "./backend/interface";
import {
  formatDateTime,
  formatDuration,
  formatQuantity,
  formatUncertainty,
  runDurationSeconds,
  selectActiveDecision,
  selectActiveDesign,
  selectCandidateComparison,
  selectEvidenceByIds,
  selectEvidenceIntegrity,
  selectEvidenceSummary,
  selectGateEvaluations,
  selectLastCompletedRun,
  selectLatestRun,
  selectLatestSuccessfulRun,
  selectMetric,
  selectModel,
  selectModelAdequacy,
  selectPreferredCandidate,
  selectStackThicknessMicrometers,
  selectTemperatureField,
  selectWorkflow,
  uncertaintyPercent,
} from "./domain/selectors";
import type {
  ApprovedWorkflowDefinition,
  GenericMetricResult,
  MetricKey,
  MetricResult,
  ModelFidelity,
  PackageLayer,
  ProjectSnapshot,
  RunRecord,
} from "./domain/types";
import { useWorkbench } from "./hooks/use-workbench";

type ViewId = "overview" | "geometry" | "models" | "runs" | "compare" | "evidence";

type IconName =
  | ViewId
  | "shield"
  | "clock"
  | "thermometer"
  | "warpage"
  | "margin"
  | "runtime"
  | "check"
  | "chevron"
  | "menu"
  | "close"
  | "info"
  | "external"
  | "layers";

const navItems: Array<{ id: ViewId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "geometry", label: "Geometry" },
  { id: "models", label: "Models" },
  { id: "runs", label: "Runs" },
  { id: "compare", label: "Compare" },
  { id: "evidence", label: "Evidence" },
];

const metricIcons: Record<MetricKey, IconName> = {
  temperature: "thermometer",
  warpage: "warpage",
  margin: "margin",
  runtime: "runtime",
};

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  const paths: Record<IconName, ReactNode> = {
    overview: <><path d="M3 10.8 12 3l9 7.8" /><path d="M5 9.6V21h14V9.6" /><path d="M9 21v-7h6v7" /></>,
    geometry: <><path d="m12 2 8 4.5v11L12 22l-8-4.5v-11L12 2Z" /><path d="m4.2 6.7 7.8 4.5 7.8-4.5M12 11.2V22" /></>,
    models: <><circle cx="12" cy="4" r="2" /><circle cx="5" cy="20" r="2" /><circle cx="19" cy="20" r="2" /><path d="M12 6v5M5 18v-4h14v4M12 11v3" /></>,
    runs: <><circle cx="12" cy="12" r="9" /><path d="m10 8 6 4-6 4V8Z" /></>,
    compare: <><path d="M5 20V10M10 20V4M15 20v-7M20 20V7" /><path d="M3 20h19" /></>,
    evidence: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h4" /></>,
    shield: <><path d="M12 3 5 6v5c0 4.8 2.8 8.1 7 10 4.2-1.9 7-5.2 7-10V6l-7-3Z" /><path d="m9.2 12 1.8 1.8 4-4" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></>,
    thermometer: <><path d="M9 4a3 3 0 0 1 6 0v9.1a5 5 0 1 1-6 0V4Z" /><path d="M12 6v9" /></>,
    warpage: <><path d="M3 10c4 4 14 4 18 0" /><path d="M4 17h2M9 17h2M14 17h2M19 17h1" /></>,
    margin: <><path d="M12 3 5 6v5c0 4.8 2.8 8.1 7 10 4.2-1.9 7-5.2 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
    runtime: <><circle cx="12" cy="12" r="9" /><path d="M12 6v6h5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 5 7 7-7 7" />,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
    external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6" /></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function worstAssessedMetric(run: RunRecord | undefined): MetricResult | undefined {
  return (run?.output?.metrics ?? [])
    .filter((metric) => metric.key !== "runtime" && metric.uncertainty?.kind === "validation-error")
    .sort((a, b) => (uncertaintyPercent(b) ?? 0) - (uncertaintyPercent(a) ?? 0))[0];
}

function formatGenericMetric(metric: GenericMetricResult): string {
  if (metric.unit === "count" || metric.unit === "devices") {
    const value = Math.round(metric.value).toLocaleString();
    return metric.unit === "devices" ? `${value} devices` : value;
  }
  if (metric.unit === "s") return `${metric.value.toFixed(2)} s`;
  return `${metric.value.toPrecision(5)}${metric.unit === "1" ? "" : ` ${metric.unit}`}`;
}

function layerContent(layer: PackageLayer, fieldHotspotComponentId?: string) {
  if (layer.id === "die") {
    return fieldHotspotComponentId === layer.id ? <span className="hotspot-anchor" /> : null;
  }
  if (layer.id === "bumps") {
    return <span className="repeater bump-repeater">{Array.from({ length: 20 }, (_, index) => <i key={index} />)}</span>;
  }
  if (layer.id === "interposer") {
    return (
      <span className="interposer-features">
        <span className="rdl-lines"><i /><i /><i /><i /></span>
        <span className="repeater tsv-repeater">{Array.from({ length: 14 }, (_, index) => <i key={index} />)}</span>
      </span>
    );
  }
  if (layer.id === "substrate") {
    return <span className="substrate-traces"><i /><i /><i /><i /><i /></span>;
  }
  if (layer.id === "sink") {
    return <span className="repeater fin-repeater">{Array.from({ length: 16 }, (_, index) => <i key={index} />)}</span>;
  }
  return null;
}

function PackageDiagram({
  snapshot,
  run,
  selectedLayerId,
  onSelectLayer,
  expanded = false,
}: {
  snapshot: ProjectSnapshot;
  run: RunRecord | undefined;
  selectedLayerId: string;
  onSelectLayer: (id: string) => void;
  expanded?: boolean;
}) {
  const selectedLayer = snapshot.layers.find((layer) => layer.id === selectedLayerId) ?? snapshot.layers[0];
  const field = selectTemperatureField(run);
  const stackThickness = selectStackThicknessMicrometers(snapshot);

  return (
    <section className={`viewer-panel ${expanded ? "viewer-panel-expanded" : ""}`}>
      <div className="panel-heading">
        <div><p className="eyebrow">Geometry + field</p><h2>Package cross-section</h2></div>
        <div className={`overlay-label ${field ? "" : "overlay-empty"}`}>
          <span className="status-dot" />
          {field ? `${field.label} overlay · ${field.unit}` : "No completed field for this model"}
        </div>
      </div>

      <div className="viewer-canvas">
        <div className="viewer-meta"><span>ORTHOGRAPHIC</span><span>X–Z SECTION</span></div>
        <div className="package-layout">
          <div className="package-stack">
            {snapshot.layers.map((layer) => (
              <div className={`package-row package-row-${layer.id}`} key={layer.id}>
                <button className="layer-label" onClick={() => onSelectLayer(layer.id)} aria-pressed={selectedLayer?.id === layer.id}>
                  {layer.name}<span />
                </button>
                <button
                  className={`package-layer layer-${layer.id} ${selectedLayer?.id === layer.id ? "is-selected" : ""}`}
                  onClick={() => onSelectLayer(layer.id)}
                  aria-label={`Inspect ${layer.name}`}
                  aria-pressed={selectedLayer?.id === layer.id}
                >
                  {field?.hotspotComponentId === layer.id && <span className="hotspot-tag">{field.hotspotValue.toFixed(1)} {field.unit}</span>}
                  {layerContent(layer, field?.hotspotComponentId)}
                </button>
              </div>
            ))}
          </div>
          {field && (
            <aside className="temperature-legend" aria-label={`${field.label} legend`}>
              <span>{field.maximum.toFixed(1)}</span><i /><span>{field.minimum.toFixed(1)}</span>
            </aside>
          )}
        </div>

        <div className="viewer-footer">
          <div className="axis-glyph" aria-label="X Y Z axis"><b>Z</b><span className="axis-z" /><b>Y</b><span className="axis-y" /><b>X</b><span className="axis-x" /></div>
          <div className="selected-layer-summary">
            <span>Selected</span><strong>{selectedLayer?.name ?? "No layer"}</strong>
            <span>{selectedLayer ? `${selectedLayer.material} · ${formatQuantity(selectedLayer.thickness)}` : "—"}</span>
          </div>
          <div className="scale-bar"><span>Stack</span><i /><span>{formatQuantity({ value: stackThickness / 1000, unit: "mm" }, 2)}</span></div>
        </div>
      </div>
    </section>
  );
}

function FidelityPanel({ snapshot, selected, onSelect }: { snapshot: ProjectSnapshot; selected: ModelFidelity; onSelect: (model: ModelFidelity) => void }) {
  const adequacy = selectModelAdequacy(snapshot, selected);
  const selectedModel = selectModel(snapshot, selected);
  const passCount = adequacy.gates.filter((gate) => gate.status === "pass").length;
  return (
    <section className="fidelity-panel">
      <div className="panel-heading compact-heading">
        <div><p className="eyebrow">Decision policy</p><h2>Model fidelity</h2></div>
        <span className={`gate-state gate-${adequacy.status}`}><Icon name={adequacy.status === "adequate" ? "check" : "info"} size={16} />{adequacy.label}</span>
      </div>
      <div className="fidelity-list">
        {snapshot.models.map((model, index) => {
          const run = selectLatestSuccessfulRun(snapshot, model.id);
          const worst = worstAssessedMetric(run);
          return (
            <button key={model.id} className={`fidelity-option ${selected === model.id ? "is-selected" : ""}`} onClick={() => onSelect(model.id)} aria-pressed={selected === model.id}>
              <span className="fidelity-index">{index + 1}</span>
              <span className="fidelity-copy"><strong>{model.shortName}</strong><small>{model.description}</small></span>
              <span className="fidelity-stats"><b>{worst ? `max ±${uncertaintyPercent(worst)}%` : "not assessed"}</b><small>{formatDuration(model.expectedRuntimeSeconds)}</small></span>
            </button>
          );
        })}
      </div>
      <div className="selection-summary">
        <div className={`gate-count gate-${adequacy.status}`}><span>{passCount}/{adequacy.gates.length}</span></div>
        <div><span>Live policy gates pass</span><strong>{selectedModel?.name ?? "Unknown model"}</strong></div>
      </div>
    </section>
  );
}

function MetricCards({ metrics, onInspect }: { metrics: MetricResult[]; onInspect: (key: MetricKey) => void }) {
  if (!metrics.length) return <section className="empty-panel">No completed metrics are available for this model.</section>;
  return (
    <section className="metrics-grid" aria-label="Selected model metrics">
      {metrics.map((metric) => (
        <button className="metric-card" key={metric.key} onClick={() => onInspect(metric.key)}>
          <span className={`metric-icon metric-${metric.assessment}`}><Icon name={metricIcons[metric.key]} size={26} /></span>
          <span className="metric-copy"><span>{metric.label}</span><strong>{formatQuantity(metric.quantity)}</strong></span>
          <span className="metric-evidence">Evidence <Icon name="chevron" size={14} /></span>
        </button>
      ))}
    </section>
  );
}

function DecisionPanel({ snapshot, selected, run }: { snapshot: ProjectSnapshot; selected: ModelFidelity; run: RunRecord | undefined }) {
  const adequacy = selectModelAdequacy(snapshot, selected);
  const model = selectModel(snapshot, selected);
  const decision = selectActiveDecision(snapshot);
  const passCount = adequacy.gates.filter((gate) => gate.status === "pass").length;
  const policySelected = decision?.selectedModelId === selected;
  return (
    <section className={`decision-panel ${adequacy.status === "adequate" ? "decision-recommended" : ""}`}>
      <div className="decision-badge"><Icon name={adequacy.status === "adequate" ? "shield" : "info"} size={19} /></div>
      <div className="decision-copy">
        <span>{policySelected ? `Policy-selected · ${decision?.status}` : "Alternative fidelity inspected"}</span>
        <strong>{adequacy.label}</strong>
        <p>{run?.output?.nextAction ?? adequacy.summary}</p>
      </div>
      <dl><div><dt>Gates passed</dt><dd>{passCount} / {adequacy.gates.length}</dd></div><div><dt>Expected cost</dt><dd>{model?.costClass.replace("-", " ") ?? "Unknown"}</dd></div></dl>
    </section>
  );
}

function WorkflowPanel({ snapshot, selected }: { snapshot: ProjectSnapshot; selected: ModelFidelity }) {
  const workflow = selectWorkflow(snapshot, selected);
  const latest = selectLatestRun(snapshot, selected);
  const running = latest?.status === "queued" || latest?.status === "running";
  return (
    <section className="workflow-panel">
      <div className="workflow-title">
        <div><p className="eyebrow">Execution</p><h2>Workflow status</h2></div>
        <span className={`run-state ${running ? "is-running" : ""}`}><i />{running ? latest.progress?.message ?? latest.status : `${workflow.readyCount} of ${workflow.stages.length} stages ready`}</span>
      </div>
      <div className="workflow-stages">
        {workflow.stages.map((stage, index) => (
          <div className={`workflow-stage stage-${stage.state}`} key={stage.id}>
            <span className="stage-node">{stage.state === "complete" ? <Icon name="check" size={17} /> : index + 1}</span>
            <div><strong>{stage.name}</strong><span>{stage.summary}</span><small>{stage.timestamp ?? "Waiting for upstream evidence"}</small></div>
            {index < workflow.stages.length - 1 && <i className="stage-connector" />}
          </div>
        ))}
      </div>
    </section>
  );
}

function OverviewView({ snapshot, selectedModel, setSelectedModel, selectedLayer, setSelectedLayer, onInspectMetric }: {
  snapshot: ProjectSnapshot;
  selectedModel: ModelFidelity;
  setSelectedModel: (model: ModelFidelity) => void;
  selectedLayer: string;
  setSelectedLayer: (layer: string) => void;
  onInspectMetric: (metric: MetricKey) => void;
}) {
  const run = selectLatestSuccessfulRun(snapshot, selectedModel);
  return <>
    <div className="overview-grid">
      <PackageDiagram snapshot={snapshot} run={run} selectedLayerId={selectedLayer} onSelectLayer={setSelectedLayer} />
      <FidelityPanel snapshot={snapshot} selected={selectedModel} onSelect={setSelectedModel} />
    </div>
    <MetricCards metrics={run?.output?.metrics ?? []} onInspect={onInspectMetric} />
    <DecisionPanel snapshot={snapshot} selected={selectedModel} run={run} />
    <WorkflowPanel snapshot={snapshot} selected={selectedModel} />
  </>;
}

function GeometryView({ snapshot, selectedModel, selectedLayer, setSelectedLayer }: { snapshot: ProjectSnapshot; selectedModel: ModelFidelity; selectedLayer: string; setSelectedLayer: (layer: string) => void }) {
  const layer = snapshot.layers.find((item) => item.id === selectedLayer) ?? snapshot.layers[0];
  const run = selectLatestSuccessfulRun(snapshot, selectedModel);
  const field = selectTemperatureField(run);
  return (
    <div className="detail-layout">
      <PackageDiagram snapshot={snapshot} run={run} selectedLayerId={selectedLayer} onSelectLayer={setSelectedLayer} expanded />
      <aside className="inspector-panel">
        <div className="inspector-heading"><Icon name="layers" /><span>Layer inspector</span></div>
        <h2>{layer?.name ?? "No layer selected"}</h2><p>{layer?.role}</p>
        <dl className="inspector-list">
          <div><dt>Material</dt><dd>{layer?.material ?? "—"}</dd></div>
          <div><dt>Thickness</dt><dd>{layer ? formatQuantity(layer.thickness) : "—"}</dd></div>
          <div><dt>Embedded features</dt><dd>{layer?.embeddedFeatures?.map((feature) => feature.name).join(", ") || "None"}</dd></div>
          <div><dt>Displayed field</dt><dd>{field ? `${field.minimum.toFixed(1)}–${field.maximum.toFixed(1)} ${field.unit}` : "No completed field"}</dd></div>
          <div><dt>Source revision</dt><dd>{selectActiveDesign(snapshot)?.packageRevision ?? "Not recorded"}</dd></div>
        </dl>
        <div className="inspector-note"><Icon name="info" size={18} /><p>This is a derived sanity-check view. Authoritative solver geometry, mesh, and quantitative fields remain checksummed artifacts.</p></div>
        <div className="layer-index">{snapshot.layers.map((item) => <button key={item.id} className={item.id === layer?.id ? "is-active" : ""} onClick={() => setSelectedLayer(item.id)}><span />{item.name}<Icon name="chevron" size={14} /></button>)}</div>
      </aside>
    </div>
  );
}

function ModelsView({ snapshot, selectedModel, setSelectedModel }: { snapshot: ProjectSnapshot; selectedModel: ModelFidelity; setSelectedModel: (model: ModelFidelity) => void }) {
  const decision = selectActiveDecision(snapshot);
  const adequacy = selectModelAdequacy(snapshot, selectedModel);
  return (
    <div className="content-stack">
      <section className="page-intro"><div><p className="eyebrow">Fidelity management</p><h1>Choose the cheapest adequate model</h1><p>{decision ? `${decision.policyVersion} evaluates model validity, assessed error, reliability margin, and reduced/reference discrepancy.` : "No active decision policy is recorded."}</p></div><span className={`policy-status policy-${decision?.status ?? "missing"}`}><Icon name="shield" size={18} />{decision ? `${decision.status} policy` : "Policy unavailable"}</span></section>
      <section className="model-comparison">
        {snapshot.models.map((model, index) => {
          const isSelected = selectedModel === model.id;
          const run = selectLatestSuccessfulRun(snapshot, model.id);
          const worst = worstAssessedMetric(run);
          const modelAdequacy = selectModelAdequacy(snapshot, model.id);
          return (
            <button key={model.id} className={`model-card ${isSelected ? "is-selected" : ""}`} onClick={() => setSelectedModel(model.id)}>
              <span className="model-number">{String(index + 1).padStart(2, "0")}</span>
              <div className="model-card-heading"><div><span>{model.validityClass}</span><h2>{model.shortName}</h2></div>{isSelected && <i><Icon name="check" size={15} /></i>}</div>
              <p>{model.description}</p>
              <dl><div><dt>Worst assessed error</dt><dd>{worst ? `±${uncertaintyPercent(worst)}%` : "Not assessed"}</dd></div><div><dt>Expected runtime</dt><dd>{formatDuration(model.expectedRuntimeSeconds)}</dd></div><div><dt>Live decision</dt><dd>{modelAdequacy.status}</dd></div></dl>
              <div className="assumption-list"><span>Key assumptions</span>{model.assumptions.map((assumption) => <small key={assumption}><Icon name="check" size={13} />{assumption}</small>)}</div>
            </button>
          );
        })}
      </section>
      <section className="policy-grid">
        <article><div className="section-label"><Icon name="shield" size={18} /> Live gate evaluation</div><ul>{adequacy.gates.map((gate) => <li className={`gate-list-${gate.status}`} key={gate.id}><strong>{gate.label}: {gate.status}</strong><span>{gate.observed} · policy {gate.threshold}</span></li>)}</ul></article>
        <article className="trigger-card"><div className="section-label"><Icon name="info" size={18} /> Decision explanation</div><p className="policy-summary">{adequacy.summary}</p><ul>{adequacy.gates.filter((gate) => gate.status !== "pass").map((gate) => <li key={gate.id}>{gate.explanation}</li>)}</ul></article>
      </section>
    </div>
  );
}

function ApprovedWorkflowPanel({
  snapshot,
  workflow,
  onRun,
  disabled,
}: {
  snapshot: ProjectSnapshot;
  workflow: ApprovedWorkflowDefinition;
  onRun: () => void;
  disabled: boolean;
}) {
  const isDemo = snapshot.mode === "demo";
  const latest = snapshot.runs.find(
    (run) => run.workflowId === workflow.id && run.status === "succeeded",
  );
  return (
    <section className="approved-workflow-panel">
      <div className="approved-workflow-heading">
        <span className="dialog-icon"><Icon name="runs" size={22} /></span>
        <div><p className="eyebrow">{isDemo ? "Approved simulation contract" : "Server-approved workflow"}</p><h2>{workflow.name}</h2><code>{workflow.executorKey}</code></div>
        <button className="primary-action" onClick={onRun} disabled={disabled}>{isDemo ? "Review simulation" : "Review and run"} <Icon name="chevron" size={16} /></button>
      </div>
      <p>{isDemo ? "Browser simulation of the approved local workflow contract using reviewed, retained TSV evidence." : workflow.description}</p>
      {latest?.output?.genericMetrics?.length ? (
        <div className="generic-metric-grid">
          {latest.output.genericMetrics.map((metric) => (
            <article key={metric.key}><span>{metric.label}</span><strong>{formatGenericMetric(metric)}</strong></article>
          ))}
        </div>
      ) : (
        <div className="approved-workflow-empty">{isDemo ? "No simulation is recorded yet. The browser models lifecycle events and links reviewed, precomputed evidence." : "No local run is recorded yet. Connected mode executes the server allowlist."}</div>
      )}
      <div className="workflow-boundary"><Icon name="info" size={17} /><div><strong>Release validation: {workflow.releaseValidation ? "claimed" : "not claimed"}</strong><p>{workflow.claimBoundary}</p></div></div>
      <footer><span>{isDemo ? "Browser simulation: approved workflow ID" : "Browser request: workflow ID only"}</span><span>{isDemo ? "No solver executes; reviewed evidence is precomputed" : "Server owns driver, arguments, output root, and timeout"}</span></footer>
    </section>
  );
}

function RunsView({
  snapshot,
  onRunModel,
  onRunWorkflow,
  onCancel,
  activeRun,
}: {
  snapshot: ProjectSnapshot;
  onRunModel: () => void;
  onRunWorkflow: (workflowId: string) => void;
  onCancel: (runId: string) => void;
  activeRun: RunRecord | undefined;
}) {
  const isDemo = snapshot.mode === "demo";
  return (
    <div className="content-stack">
      <section className="page-intro"><div><p className="eyebrow">{isDemo ? "Browser simulation" : "Execution history"}</p><h1>{isDemo ? "Approved workflow simulation" : "Approved runs"}</h1><p>{isDemo ? "Public-mode records simulate the interface lifecycle and link only to reviewed, retained project artifacts." : "Successful connected executions retain outputs, stdout/stderr, source tree state, and artifact hashes."}</p></div>{snapshot.models.length > 0 && <button className="secondary-action" onClick={onRunModel}>New model analysis <Icon name="chevron" size={16} /></button>}</section>
      {snapshot.approvedWorkflows.map((workflow) => (
        <ApprovedWorkflowPanel
          snapshot={snapshot}
          workflow={workflow}
          onRun={() => onRunWorkflow(workflow.id)}
          disabled={Boolean(activeRun)}
          key={workflow.id}
        />
      ))}
      <section className="table-panel"><div className="table-heading"><h2>{isDemo ? "Simulated run history" : "Recent analyses"}</h2><span>{snapshot.runs.length} records</span></div><div className="data-table run-table">
        <div className="data-row data-header"><span>{isDemo ? "Simulation" : "Run"}</span><span>Target</span><span>Design revision</span><span>Started</span><span>Duration</span><span>Evidence</span></div>
        {snapshot.runs.map((run) => {
          const model = run.modelId ? selectModel(snapshot, run.modelId) : undefined;
          const workflow = snapshot.approvedWorkflows.find((item) => item.id === run.workflowId);
          const evidenceCount = selectEvidenceByIds(snapshot, run.output?.evidenceIds ?? []).length;
          const active = run.status === "queued" || run.status === "running";
          const cancellable = run.status === "queued" || (snapshot.mode === "demo" && run.status === "running");
          return <div className="data-row" key={run.id}><span><b className={`run-dot run-${run.status === "succeeded" ? "complete" : run.status}`} /><strong>{run.id}</strong></span><span>{workflow?.name ?? model?.shortName ?? "Unknown target"}</span><span>{run.input.designRevision}</span><span>{formatDateTime(run.startedAt ?? run.requestedAt)}</span><span>{active ? run.progress?.message ?? run.status : formatDuration(runDurationSeconds(run))}</span><span>{cancellable ? <button className="table-action" onClick={() => onCancel(run.id)}>Cancel</button> : active ? "Cannot cancel after start" : `${evidenceCount} linked`}</span></div>;
        })}
        {snapshot.runs.length === 0 && <div className="empty-panel">{isDemo ? "No simulated records have been created in this browser session." : "No run records have been created by this backend."}</div>}
      </div></section>
      <section className="provenance-strip"><Icon name="shield" size={20} /><div><strong>{snapshot.mode === "connected" ? "Current-process run index" : "Interface-only history"}</strong><span>{snapshot.mode === "connected" ? "Successful entries retain source revision and tree state, the regression-oracle hash, and checksummed output artifacts. The API index resets when the service restarts." : "The browser simulation does not create a solver manifest; linked TSV artifacts are precomputed repository records."}</span></div></section>
    </div>
  );
}

function WorkflowRunDialog({
  snapshot,
  workflowId,
  onClose,
  onConfirm,
  busy,
}: {
  snapshot: ProjectSnapshot;
  workflowId: string | null;
  onClose: () => void;
  onConfirm: () => void;
  busy: boolean;
}) {
  const workflow = snapshot.approvedWorkflows.find((item) => item.id === workflowId);
  const design = selectActiveDesign(snapshot);
  const isDemo = snapshot.mode === "demo";
  if (!workflow) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="run-dialog" role="dialog" aria-modal="true" aria-labelledby="workflow-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
        <button className="dialog-close" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        <span className="dialog-icon"><Icon name="runs" size={24} /></span>
        <p className="eyebrow">{isDemo ? "Browser simulation boundary" : "Approved execution boundary"}</p>
        <h2 id="workflow-dialog-title">{isDemo ? "Simulate" : "Run"} {workflow.name}</h2>
        <p>{isDemo ? <>The browser models lifecycle events for <strong>{workflow.id}</strong> and links reviewed, precomputed evidence. It does not contact a solver or execute <code>{workflow.executorKey}</code>.</> : <>The browser submits <strong>{workflow.id}</strong>. The service maps it to <code>{workflow.executorKey}</code> and owns the driver, arguments, output root, and timeout.</>}</p>
        <dl><div><dt>Design</dt><dd>{design?.label ?? "Not recorded"}</dd></div><div><dt>Release validation</dt><dd>{workflow.releaseValidation ? "Claimed" : "Not claimed"}</dd></div><div><dt>Driver record</dt><dd>{workflow.driverPath}</dd></div></dl>
        <div className="dialog-note dialog-note-boundary"><Icon name="info" size={18} />{workflow.claimBoundary}</div>
        <div className="dialog-actions"><button onClick={onClose}>Cancel</button><button className="primary-action" onClick={onConfirm} disabled={busy}>{isDemo ? "Start simulation" : "Start approved workflow"} <Icon name="chevron" size={16} /></button></div>
      </section>
    </div>
  );
}

function CompareView({ snapshot }: { snapshot: ProjectSnapshot }) {
  const comparison = selectCandidateComparison(snapshot);
  const preferred = selectPreferredCandidate(snapshot);
  const baseline = snapshot.candidates[0];
  const temperatures = comparison.map(({ candidate }) => candidate.metrics.peakTemperature.value);
  const minimum = Math.min(...temperatures);
  const maximum = Math.max(...temperatures);
  const range = Math.max(maximum - minimum, Number.EPSILON);
  const tempImprovement = baseline && preferred ? baseline.metrics.peakTemperature.value - preferred.metrics.peakTemperature.value : undefined;
  const warpageImprovement = baseline && preferred ? ((baseline.metrics.warpage.value - preferred.metrics.warpage.value) / baseline.metrics.warpage.value) * 100 : undefined;
  return (
    <div className="content-stack">
      <section className="page-intro"><div><p className="eyebrow">Design decision</p><h1>Compare candidates</h1><p>Physical performance, reliability margin, and computational cost use the same recorded metric basis.</p></div><span className="policy-status"><Icon name="check" size={18} />{preferred ? `${preferred.name} preferred` : "No feasible candidate"}</span></section>
      <section className="candidate-grid">{comparison.map(({ candidate, recommendation }) => {
        const width = 65 + ((maximum - candidate.metrics.peakTemperature.value) / range) * 35;
        return <article className={`candidate-card candidate-${recommendation}`} key={candidate.id}><div className="candidate-heading"><span>{candidate.id}</span><div><small>{candidate.revision}</small><h2>{candidate.name}</h2></div><b>{recommendation}</b></div><div className="temperature-bar"><span style={{ width: `${width}%` }} /><i>{formatQuantity(candidate.metrics.peakTemperature)}</i></div><dl><div><dt>Peak temperature</dt><dd>{formatQuantity(candidate.metrics.peakTemperature)}</dd></div><div><dt>Warpage</dt><dd>{formatQuantity(candidate.metrics.warpage)}</dd></div><div><dt>Failure margin</dt><dd>{formatQuantity(candidate.metrics.failureMargin)}</dd></div><div><dt>Runtime</dt><dd>{formatDuration(candidate.metrics.runtime.value)}</dd></div></dl><button>Open revision <Icon name="external" size={15} /></button></article>;
      })}</section>
      <section className="tradeoff-panel"><div><p className="eyebrow">Recommendation</p><h2>{preferred ? `${preferred.name} is the lowest-temperature feasible candidate.` : "No candidate clears the active margin gate."}</h2></div><p>{preferred && baseline && tempImprovement !== undefined && warpageImprovement !== undefined ? `Relative to ${baseline.name}, ${preferred.name} lowers peak temperature by ${tempImprovement.toFixed(1)} °C, changes warpage by ${warpageImprovement.toFixed(1)}%, and moves failure margin from ${formatQuantity(baseline.metrics.failureMargin)} to ${formatQuantity(preferred.metrics.failureMargin)}.` : "Add a feasible candidate or revise the active policy before selecting a design."}</p></section>
    </div>
  );
}

function EvidenceView({ snapshot, selectedModel }: { snapshot: ProjectSnapshot; selectedModel: ModelFidelity }) {
  const summary = selectEvidenceSummary(snapshot);
  const design = selectActiveDesign(snapshot);
  const decision = selectActiveDecision(snapshot);
  const run = selectLatestSuccessfulRun(snapshot, selectedModel);
  const margin = selectMetric(run, "margin");
  return (
    <div className="content-stack">
      <section className="page-intro"><div><p className="eyebrow">Engineering trust</p><h1>Evidence</h1><p>Results remain linked to source data, verification checks, artifacts, and run provenance.</p></div><span className="policy-status"><Icon name="shield" size={18} />{summary.verified} verified · {summary.review} review · {summary.generated} generated</span></section>
      <section className="evidence-grid">{snapshot.evidence.map((evidence) => {
        const artifacts = snapshot.artifacts.filter((artifact) => evidence.artifactIds.includes(artifact.id));
        const artifactState = artifacts.length === evidence.artifactIds.length ? "linked" : "missing";
        return <article key={evidence.id}><div className="evidence-top"><span className={`evidence-icon evidence-${evidence.status}`}><Icon name={evidence.category === "provenance" ? "evidence" : "shield"} size={20} /></span><b>{evidence.status}</b></div><small>{evidence.category} · {evidence.authority}</small><h2>{evidence.title}</h2><p>{evidence.description}</p><div className="artifact-source"><span>{evidence.source}</span><span>{artifacts.length} {artifactState}</span></div><footer>Updated {formatDateTime(evidence.updatedAt)}</footer></article>;
      })}</section>
      <section className="provenance-map"><div><span>Design revision</span><strong>{run?.input.designRevision ?? design?.label ?? "Not recorded"}</strong></div><i /><div><span>Model decision</span><strong>{decision ? `${selectModel(snapshot, decision.selectedModelId)?.shortName ?? decision.selectedModelId} · ${decision.status}` : "Not recorded"}</strong></div><i /><div><span>Run manifest</span><strong>{run?.id ?? "No successful run"}</strong></div><i /><div><span>Decision metric</span><strong>{margin ? `${margin.label} ${formatQuantity(margin.quantity)}` : "No margin result"}</strong></div></section>
    </div>
  );
}

function RunDialog({ snapshot, open, selectedModel, onClose, onConfirm, busy }: { snapshot: ProjectSnapshot; open: boolean; selectedModel: ModelFidelity; onClose: () => void; onConfirm: () => void; busy: boolean }) {
  const model = selectModel(snapshot, selectedModel);
  const design = selectActiveDesign(snapshot);
  const validity = selectGateEvaluations(snapshot, selectedModel).find((gate) => gate.id === "validity");
  if (!open || !model) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="run-dialog" role="dialog" aria-modal="true" aria-labelledby="run-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
        <button className="dialog-close" onClick={onClose} aria-label="Close"><Icon name="close" /></button><span className="dialog-icon"><Icon name="runs" size={24} /></span><p className="eyebrow">Review before execution</p><h2 id="run-dialog-title">Run {model.name}</h2><p>The backend will create a retained run record from <strong>{design?.label ?? "the active design"}</strong> and preserve its manifest.</p>
        <dl><div><dt>Expected runtime</dt><dd>{formatDuration(model.expectedRuntimeSeconds)}</dd></div><div><dt>Validity gate</dt><dd>{validity?.status ?? "not evaluable"}</dd></div><div><dt>Package revision</dt><dd>{design?.packageRevision ?? "Not recorded"}</dd></div></dl>
        <div className="dialog-note"><Icon name="shield" size={18} />{snapshot.mode === "demo" ? "Demonstration mode simulates the run lifecycle and returns labeled precomputed data; it does not execute a solver." : "No solver command is exposed to the browser. The backend resolves the approved executor."}</div>
        <div className="dialog-actions"><button onClick={onClose}>Cancel</button><button className="primary-action" onClick={onConfirm} disabled={busy}>Start analysis <Icon name="chevron" size={16} /></button></div>
      </section>
    </div>
  );
}

function EvidenceDrawer({ snapshot, run, metricKey, onClose }: { snapshot: ProjectSnapshot; run: RunRecord | undefined; metricKey: MetricKey | null; onClose: () => void }) {
  const metric = metricKey ? selectMetric(run, metricKey) : undefined;
  if (!metric || !run) return null;
  const evidenceIds = [...new Set([...metric.evidenceIds, ...(metric.uncertainty?.evidenceIds ?? [])])];
  const evidence = selectEvidenceByIds(snapshot, evidenceIds);
  const integrity = selectEvidenceIntegrity(snapshot, evidenceIds);
  return (
    <aside className="evidence-drawer" aria-label={`${metric.label} evidence`}>
      <div className="drawer-heading"><span className="metric-icon"><Icon name={metricIcons[metric.key]} /></span><div><small>Metric evidence</small><h2>{metric.label}</h2></div><button onClick={onClose} aria-label="Close evidence"><Icon name="close" /></button></div>
      <div className="drawer-value"><strong>{formatQuantity(metric.quantity)}</strong><span className={`metric-status status-${metric.assessment}`}>{metric.assessment}</span></div>
      {metric.uncertainty && <article className="uncertainty-evidence"><span>{metric.uncertainty.kind}</span><h3>{formatUncertainty(metric)}</h3><p>{metric.uncertainty.method}</p><small>Validity domain: {metric.uncertainty.domain}{metric.uncertainty.kind === "validation-error" ? ` · ${metric.uncertainty.sampleCount} cases · ${metric.uncertainty.statistic}` : ""}</small></article>}
      {evidence.map((record) => <article key={record.id}><span>{record.category} · {record.authority}</span><h3>{record.title}</h3><p>{record.description}</p><small>{record.source}</small></article>)}
      <div className={`drawer-foot ${integrity.valid ? "" : "drawer-foot-error"}`}><Icon name={integrity.valid ? "shield" : "info"} size={18} />{integrity.valid ? `All requested evidence and artifact IDs resolve. ${run.id} records design ${run.input.designRevision}.` : `Missing evidence: ${integrity.missingIds.join(", ")}`}</div>
    </aside>
  );
}

export interface AppProps {
  backend: CoupFEBackend;
  projectId: string;
}

export default function App({ backend, projectId }: AppProps) {
  const { snapshot, loading, error, startRun, startWorkflow, cancelRun } = useWorkbench(backend, projectId);
  const [view, setView] = useState<ViewId>("overview");
  const [selectedModel, setSelectedModel] = useState<ModelFidelity>("reduced");
  const [selectedLayer, setSelectedLayer] = useState("interposer");
  const [mobileNav, setMobileNav] = useState(false);
  const [runDialog, setRunDialog] = useState(false);
  const [workflowDialog, setWorkflowDialog] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState("");
  const [inspectedMetric, setInspectedMetric] = useState<MetricKey | null>(null);
  const initializedSelection = useRef(false);

  useEffect(() => {
    if (!snapshot || initializedSelection.current) return;
    const decision = selectActiveDecision(snapshot);
    if (decision) setSelectedModel(decision.selectedModelId);
    if (snapshot.models.length === 0 && snapshot.approvedWorkflows.length > 0) setView("runs");
    if (snapshot.layers[0] && !snapshot.layers.some((layer) => layer.id === selectedLayer)) setSelectedLayer(snapshot.layers[0].id);
    initializedSelection.current = true;
  }, [selectedLayer, snapshot]);

  useEffect(() => {
    if (!runDialog && !workflowDialog && !inspectedMetric) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setRunDialog(false); setWorkflowDialog(null); setInspectedMetric(null); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [runDialog, workflowDialog, inspectedMetric]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const activeRun = useMemo(() => snapshot?.runs.find((run) => run.status === "queued" || run.status === "running"), [snapshot]);
  const selectedSuccessfulRun = snapshot ? selectLatestSuccessfulRun(snapshot, selectedModel) : undefined;

  if (loading && !snapshot) return <main className="loading-screen"><span className="brand-mark"><i /><i /><i /></span><strong>Loading the engineering record…</strong></main>;
  if (!snapshot) return <main className="loading-screen error-screen"><Icon name="info" size={28} /><strong>Workbench unavailable</strong><span>{error ?? "No project snapshot was returned."}</span></main>;

  const model = selectModel(snapshot, selectedModel);
  const gates = selectGateEvaluations(snapshot, selectedModel);
  const gatePassCount = gates.filter((gate) => gate.status === "pass").length;
  const lastCompleted = selectLastCompletedRun(snapshot);
  const design = selectActiveDesign(snapshot);
  const effectiveView: ViewId = snapshot.models.length === 0 && !["runs", "evidence"].includes(view)
    ? "runs"
    : view;
  const activeTargetLabel = activeRun
    ? snapshot.approvedWorkflows.find((item) => item.id === activeRun.workflowId)?.name
      ?? (activeRun.modelId ? selectModel(snapshot, activeRun.modelId)?.shortName : undefined)
      ?? "Run"
    : "";

  const chooseView = (nextView: ViewId) => { setView(nextView); setMobileNav(false); };
  const handleStartRun = async () => {
    setSubmitting(true);
    try {
      const run = await startRun(selectedModel);
      setRunDialog(false);
      setToast(`${model?.shortName ?? selectedModel} analysis queued · ${run.id}`);
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : "Unable to start the analysis.");
    } finally {
      setSubmitting(false);
    }
  };
  const handleStartWorkflow = async () => {
    if (!workflowDialog) return;
    setSubmitting(true);
    try {
      const run = await startWorkflow(workflowDialog);
      setWorkflowDialog(null);
      setToast(`${snapshot.mode === "demo" ? "Simulation" : "Approved workflow"} queued · ${run.id}`);
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : snapshot.mode === "demo" ? "Unable to start the simulation." : "Unable to start the approved workflow.");
    } finally {
      setSubmitting(false);
    }
  };
  const handleCancel = async (runId: string) => {
    try {
      const run = await cancelRun(runId);
      setToast(`${run.id} ${run.status}`);
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : "Unable to cancel the run.");
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <button className="mobile-menu" onClick={() => setMobileNav((value) => !value)} aria-label="Toggle navigation"><Icon name="menu" /></button>
        <div className="brand"><span className="brand-mark"><i /><i /><i /></span><strong>CoupFE<span>–EDA</span></strong></div>
        <div className="project-title"><span /><div><small>Active project</small><strong>{snapshot.project.name}</strong></div></div>
        <div className="topbar-meta"><div><Icon name="shield" size={19} /><span>{snapshot.models.length ? "Live gates" : "Approved workflows"}<strong>{snapshot.models.length ? `${gatePassCount} / ${gates.length} pass` : snapshot.approvedWorkflows.length}</strong></span></div><div><Icon name="clock" size={19} /><span>Last completed<strong>{lastCompleted ? formatDateTime(lastCompleted.completedAt) : "No completed run"}</strong></span></div></div>
        <button
          className="primary-action topbar-action"
          onClick={() => snapshot.models.length ? setRunDialog(true) : setWorkflowDialog(snapshot.approvedWorkflows[0]?.id ?? null)}
          disabled={Boolean(activeRun) || (!snapshot.models.length && !snapshot.approvedWorkflows.length)}
        >{activeRun ? `${activeTargetLabel} ${Math.round((activeRun.progress?.fraction ?? 0) * 100)}%` : snapshot.models.length ? "Run selected model" : snapshot.mode === "demo" ? "Simulate approved workflow" : "Run approved workflow"}<Icon name="chevron" size={17} /></button>
      </header>

      <nav className={`sidebar ${mobileNav ? "is-open" : ""}`} aria-label="Primary navigation">
        <div className="sidebar-cap"><span>{design?.label ?? "No active design"}</span><small>{design?.packageRevision ?? "No package revision"}</small></div>
        {navItems.filter((item) => snapshot.models.length > 0 || ["runs", "evidence"].includes(item.id)).map((item) => <button key={item.id} className={effectiveView === item.id ? "is-active" : ""} onClick={() => chooseView(item.id)} aria-current={effectiveView === item.id ? "page" : undefined}><Icon name={item.id} size={23} /><span>{item.label}</span></button>)}
        <div className="sidebar-foot"><span className="connection-dot" /><div><strong>{snapshot.mode === "demo" ? "Demonstration backend" : "Connected backend"}</strong><small>{snapshot.mode === "demo" ? "Precomputed data adapter" : "API event stream"}</small></div></div>
      </nav>

      <section className="workspace">
        <div className={`mode-banner mode-${snapshot.mode}`} role="note"><Icon name="info" size={16} /><span><strong>{snapshot.mode === "demo" ? "Demonstration data" : "Connected project"}</strong>{snapshot.mode === "demo" ? "No engineering solver runs in this browser demo. Simulation actions model lifecycle events and return labeled precomputed results." : "Results and run events are provided by the configured CoupFE–EDA API."}</span>{error && <b>{error}</b>}</div>
        <div className="workspace-mobile-title"><span>{navItems.find((item) => item.id === effectiveView)?.label}</span><small>{snapshot.project.name}</small></div>
        {effectiveView === "overview" && <OverviewView snapshot={snapshot} selectedModel={selectedModel} setSelectedModel={setSelectedModel} selectedLayer={selectedLayer} setSelectedLayer={setSelectedLayer} onInspectMetric={setInspectedMetric} />}
        {effectiveView === "geometry" && <GeometryView snapshot={snapshot} selectedModel={selectedModel} selectedLayer={selectedLayer} setSelectedLayer={setSelectedLayer} />}
        {effectiveView === "models" && <ModelsView snapshot={snapshot} selectedModel={selectedModel} setSelectedModel={setSelectedModel} />}
        {effectiveView === "runs" && <RunsView snapshot={snapshot} onRunModel={() => setRunDialog(true)} onRunWorkflow={setWorkflowDialog} onCancel={(runId) => void handleCancel(runId)} activeRun={activeRun} />}
        {effectiveView === "compare" && <CompareView snapshot={snapshot} />}
        {effectiveView === "evidence" && <EvidenceView snapshot={snapshot} selectedModel={selectedModel} />}
      </section>

      <RunDialog snapshot={snapshot} open={runDialog} selectedModel={selectedModel} onClose={() => setRunDialog(false)} onConfirm={() => void handleStartRun()} busy={submitting} />
      <WorkflowRunDialog snapshot={snapshot} workflowId={workflowDialog} onClose={() => setWorkflowDialog(null)} onConfirm={() => void handleStartWorkflow()} busy={submitting} />
      <EvidenceDrawer snapshot={snapshot} run={selectedSuccessfulRun} metricKey={inspectedMetric} onClose={() => setInspectedMetric(null)} />
      {toast && <div className="toast" role="status"><Icon name="check" size={17} />{toast}</div>}
      {mobileNav && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMobileNav(false)} />}
    </main>
  );
}
