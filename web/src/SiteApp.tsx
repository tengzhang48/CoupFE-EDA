import App from "./App";
import { createBackend } from "./backend/factory";
import siteData from "../site-data.json";

type Workflow = (typeof siteData.workflows)[number];
type WorkflowKind = "integration" | "verification";
type SimulationMedia = (typeof siteData.simulationMedia)[number];

const repositoryFile = (sourcePath: string) =>
  `${siteData.repository.url}/blob/${siteData.repository.branch}/${sourcePath}`;

const publicAsset = (assetPath: string) =>
  `${import.meta.env.BASE_URL}${assetPath.replace(/^\//, "")}`;

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

function SimulationMediaCard({ media }: { media: SimulationMedia }) {
  const comparison = siteData.solderComparison;
  const isDesignLinkedSolder = media.id === comparison.designLinkedMediaId;
  const peakRatio = comparison.baselinePeakDissipationMPa / comparison.designLinkedPeakDissipationMPa;
  return (
    <article className="site-media-card">
      <figure>
        <img src={publicAsset(media.asset)} alt={media.alt} loading="lazy" />
        <figcaption>{media.eyebrow}</figcaption>
      </figure>
      <div className="site-media-card-copy">
        <header><span>{media.eyebrow}</span><h3>{media.title}</h3></header>
        <p>{media.summary}</p>
        <div className="site-result-strip">
          <strong>{media.result}</strong>
          <span>{media.detail}</span>
        </div>
        {isDesignLinkedSolder && (
          <div className="site-media-comparison" role="note">
            <strong>Why this field is lower</strong>
            <span>
              L_D/h is {comparison.designLinkedLDOverH.toFixed(4)} versus {comparison.baselineLDOverH.toFixed(1)}
              {` in the other solder view. With the same 3 × 3 × 2 mesh and SAC305 material model, the lower ratio produces lower shear (${comparison.designLinkedShearRange.toFixed(6)} versus ${comparison.baselineShearRange.toFixed(6)}) and about ${peakRatio.toFixed(1)}× lower peak dissipation.`}
            </span>
          </div>
        )}
        <Boundary compact>{media.boundary}</Boundary>
        <nav className="site-inline-links" aria-label={`${media.title} evidence`}>
          <a href={publicAsset(media.asset)}>Open SVG</a>
          <SourceLink path={media.runnerPath}>Runner</SourceLink>
          <SourceLink path={media.resultPath}>Oracle</SourceLink>
          <SourceLink path={media.evidencePath}>SHA-256 record</SourceLink>
        </nav>
      </div>
    </article>
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

        <section className="site-section site-simulation-gallery" id="simulations">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Simulation media</p><h2>More views generated from checked CoupFE-EDA runs</h2></div>
            <p>These are data-driven exports, not stock imagery or AI-generated concepts. Each figure names its runner, retained oracle, checksum record, and evidence boundary.</p>
          </div>
          <div className="site-media-grid">
            {siteData.simulationMedia.map((media) => <SimulationMediaCard media={media} key={media.id} />)}
          </div>
          <div className="site-media-provenance" role="note">
            <strong>How these figures are built</strong>
            <span>The solder, design-linked solder, and ETV images rerun the named CoupFE mechanics examples and refuse output unless their numerical oracles pass. The device map is regenerated from its EDA screening runner. Artifact and source hashes are retained in the linked contracts.</span>
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
