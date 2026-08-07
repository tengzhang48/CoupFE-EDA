import App from "./App";
import { createBackend } from "./backend/factory";
import siteData from "../site-data.json";

type Workflow = (typeof siteData.workflows)[number];
type WorkflowKind = "integration" | "verification";
type SimulationMedia = (typeof siteData.simulationMedia)[number];
type EtvMeshMetadata = {
  meshNx?: number;
  meshNy?: number;
  topAggregationElements?: number;
  topRowDepthMicrometers?: number;
};
type EtvSetup = (typeof siteData.etvComparison.setup) & EtvMeshMetadata;

const repositoryFile = (sourcePath: string) =>
  `${siteData.repository.url}/blob/${siteData.repository.branch}/${sourcePath}`;

const publicAsset = (assetPath: string) =>
  `${import.meta.env.BASE_URL}${assetPath.replace(/^\//, "")}`;

export function formatSignedPercent(value: number, fractionDigits: number) {
  const sign = value < 0 ? "−" : "+";
  return `${sign}${Math.abs(value).toFixed(fractionDigits)}%`;
}

function Mark() {
  return <span className="site-mark" aria-hidden="true"><i /><i /><i /></span>;
}

function SourceLink({ path, children }: { path: string; children: string }) {
  return <a className="site-source-link" href={repositoryFile(path)}>{children}<span aria-hidden="true">↗</span></a>;
}

function Boundary({ children, compact = false }: { children: string; compact?: boolean }) {
  return (
    <div className={`site-boundary ${compact ? "site-boundary-compact" : ""}`}>
      <span>Claim boundary</span>
      <p>{children}</p>
    </div>
  );
}

function ProcessDiagram() {
  const stepFor = (id: string) => {
    const step = siteData.process.steps.find((candidate) => candidate.id === id);
    if (!step) throw new Error(`Missing process step ${id}`);
    return step;
  };
  const identity = stepFor("identity_provenance");
  const feedback = stepFor("bounded_feedback");
  const stages = [
    { step: stepFor("design_inputs"), role: "Source", signals: ["placement", "power", "PDN", "joints"] },
    { step: stepFor("analysis_representation"), role: "Model", signals: ["mesh", "analytic proxy", "reduced form"] },
    { step: stepFor("selected_analysis"), role: "Analyze", signals: ["electrical", "thermal", "mechanics", "solder"] },
    { step: stepFor("retained_evidence"), role: "Record", signals: ["oracles", "residuals", "arrays", "boundaries"] },
  ];

  return (
    <figure
      className="site-process-map"
      aria-labelledby="process-map-title"
      aria-describedby="process-map-caption"
    >
      <section className="site-process-trace" aria-label="Information retained across every handoff">
        <header><span>Persistent trace</span><strong>{identity.title}</strong></header>
        <p>{identity.detail}</p>
        <div className="site-process-trace-track" aria-hidden="true">
          {stages.map(({ step }) => <i key={step.id} />)}
        </div>
      </section>

      <ol className="site-process-stages" aria-label="Analysis handoffs">
        {stages.map(({ step, role, signals }, index) => (
          <li className={step.id === "retained_evidence" ? "is-evidence" : ""} key={step.id}>
            <header><span>{String(index + 1).padStart(2, "0")}</span><small>{role}</small></header>
            <strong>{step.title}</strong>
            <p>{step.detail}</p>
            <ul className="site-process-signals" aria-label={`${role} record contents`}>
              {signals.map((signal) => <li key={signal}>{signal}</li>)}
            </ul>
          </li>
        ))}
      </ol>

      <aside className="site-process-return" aria-label="Bounded return path to source identity">
        <header><span>Return to source ID</span><strong>{feedback.title}</strong></header>
        <p>{feedback.detail}</p>
        <b><i aria-hidden="true">×</i> No live database edits</b>
      </aside>

      <section className="site-process-rules" aria-labelledby="process-rules-title">
        <strong id="process-rules-title">Record rules</strong>
        <ul>
          <li><i>01</i> Stable identity</li>
          <li><i>02</i> Declared model level</li>
          <li><i>03</i> Checked outputs only</li>
        </ul>
      </section>

      <figcaption id="process-map-caption">{siteData.process.summary}</figcaption>
    </figure>
  );
}

function HeroResult() {
  const field = siteData.tsvField;
  return (
    <figure
      className="site-hero-result"
      aria-labelledby="hero-result-title"
      aria-describedby="hero-result-caption hero-result-scope"
    >
      <header>
        <div>
          <span>Actual CoupFE output</span>
          <strong id="hero-result-title">Solver-derived TSV stress field</strong>
        </div>
        <a href={publicAsset(field.contourAsset)}>Open full figure <span aria-hidden="true">↗</span></a>
      </header>
      <a
        className="site-hero-result-visual"
        href={publicAsset(field.contourAsset)}
        aria-label="Open the complete solver-derived TSV contour"
      >
        <svg
          viewBox="0 160 580 418"
          role="img"
          aria-labelledby="hero-field-title hero-field-description"
          preserveAspectRatio="xMidYMid meet"
        >
          <title id="hero-field-title">Axisymmetric TSV radial stress field</title>
          <desc id="hero-field-description">
            Cropped view of the retained radial stress reconstruction around the copper and silicon interface. The complete figure also contains the fixed color scale, recovered stress profiles, and Lamé comparison.
          </desc>
          <image href={publicAsset(field.contourAsset)} width="1200" height="720" />
        </svg>
      </a>
      <figcaption id="hero-result-caption">
        <strong>{field.diameterUm} µm TSV · σrr({field.queryRadiusUm} µm) = {field.sigmaRrAtQueryMpa.toFixed(3)} MPa</strong>
        <span>{field.relativeErrorPercent.toFixed(4)}% from the declared Lamé reference · {field.degreesOfFreedom.toLocaleString()} DOFs · {field.loadSteps} static solves</span>
      </figcaption>
      <div className="site-hero-result-scope" id="hero-result-scope" role="note">
        <span>Scope</span>
        <p><strong>Measured-device comparison: not performed.</strong> Axisymmetric plane-strain component verification; not a finite-depth 3-D model, transient simulation, or experimental result.</p>
      </div>
    </figure>
  );
}

function WorkflowCard({ workflow, kind, displayIndex }: { workflow: Workflow; kind: WorkflowKind; displayIndex: number }) {
  return (
    <article className={`site-workflow-card site-workflow-card-${kind}`}>
      <header>
        <span>{String(displayIndex).padStart(2, "0")}</span>
        <div><small>{kind === "integration" ? "EDA-linked demonstration" : "Physics / solver verification"}</small><h4>{workflow.title}</h4></div>
      </header>
      <p>{workflow.summary}</p>
      <div className="site-result-strip">
        <strong>{workflow.result}</strong>
        <span>{workflow.detail}</span>
      </div>
      <Boundary compact>{workflow.boundary}</Boundary>
      <code>{workflow.command}</code>
      <footer>
        <span>{workflow.tier}</span>
        <nav aria-label={`${workflow.title} sources`}>
          <SourceLink path={workflow.readmePath}>Guide</SourceLink>
          <SourceLink path={workflow.runnerPath}>Code</SourceLink>
          <SourceLink path={workflow.resultPath}>Retained result</SourceLink>
        </nav>
      </footer>
    </article>
  );
}

function SimulationEvidenceLinks({
  media,
  assetLabel = "Generated SVG",
  downloadAsset = false,
  recordAsset,
}: {
  media: SimulationMedia;
  assetLabel?: string;
  downloadAsset?: boolean;
  recordAsset?: string;
}) {
  return (
    <nav className="site-inline-links" aria-label={`${media.title} evidence`}>
      <a href={publicAsset(media.asset)} download={downloadAsset || undefined}>{assetLabel}</a>
      {recordAsset ? <a href={publicAsset(recordAsset)} download>Retained state JSON</a> : null}
      <SourceLink path={media.runnerPath}>Runner</SourceLink>
      <SourceLink path={media.resultPath}>Regression oracle</SourceLink>
      <SourceLink path={media.evidencePath}>SHA-256 record</SourceLink>
    </nav>
  );
}

function EtvStructuredMesh({
  x,
  y,
  size,
  columns,
  rows,
}: {
  x: number;
  y: number;
  size: number;
  columns: number;
  rows: number;
}) {
  const verticalLines = Array.from({ length: columns - 1 }, (_, index) => {
    const lineX = x + ((index + 1) * size) / columns;
    return `M${lineX} ${y}V${y + size}`;
  });
  const horizontalLines = Array.from({ length: rows - 1 }, (_, index) => {
    const lineY = y + ((index + 1) * size) / rows;
    return `M${x} ${lineY}H${x + size}`;
  });
  const topRowHeight = size / rows;

  return (
    <g
      data-etv-mesh-grid={`${columns}x${rows}`}
      data-etv-top-row-elements={columns}
      aria-hidden="true"
    >
      <rect className="site-etv-schematic-domain" x={x} y={y} width={size} height={size} />
      <rect
        className="site-etv-schematic-sample"
        x={x + 1}
        y={y + 1}
        width={size - 2}
        height={Math.max(topRowHeight - 1, 1)}
      />
      <path
        className="site-etv-schematic-grid"
        d={[...verticalLines, ...horizontalLines].join(" ")}
        shapeRendering="crispEdges"
        vectorEffect="non-scaling-stroke"
      />
    </g>
  );
}

function EtvSetupDiagram({
  meshNx,
  meshNy,
  topAggregationElements,
  topRowDepthMicrometers,
}: {
  meshNx: number;
  meshNy: number;
  topAggregationElements: number;
  topRowDepthMicrometers: number;
}) {
  const comparison = siteData.etvComparison;
  const meshLabel = `${meshNx} by ${meshNy}`;
  return (
    <figure className="site-etv-setup-figure" aria-labelledby="etv-setup-title" aria-describedby="etv-setup-caption">
      <header><span>01 · Declared model</span><h4 id="etv-setup-title">What is being solved</h4></header>
      <svg className="site-etv-setup-desktop" viewBox="0 0 460 305" role="img" aria-labelledby="etv-schematic-title etv-schematic-description">
        <title id="etv-schematic-title">Plane-strain solder-block model setup on a selected {meshLabel} mesh</title>
        <desc id="etv-schematic-description">A {meshLabel} quadrilateral mesh representing a 0.1 millimetre square SAC305 block. The bottom edge is fixed, horizontal thermal-mismatch displacement is prescribed at the top, lateral sides are traction free, and the {topAggregationElements}-element top row is the {topRowDepthMicrometers} micrometre-deep aggregation region.</desc>
        <defs>
          <marker id="etv-arrow-desktop" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" /></marker>
        </defs>
        <EtvStructuredMesh x={80} y={45} size={190} columns={meshNx} rows={meshNy} />
        <line className="site-etv-schematic-load" x1="94" y1="24" x2="202" y2="24" markerEnd="url(#etv-arrow-desktop)" />
        <text x="80" y="15">prescribed top displacement</text>
        <path className="site-etv-schematic-callout" d="M270 47H293V69" />
        <text x="302" y="62">top: uₓ = γH</text>
        <text x="302" y="79">uᵧ = 0</text>
        <path className="site-etv-schematic-callout site-etv-schematic-aggregation-callout" d="M270 54H284V112H295" />
        <text className="site-etv-schematic-sample-label" x="302" y="105">aggregation: top row</text>
        <text className="site-etv-schematic-sample-label" x="302" y="122">{topAggregationElements} elements · {topRowDepthMicrometers} µm</text>
        <path className="site-etv-schematic-callout" d="M270 155H293" />
        <text x="302" y="151">sides:</text>
        <text x="302" y="168">traction free</text>
        <path className="site-etv-schematic-callout" d="M270 235H293V218" />
        <text x="302" y="213">bottom:</text>
        <text x="302" y="230">uₓ = uᵧ = 0</text>
        {[95, 127, 159, 191, 223, 255].map((x) => <path className="site-etv-schematic-fix" d={`M${x} 235l-8 13h16z`} key={x} />)}
        <path className="site-etv-schematic-dimension" d="M80 270V258M80 264H270M270 270V258" />
        <text x="175" y="286" textAnchor="middle">{comparison.setup.widthMm.toFixed(1)} mm</text>
        <path className="site-etv-schematic-dimension" d="M50 45H62M56 45V235M50 235H62" />
        <text x="35" y="140" textAnchor="middle" transform="rotate(-90 35 140)">{comparison.setup.heightMm.toFixed(1)} mm</text>
      </svg>
      <svg className="site-etv-setup-mobile" viewBox="0 0 300 425" role="img" aria-labelledby="etv-schematic-mobile-title etv-schematic-mobile-description">
        <title id="etv-schematic-mobile-title">Plane-strain solder-block model setup on a selected {meshLabel} mesh, mobile layout</title>
        <desc id="etv-schematic-mobile-description">A mobile schematic of the same {meshLabel} quadrilateral mesh, its {topAggregationElements}-element top aggregation row, and the declared displacement boundary conditions.</desc>
        <defs>
          <marker id="etv-arrow-mobile" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" /></marker>
        </defs>
        <text x="22" y="18">prescribed top displacement</text>
        <line className="site-etv-schematic-load" x1="55" y1="34" x2="170" y2="34" markerEnd="url(#etv-arrow-mobile)" />
        <EtvStructuredMesh x={55} y={54} size={190} columns={meshNx} rows={meshNy} />
        {[70, 102, 134, 166, 198, 230].map((x) => <path className="site-etv-schematic-fix" d={`M${x} 244l-8 13h16z`} key={x} />)}
        <path className="site-etv-schematic-dimension" d="M55 283V271M55 277H245M245 283V271" />
        <text x="150" y="302" textAnchor="middle">{comparison.setup.widthMm.toFixed(1)} mm × {comparison.setup.heightMm.toFixed(1)} mm</text>
        <text className="site-etv-schematic-sample-label" x="22" y="329">Aggregation: top row · {topAggregationElements} elements · {topRowDepthMicrometers} µm</text>
        <text x="22" y="352">Top: uₓ = γH; uᵧ = 0 (prescribed)</text>
        <text x="22" y="375">Sides: traction free</text>
        <text x="22" y="398">Bottom: uₓ = uᵧ = 0</text>
      </svg>
      <figcaption id="etv-setup-caption">Model schematic—not a solved field. Selected single mesh; no mesh-convergence study. Plane strain; out-of-plane package geometry is not modeled.</figcaption>
    </figure>
  );
}

function EtvComparisonResult() {
  const comparison = siteData.etvComparison;
  const comparisonMesh = comparison as typeof comparison & EtvMeshMetadata;
  const setup = comparison.setup as EtvSetup;
  const meshNx = comparisonMesh.meshNx ?? setup.meshNx ?? 20;
  const meshNy = comparisonMesh.meshNy ?? setup.meshNy ?? 20;
  const topAggregationElements = comparisonMesh.topAggregationElements ?? setup.topAggregationElements ?? meshNx;
  const topRowDepthMicrometers = comparisonMesh.topRowDepthMicrometers ?? setup.topRowDepthMicrometers ?? (setup.heightMm * 1000) / meshNy;
  const elementCount = meshNx * meshNy;
  const nodeCount = (meshNx + 1) * (meshNy + 1);
  const displacementDofs = nodeCount * 2;
  const media = siteData.simulationMedia.find((candidate) => candidate.id === comparison.mediaId);
  if (!media) throw new Error(`Missing ETV simulation media ${comparison.mediaId}`);
  const temperatureLabel = (value: number) => value < 0 ? `−${Math.abs(value)}` : `${value}`;
  const outputAlt = `Retained second-cycle temperature paths and accumulated inelastic-energy-density fields, dW, for quasisteady and lumped-transient treatments on the selected ${meshNx} by ${meshNy} SAC305 mesh; every element is shown without smoothing and the end-cycle deformation is magnified 10 times`;

  return (
    <article className="site-etv-result" aria-labelledby="etv-result-title">
      <header className="site-etv-case-header">
        <div><span>Checked partitioned example · {comparison.caseId}</span><h3 id="etv-result-title">Thermal-mismatch shear in SAC305</h3></div>
        <p>A uniform local temperature drives a spatial mechanics solve on one selected {meshNx} × {meshNy} mesh. The comparison asks how much the retained response changes between two declared uniform-temperature treatments; it is not a mesh-convergence result.</p>
      </header>

      <section className="site-etv-setup" aria-label="Declared ETV model setup">
        <EtvSetupDiagram
          meshNx={meshNx}
          meshNy={meshNy}
          topAggregationElements={topAggregationElements}
          topRowDepthMicrometers={topRowDepthMicrometers}
        />
        <div className="site-etv-setup-ledger">
          <p className="site-kicker"><span /> Selected retained inputs</p>
          <dl>
            <div><dt>Domain / mesh</dt><dd>{comparison.setup.widthMm.toFixed(1)} × {comparison.setup.heightMm.toFixed(1)} mm<br /><span>{meshNx} × {meshNy} Quad4 plane strain · {nodeCount} nodes · {displacementDofs} DOFs</span></dd></div>
            <div><dt>Reported aggregation</dt><dd>Top-row element mean<br /><span>{topAggregationElements} elements · {topRowDepthMicrometers} µm row depth</span></dd></div>
            <div><dt>Constitutive inputs</dt><dd>{comparison.setup.material}<br /><span>Project elastic inputs: E = {(comparison.setup.elasticModulusMPa / 1000).toFixed(0)} GPa · ν = {comparison.setup.poissonRatio.toFixed(2)}</span></dd></div>
            <div><dt>Chamber cycle</dt><dd>{temperatureLabel(comparison.temperatureCycleC.low)} → {comparison.temperatureCycleC.high} → {temperatureLabel(comparison.temperatureCycleC.low)} °C<br /><span>{comparison.cycles} cycles · {comparison.incrementsPerCycle} increments/cycle</span></dd></div>
            <div><dt>Mismatch loading</dt><dd>γ = Δα(T<sub>local</sub> − T<sub>ref</sub>)(L<sub>D</sub>/h)<br /><span>Δα = {(comparison.setup.cteMismatchPerK * 1e6).toFixed(0)} × 10⁻⁶ K⁻¹ · L<sub>D</sub>/h = {comparison.setup.distanceToNeutralPointOverHeight.toFixed(0)} · T<sub>ref</sub> = {comparison.setup.temperatureReferenceC.toFixed(1)} °C</span></dd></div>
            <div><dt>Thermal reduction</dt><dd>g<sub>th</sub> = {(comparison.setup.thermalConductanceDensityWPerM3K / 1e6).toFixed(1)} MW/m³K · ρc = {(comparison.setup.volumetricHeatCapacityJPerM3K / 1e6).toFixed(1)} MJ/m³K<br /><span>Taylor–Quinney fraction = {comparison.setup.inelasticHeatFraction.toFixed(1)}</span></dd></div>
          </dl>
          <div className="site-etv-input-note" role="note">
            <strong>Scalar heating input</strong>
            <p>q<sub>J</sub> = {comparison.setup.jouleDensityWPerM3.toExponential(5)} W/m³ comes from the documented representative current-density context. This cycle does not solve an electrical field or reproduce that bump geometry.</p>
          </div>
        </div>
      </section>

      <section className="site-etv-paths" aria-labelledby="etv-paths-title">
        <header><span>02 · Two declared thermal paths</span><h4 id="etv-paths-title">Same mechanics; two alternative uniform-temperature treatments</h4></header>
        <div className="site-etv-path-grid">
          <div className="site-etv-path-input"><small>Prescribed chamber cycle</small><strong>{temperatureLabel(comparison.temperatureCycleC.low)} → {comparison.temperatureCycleC.high} → {temperatureLabel(comparison.temperatureCycleC.low)} °C</strong><span>1,600 s or 1 s period</span></div>
          <div className="site-etv-path-branches" aria-label="Alternative uniform-temperature treatments">
            <article><small>Alternative A</small><strong>Quasisteady</strong><p>Uniform chamber temperature plus the steady Joule-heating offset.</p></article>
            <span className="site-etv-path-or" aria-hidden="true">OR</span>
            <article><small>Alternative B</small><strong>Lumped transient</strong><p>Uniform temperature advanced by backward Euler with finite heat capacity and one-increment-lagged inelastic heating.</p></article>
          </div>
          <div className="site-etv-path-solve"><small>Shared spatial solve</small><strong>{elementCount} Quad4 elements</strong><span>stateful plane-strain SAC305 mechanics</span></div>
        </div>
        <p>Partitioned uniform-temperature feedback—not a monolithic φ–T–u element or a spatial thermal-field solution.</p>
      </section>

      <section className="site-etv-output" aria-labelledby="etv-output-title">
        <figure className="site-etv-output-visual">
          <header>
            <div><span>03 · Actual checked simulation output</span><h4 id="etv-output-title">Temperature histories and end-cycle inelastic-energy fields</h4></div>
            <nav aria-label="ETV figure layouts">
              <a href={publicAsset(media.asset)}>Desktop SVG <span aria-hidden="true">↗</span></a>
              <a href={publicAsset(comparison.mobileAsset)}>Portrait SVG <span aria-hidden="true">↗</span></a>
            </nav>
          </header>
          <div className="site-etv-output-context" role="note" aria-label="Simulation setup carried into the output">
            <strong>Problem carried into these snapshots</strong>
            <span>0.1 × 0.1 mm SAC305 · {meshNx} × {meshNy} Quad4 · bottom fixed · top thermal-mismatch shear · sides free · {temperatureLabel(comparison.temperatureCycleC.low)} → {comparison.temperatureCycleC.high} → {temperatureLabel(comparison.temperatureCycleC.low)} °C in {comparison.fast.periodSeconds.toLocaleString()} s</span>
          </div>
          <div className="site-etv-output-frame" aria-describedby="etv-output-caption">
            <picture>
              <source media="(max-width: 900px)" srcSet={publicAsset(comparison.mobileAsset)} />
              <img src={publicAsset(media.asset)} alt={outputAlt} loading="lazy" />
            </picture>
          </div>
          <figcaption id="etv-output-caption">These are two actual end-cycle solver snapshots. Each colored cell is its element’s accumulated inelastic energy density, dW, during the second cycle. Both fields use one common scale with no interpolation or smoothing; deformation is magnified 10×. Temperature is uniform by construction and is therefore shown as a history, not a spatial contour.</figcaption>
        </figure>
        <div className="site-etv-reading">
          <p className="site-kicker"><span /> What this case establishes</p>
          <div className="site-etv-metric"><span>Energy-density change</span><strong>{formatSignedPercent(comparison.fast.relativeDifferencePercent, 2)}</strong><small>Lumped relative to quasisteady<br />{comparison.relativeDifferenceDefinition}</small></div>
          <p>
            At {comparison.slow.periodSeconds.toLocaleString()} s, the two treatments nearly agree. At {comparison.fast.periodSeconds.toLocaleString()} s, they produce different retained temperature paths and second-cycle inelastic-energy results. This comparison does not establish which treatment is more accurate.
            {` `}It uses one selected {meshNx} × {meshNy} mesh and does not establish mesh convergence.
          </p>
          <dl>
            <div><dt>Quasisteady local T peak</dt><dd>{comparison.fast.quasisteadyPeakTemperatureC.toFixed(2)} °C <span>uniform-temperature path</span></dd></div>
            <div><dt>Lumped local T peak</dt><dd>{comparison.fast.lumpedTransientPeakTemperatureC.toFixed(2)} °C <span>uniform-temperature path</span></dd></div>
            <div><dt>Second-cycle accumulated dW</dt><dd>{comparison.fast.quasisteadyEnergyMPa.toFixed(6)} → {comparison.fast.lumpedTransientEnergyMPa.toFixed(6)} MPa<span>{topAggregationElements}-element, {topRowDepthMicrometers} µm top-row mean</span></dd></div>
            <div><dt>1,600 s top-row control</dt><dd>{comparison.slow.quasisteadyEnergyMPa.toFixed(6)} → {comparison.slow.lumpedTransientEnergyMPa.toFixed(6)} MPa<span>{formatSignedPercent(comparison.slow.relativeDifferencePercent, 4)}</span></dd></div>
          </dl>
          <div className="site-etv-check" role="note" aria-label="ETV regression status">
            <span>Regression oracle <strong>{comparison.oraclePassed ? "passed" : "not passed"}</strong></span>
            <code>{comparison.command}</code>
          </div>
          <Boundary compact>{comparison.boundary}</Boundary>
          <SimulationEvidenceLinks media={media} assetLabel="Retained dW-field SVG" recordAsset={comparison.recordAsset} />
        </div>
      </section>
    </article>
  );
}

function SupportingSimulationOutputs() {
  const mediaFor = (id: string) => {
    const media = siteData.simulationMedia.find((candidate) => candidate.id === id);
    if (!media) throw new Error(`Missing supporting simulation media ${id}`);
    return media;
  };
  const solder = mediaFor("solder_3d_dissipation");
  const device = mediaFor("tsv_device_screening");
  const comparison = siteData.solderComparison;

  return (
    <section className="site-output-register" aria-labelledby="supporting-output-title">
      <header>
        <span>Supporting output register</span>
        <div><h3 id="supporting-output-title">Two additional checks, kept in proportion</h3><p>The representative solder map is shown once; its second same-block loading variant is not repeated here. The device result is explicitly analytic, not FE.</p></div>
      </header>
      <ol>
        <li>
          <span className="site-output-index">01</span>
          <a className="site-output-thumbnail" href={publicAsset(solder.asset)} aria-label="Open the complete 18-element solder output"><img src={publicAsset(solder.asset)} alt={solder.alt} loading="lazy" /></a>
          <div className="site-output-identity"><small>Stateful 3-D FE mechanics</small><strong>Idealized SAC305 block</strong><span>3 × 3 × 2 Hex8 · one thermal cycle</span></div>
          <div className="site-output-value"><strong>{comparison.baselinePeakDissipationMPa.toFixed(6)} MPa</strong><span>peak accumulated inelastic energy density</span></div>
          <div className="site-output-scope">
            <p>All {comparison.elements} cycle-accumulated element values are retained; all {comparison.acceptedIncrements} increments were accepted. Mean {comparison.baselineMeanDissipationMPa.toFixed(6)} MPa, peak/mean {comparison.baselinePeakToMean.toFixed(5)}.</p>
            <Boundary compact>{solder.boundary}</Boundary>
            <SimulationEvidenceLinks media={solder} assetLabel="Open 18-element output" />
          </div>
        </li>
        <li>
          <span className="site-output-index">02</span>
          <a className="site-output-thumbnail" href={publicAsset(device.asset)} aria-label="Open the complete synthetic TSV-to-device identity map"><img src={publicAsset(device.asset)} alt={device.alt} loading="lazy" /></a>
          <div className="site-output-identity"><small>Analytic EDA handoff · not FE</small><strong>TSV-to-device screening</strong><span>{siteData.tsvScreening.nDevices} project-authored synthetic devices · {(siteData.tsvScreening.threshold * 100).toFixed(0)}% threshold</span></div>
          <div className="site-output-value"><strong>{siteData.tsvScreening.baselineViolations} → {siteData.tsvScreening.optimizedViolations}</strong><span>proxy-threshold exceedances</span></div>
          <div className="site-output-scope">
            <p>Peak absolute mobility proxy {siteData.tsvScreening.baselinePeakAbsMobilityProxy.toFixed(4)} → {siteData.tsvScreening.optimizedPeakAbsMobilityProxy.toFixed(4)} after the deterministic orientation action.</p>
            <Boundary compact>{device.boundary}</Boundary>
            <SimulationEvidenceLinks media={device} assetLabel="Open identity map" />
          </div>
        </li>
      </ol>
    </section>
  );
}

function ScalingFigure() {
  const maximum = Math.max(...siteData.scaling.medianSeconds);
  const first = siteData.scaling.medianSeconds[0]!;
  const last = siteData.scaling.medianSeconds.at(-1)!;
  const firstRank = siteData.scaling.ranks[0]!;
  const lastRank = siteData.scaling.ranks.at(-1)!;
  return (
    <div className="site-scaling-chart" role="img" aria-label={`Median solve wall time decreases from ${first.toFixed(2)} seconds at ${firstRank} rank to ${last.toFixed(2)} seconds at ${lastRank} ranks`}>
      {siteData.scaling.ranks.map((rank, index) => (
        <div className="site-scaling-row" key={rank}>
          <strong>{rank}<small>{rank === 1 ? " rank" : " ranks"}</small></strong>
          <div><span style={{ width: `${(siteData.scaling.medianSeconds[index]! / maximum) * 100}%` }} /></div>
          <p><b>{siteData.scaling.medianSeconds[index]!.toFixed(2)} s</b><small>{siteData.scaling.speedup[index]!.toFixed(2)}×</small></p>
        </div>
      ))}
    </div>
  );
}

function PublicSite() {
  const firstMedian = siteData.scaling.medianSeconds[0]!;
  const lastMedian = siteData.scaling.medianSeconds.at(-1)!;
  const firstRank = siteData.scaling.ranks[0]!;
  const lastRank = siteData.scaling.ranks.at(-1)!;
  const measuredSpeedup = siteData.scaling.speedup.at(-1)!;
  const workflowFor = (id: string) => {
    const workflow = siteData.workflows.find((candidate) => candidate.id === id);
    if (!workflow) throw new Error(`Missing public workflow ${id}`);
    return workflow;
  };
  const integrationWorkflows = [
    workflowFor("tsv_device_screening"),
    workflowFor("design_linked_solder_screening"),
  ];
  const verificationWorkflows = [
    workflowFor("tsv_axisymmetric_field"),
    workflowFor("etv_partitioned_cycle"),
    workflowFor("solder_3d_cycle"),
  ];

  return (
    <div className="site-shell">
      <a className="site-skip-link" href="#main-content">Skip to content</a>
      <header className="site-header">
        <a className="site-brand" href={import.meta.env.BASE_URL}><Mark /><strong>CoupFE<span>–EDA</span></strong></a>
        <nav className="site-desktop-nav" aria-label="Project website">
          <a href="#how-it-works">How it works</a>
          <a href="#simulations">Simulations</a>
          <a href="#examples">Examples</a>
          <a href="#validation">Evidence</a>
          <a href="#performance">Performance</a>
          <a href={repositoryFile("docs/README.md")}>Documentation</a>
        </nav>
        <details className="site-mobile-nav">
          <summary>Menu</summary>
          <nav
            aria-label="Mobile project website"
            onClick={(event) => {
              if ((event.target as HTMLElement).closest("a")) {
                event.currentTarget.closest("details")?.removeAttribute("open");
              }
            }}
          >
            <a href="#how-it-works">How it works</a>
            <a href="#simulations">Simulations</a>
            <a href="#examples">Examples</a>
            <a href="#validation">Evidence</a>
            <a href="#performance">Performance</a>
            <a href={repositoryFile("docs/README.md")}>Documentation</a>
          </nav>
        </details>
        <a className="site-header-action" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Real field explorer <span>→</span></a>
      </header>

      <main id="main-content">
        <section className="site-hero">
          <div className="site-hero-copy">
            <p className="site-kicker"><span /> Open research software · built on CoupFE</p>
            <h1>EDA-aware multiphysics, with results you can inspect.</h1>
            <p className="site-lede">
              CoupFE-EDA carries stable design identities into documented electrical, thermal,
              mechanical, and reliability analyses. Runnable examples retain field arrays, solver
              telemetry, reference checks, and explicit model limits for review.
            </p>
            <div className="site-hero-actions">
              <a className="site-primary-link" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Explore retained field <span>→</span></a>
              <a className="site-secondary-link" href={siteData.repository.url}>View source on GitHub <span>↗</span></a>
            </div>
          </div>
          <HeroResult />
        </section>

        <section className="site-process site-section" id="how-it-works">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> How CoupFE-EDA works</p><h2 id="process-map-title">From design record to checked result.</h2></div>
            <p>Across the checked examples, representations change at each handoff. Identity, units, model choices, and evidence limits stay attached.</p>
          </div>
          <ProcessDiagram />
          <Boundary>{siteData.process.boundary}</Boundary>
        </section>

        <section className="site-feature" id="solver-field">
          <div className="site-feature-visual">
            <figure className="site-feature-player">
              <video
                src={publicAsset(siteData.tsvField.videoAsset)}
                aria-describedby="tsv-load-sweep-caption"
                controls
                muted
                playsInline
                preload="auto"
              />
              <figcaption id="tsv-load-sweep-caption"><strong>{siteData.tsvField.caseId}</strong><span>{siteData.tsvField.videoInterpretation}</span></figcaption>
            </figure>
            <a href={publicAsset(siteData.tsvField.contourAsset)}>Open solver-derived contour <span>↗</span></a>
          </div>
          <div className="site-feature-copy">
            <p className="site-kicker"><span /> Evidence behind the field · raw arrays included</p>
            <div className="site-feature-title"><h2>Inspect the run behind the field</h2><span>Retained evidence</span></div>
            <p>
              The named reference runner solves a {siteData.tsvField.diameterUm} µm copper TSV under
              {` ${siteData.tsvField.deltaTemperatureK} K`} prescribed cooling with CoupFE Core. The retained
              bundle contains all {siteData.tsvField.nodes.toLocaleString()} radial nodes, displacement,
              σrr, σθθ, convergence telemetry, and nine independently solved load states.
            </p>
            <div className="site-feature-process" aria-label="Axisymmetric TSV field evidence process">
              <span>Line2 mesh</span><span>CoupFE Newton solve</span><span>σrr + σθθ recovery</span><span>Lamé comparison</span><span>Hash-bound media</span>
            </div>
            <div className="site-feature-metrics">
              <article><span>Radial stress at r = {siteData.tsvField.queryRadiusUm} µm</span><strong>{siteData.tsvField.sigmaRrAtQueryMpa.toFixed(2)} MPa</strong></article>
              <article><span>Difference from declared Lamé reference</span><strong>{siteData.tsvField.relativeErrorPercent.toFixed(4)}%</strong></article>
              <article><span>Mesh / DOFs</span><strong>{siteData.tsvField.elements.toLocaleString()} / {siteData.tsvField.degreesOfFreedom.toLocaleString()}</strong></article>
              <article><span>Accepted load states</span><strong>{siteData.tsvField.loadSteps} independent solves</strong></article>
            </div>
            <Boundary>{siteData.tsvField.claimBoundary}</Boundary>
            <nav className="site-inline-links" aria-label="Axisymmetric TSV field evidence">
              <a href={publicAsset(siteData.tsvField.fieldAsset)}>Raw field JSON</a>
              <a href={publicAsset(siteData.tsvField.summaryAsset)}>Numerical summary</a>
              <a href={publicAsset(siteData.tsvField.manifestAsset)}>SHA-256 manifest</a>
              <SourceLink path={siteData.tsvField.runnerPath}>Exact runner</SourceLink>
              <SourceLink path={siteData.tsvField.readmePath}>Method and limits</SourceLink>
            </nav>
          </div>
        </section>

        <section className="site-section site-simulation-evidence" id="simulations">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Separate checked setup · partitioned ETV</p><h2>How does a 0.1 mm solder block respond to a one-second thermal cycle?</h2></div>
            <p>A fixed-bottom, shear-driven SAC305 block is solved with two uniform-temperature treatments. The case sheet below establishes the selected mesh and loading before showing the retained second-cycle temperature paths and accumulated element-mean dW fields.</p>
          </div>
          <EtvComparisonResult />
          <SupportingSimulationOutputs />
          <div className="site-simulation-provenance" role="note">
            <strong>Evidence construction</strong>
            <span>The ETV and solder media are regenerated from their named runners and are refused when the retained numerical oracles fail. The analytic device artifacts are regenerated separately. Every linked artifact remains bound to a SHA-256 contract.</span>
          </div>
        </section>

        <section className="site-interface-cta" id="interface">
          <div><p className="site-kicker"><span /> Real field workbench</p><h2>Probe the mesh, fields, load sweep, and solver evidence</h2></div>
          <p>GitHub Pages explores the retained, hash-verified CoupFE run. A local connected checkout exposes one fixed server-owned Run action that executes the same case; the browser never supplies a command, mesh size, or solver argument.</p>
          <nav aria-label="Real field workbench">
            <a className="site-primary-link" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Open real field explorer <span>→</span></a>
            <a className="site-secondary-link" href={repositoryFile("web/README.md")}>Local setup documentation <span>↗</span></a>
          </nav>
        </section>

        <section className="site-section site-examples" id="examples">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Checked examples</p><h2>EDA-linked demonstrations and focused numerical examples</h2></div>
            <p>Every card links to its runner, retained numerical oracle, and full limitation. The grouping distinguishes declared handoff demonstrations from focused physics and solver checks.</p>
          </div>
          <section className="site-workflow-group" aria-labelledby="integration-workflows-title">
            <header><div><span>EDA-linked demonstrations</span><h3 id="integration-workflows-title">Design identities carried into engineering screens</h3></div><p>Integration examples preserve a synthetic design object across a declared analysis or screening handoff.</p></header>
            <div className="site-workflow-grid site-workflow-grid-integration">
              {integrationWorkflows.map((workflow, index) => <WorkflowCard workflow={workflow} kind="integration" displayIndex={index + 1} key={workflow.id} />)}
            </div>
          </section>
          <section className="site-workflow-group" aria-labelledby="verification-workflows-title">
            <header><div><span>Physics and solver verification</span><h3 id="verification-workflows-title">Selected physics and solver examples</h3></div><p>These examples check specific constitutive, coupling, assembly, and state-update behavior without claiming a complete device workflow.</p></header>
            <div className="site-workflow-grid site-workflow-grid-verification">
              {verificationWorkflows.map((workflow, index) => <WorkflowCard workflow={workflow} kind="verification" displayIndex={index + 1} key={workflow.id} />)}
            </div>
          </section>
        </section>

        <section className="site-scaling site-section" id="performance">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Performance evidence</p><h2>{siteData.scaling.ndof.toLocaleString()}-DOF fixed-size solve</h2></div>
            <p>{siteData.scaling.driver} · {siteData.scaling.repeatsPerRank} complete launches per rank count · synchronized maximum-rank solve wall time.</p>
          </div>
          <div className="site-scaling-layout">
            <ScalingFigure />
            <aside>
              <strong>{firstMedian.toFixed(2)} s <i>→</i> {lastMedian.toFixed(2)} s</strong>
              <span>{firstRank} to {lastRank} ranks · {measuredSpeedup.toFixed(2)}× measured speedup</span>
              <dl>
                <div><dt>Problem</dt><dd>{siteData.scaling.ndof.toLocaleString()} DOF, n={siteData.scaling.problemN}</dd></div>
                <div><dt>Rank sweep</dt><dd>{siteData.scaling.ranks.join(" / ")}</dd></div>
                <div><dt>Last KSP iterations</dt><dd>{siteData.scaling.iterations.join(" / ")}</dd></div>
                <div><dt>Machine scope</dt><dd>{siteData.scaling.machineScope}</dd></div>
              </dl>
              <Boundary compact>{siteData.scaling.boundary}</Boundary>
              <nav className="site-inline-links" aria-label="Scaling sources">
                <SourceLink path={siteData.scaling.summaryPath}>Every sample</SourceLink>
                <SourceLink path={siteData.scaling.tablePath}>Table</SourceLink>
                <SourceLink path={siteData.scaling.manifestPath}>Protocol</SourceLink>
              </nav>
            </aside>
          </div>
        </section>

        <section className="site-validation-summary site-section" id="validation">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Validation status</p><h2>Checked foundations; real-device validation remains open</h2></div>
            <p>The homepage summarizes the current boundary. The detailed evidence categories, secondary figures, and future research stages remain public in the linked technical records.</p>
          </div>
          <div className="site-validation-grid">
            <article><span>Demonstrated here</span><h3>Checked public evidence</h3><ul><li>Five guided result-bearing workflows with retained regression oracles</li><li>Synthetic identity-preserving TSV screening and deterministic orientation action</li><li>A retained 526,338-DOF, 1/2/4/8-rank benchmark on its recorded machine</li></ul></article>
            <article><span>Not currently claimed</span><h3>Real-device qualification</h3><ul><li>Experiment-matched TSV stress or mobility agreement</li><li>Predictive solder/package life or a live OpenDB design loop</li><li>Manufacturing signoff or production qualification</li></ul></article>
            <article><span>Next major milestone</span><h3>3-D TSV reference case</h3><p>Retain a permitted, versioned reference case with experiment-matched boundary conditions, mesh/domain convergence, and a comparison record with declared alignment and uncertainty.</p></article>
          </div>
          <div className="site-validation-footer">
            <Boundary>{siteData.projectBoundary}</Boundary>
            <nav className="site-inline-links" aria-label="Validation records">
              <SourceLink path={siteData.scorecard.evidenceGuidePath}>Evidence guide</SourceLink>
              <SourceLink path={siteData.scorecard.roadmapPath}>Research roadmap</SourceLink>
              <SourceLink path={siteData.scorecard.sourcePath}>Machine-readable status</SourceLink>
            </nav>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <a className="site-brand" href={import.meta.env.BASE_URL}><Mark /><strong>CoupFE<span>–EDA</span></strong></a>
        <div><p>One open implementation of EDA-aware multiphysics workflows, built on CoupFE. The current evidence limits remain explicit.</p><small>v{siteData.repository.version} · {siteData.repository.releaseStatus} · {siteData.repository.author}</small></div>
        <nav aria-label="Project resources"><a href={siteData.repository.url}>GitHub</a><SourceLink path="docs/README.md">Documentation</SourceLink><SourceLink path={siteData.scorecard.evidenceGuidePath}>Evidence</SourceLink><SourceLink path={siteData.scorecard.roadmapPath}>Roadmap</SourceLink><a href={siteData.repository.issuesUrl}>Contact / issues</a><a href={publicAsset("legal/LICENSE")}>License</a><a href={publicAsset("legal/THIRD_PARTY.md")}>Notices</a></nav>
      </footer>
    </div>
  );
}

function WorkbenchSurface() {
  const apiMode = import.meta.env.VITE_COUPFE_BACKEND === "fastapi";
  return (
    <div className="workbench-route">
      <header className="workbench-topbar">
        <a href={import.meta.env.BASE_URL}>← CoupFE–EDA website</a>
        <div>
          <strong>TSV field workbench</strong>
          <span>Axisymmetric plane-strain component verification</span>
        </div>
        <span className="workbench-topbar-status">{apiMode ? "Local solver connected" : "Retained evidence · read only"}</span>
      </header>
      <App
        backend={apiMode ? createBackend() : undefined}
        projectId="coupfe-eda-local"
        retainedFieldUrl={publicAsset(siteData.tsvField.fieldAsset)}
        summaryUrl={publicAsset(siteData.tsvField.summaryAsset)}
        manifestUrl={publicAsset(siteData.tsvField.manifestAsset)}
        runnerUrl={repositoryFile(siteData.tsvField.runnerPath)}
      />
    </div>
  );
}

export default function SiteApp() {
  const surface = new URLSearchParams(window.location.search).get("surface");
  return surface === "workbench" ? <WorkbenchSurface /> : <PublicSite />;
}
