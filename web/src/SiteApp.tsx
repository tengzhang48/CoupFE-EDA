import { useEffect, useState } from "react";
import App from "./App";
import { createBackend } from "./backend/factory";
import siteData from "../site-data.json";

type Workflow = (typeof siteData.workflows)[number];
type WorkflowKind = "integration" | "verification";
type PhysicsKind = "electrical" | "thermal" | "mechanical" | "reliability";

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
      <span>Evidence boundary</span>
      <p>{children}</p>
    </div>
  );
}

function PhysicsGlyph({ kind }: { kind: PhysicsKind }) {
  return (
    <span className={`site-physics-glyph site-physics-${kind}`} aria-hidden="true">
      <i /><i /><i /><i />
    </span>
  );
}

function WorkflowCard({ workflow, kind, displayIndex }: { workflow: Workflow; kind: WorkflowKind; displayIndex: number }) {
  return (
    <article className={`site-workflow-card site-workflow-card-${kind}`}>
      <header>
        <span>{String(displayIndex).padStart(2, "0")}</span>
        <small>{kind === "integration" ? "Design-linked" : "Physics verification"}</small>
      </header>
      <h3>{workflow.title}</h3>
      <p>{workflow.summary}</p>
      <div className="site-result-strip">
        <strong>{workflow.result}</strong>
        <span>{workflow.detail}</span>
      </div>
      <footer>
        <span>{workflow.tier}</span>
        <nav aria-label={`${workflow.title} sources`}>
          <SourceLink path={workflow.readmePath}>Guide</SourceLink>
          <SourceLink path={workflow.runnerPath}>Code</SourceLink>
          <SourceLink path={workflow.resultPath}>Result</SourceLink>
        </nav>
      </footer>
    </article>
  );
}

function ScalingFigure({ compact = false }: { compact?: boolean }) {
  const maximum = Math.max(...siteData.scaling.medianSeconds);
  const first = siteData.scaling.medianSeconds[0]!;
  const last = siteData.scaling.medianSeconds.at(-1)!;
  const firstRank = siteData.scaling.ranks[0]!;
  const lastRank = siteData.scaling.ranks.at(-1)!;
  return (
    <div
      className={`site-scaling-chart ${compact ? "site-scaling-chart-compact" : ""}`}
      role="img"
      aria-label={`Median solve wall time decreases from ${first.toFixed(2)} seconds at ${firstRank} rank to ${last.toFixed(2)} seconds at ${lastRank} ranks`}
    >
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

const reelScenes = [
  {
    id: "field",
    tab: "Coupled field",
    eyebrow: "Concept visualization",
    title: "See the package as a field, not a stack of disconnected files.",
    body: "Electrical, thermal, and mechanical effects share geometry and design identity across the workflow.",
  },
  {
    id: "screening",
    tab: "Device screening",
    eyebrow: "Retained synthetic output",
    title: "Track the TSV effect all the way back to named device sites.",
    body: "The checked demonstration carries 32 stable device IDs through a stress-to-mobility proxy and orientation screen.",
  },
  {
    id: "scaling",
    tab: "Solver scaling",
    eyebrow: "Measured benchmark",
    title: "Move from model definition to a reviewable, timed solve record.",
    body: "The repository retains every sample from a fixed 526,338-DOF rank sweep on its recorded machine.",
  },
] as const;

function SimulationReel() {
  const [activeScene, setActiveScene] = useState(0);
  const [playing, setPlaying] = useState(true);
  const scene = reelScenes[activeScene]!;

  useEffect(() => {
    if (!playing) return undefined;
    const timer = window.setInterval(
      () => setActiveScene((current) => (current + 1) % reelScenes.length),
      6200,
    );
    return () => window.clearInterval(timer);
  }, [playing]);

  return (
    <section className="site-reel site-section" id="simulations">
      <div className="site-section-heading site-section-heading-dark">
        <div><p className="site-kicker"><span /> Simulation reel</p><h2>Look at the physics before reading about it.</h2></div>
        <p>Three views, three evidence levels. Each one says exactly what it is.</p>
      </div>
      <div className="site-reel-shell">
        <div className="site-reel-tabs" role="tablist" aria-label="Simulation views">
          {reelScenes.map((candidate, index) => (
            <button
              key={candidate.id}
              type="button"
              role="tab"
              aria-selected={activeScene === index}
              onClick={() => setActiveScene(index)}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>{candidate.tab}
            </button>
          ))}
          <button className="site-reel-play" type="button" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "Pause simulation reel" : "Play simulation reel"}>
            <span aria-hidden="true">{playing ? "Ⅱ" : "▶"}</span>{playing ? "Pause" : "Play"}
          </button>
        </div>
        <figure className={`site-reel-stage site-reel-stage-${scene.id}`} key={scene.id}>
          <div className="site-reel-media">
            {scene.id === "field" && (
              <img src={publicAsset("visuals/multiphysics-package-concept.png")} alt="Illustrative semiconductor package cutaway with a colored coupled-field overlay" />
            )}
            {scene.id === "screening" && (
              <img src={publicAsset(siteData.tsvScreening.figureAsset)} alt="Retained synthetic TSV device screening result before and after orientation action" />
            )}
            {scene.id === "scaling" && <ScalingFigure compact />}
            <span className="site-reel-scan" aria-hidden="true" />
          </div>
          <figcaption>
            <p>{scene.eyebrow}</p>
            <h3>{scene.title}</h3>
            <span>{scene.body}</span>
            {scene.id === "field" && <small>Illustrative artwork · not solver output</small>}
            {scene.id === "screening" && <a href={publicAsset(siteData.tsvScreening.figureAsset)}>Open retained SVG <span>↗</span></a>}
            {scene.id === "scaling" && <SourceLink path={siteData.scaling.summaryPath}>Inspect every sample</SourceLink>}
          </figcaption>
        </figure>
      </div>
    </section>
  );
}

function PublicSite() {
  const firstMedian = siteData.scaling.medianSeconds[0]!;
  const lastMedian = siteData.scaling.medianSeconds.at(-1)!;
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
    workflowFor("etv_partitioned_cycle"),
    workflowFor("solder_3d_cycle"),
    workflowFor("solder_plane_cycle"),
  ];

  return (
    <div className="site-shell">
      <header className="site-header">
        <a className="site-brand" href={import.meta.env.BASE_URL}><Mark /><strong>CoupFE<span>–EDA</span></strong></a>
        <nav className="site-desktop-nav" aria-label="Project website">
          <a href="#capabilities">Capabilities</a>
          <a href="#simulations">Simulations</a>
          <a href="#workflow">Workflow</a>
          <a href="#evidence">Evidence</a>
          <a href={repositoryFile("docs/README.md")}>Docs</a>
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
            <a href="#capabilities">Capabilities</a>
            <a href="#simulations">Simulations</a>
            <a href="#workflow">Workflow</a>
            <a href="#evidence">Evidence</a>
            <a href={repositoryFile("docs/README.md")}>Docs</a>
          </nav>
        </details>
        <a className="site-header-action" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Launch workbench <span>↗</span></a>
      </header>

      <main>
        <section className="site-hero">
          <div className="site-hero-copy">
            <p className="site-kicker"><span /> Open-source semiconductor multiphysics</p>
            <h1>Find the hot spots.<br />See the stress.<br /><em>Decide with evidence.</em></h1>
            <p className="site-lede">
              CoupFE-EDA carries design identities into electrical, thermal, mechanical, and reliability workflows—then links every result back to its inputs, code, and evidence.
            </p>
            <div className="site-hero-actions">
              <a className="site-primary-link" href="#simulations">Watch the simulation <span>↓</span></a>
              <a className="site-secondary-link" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Try the workbench <span>↗</span></a>
            </div>
            <p className="site-hero-boundary">Research alpha · checked synthetic and verification cases · no manufacturing signoff claim</p>
          </div>
          <figure className="site-hero-visual">
            <img src={publicAsset("visuals/multiphysics-package-concept.png")} alt="Illustrative semiconductor package cutaway with finite-element-style field contours around copper vias" />
            <div className="site-hero-field-label"><i /><span>COUPLED FIELD VIEW</span><b>THERMAL · MECHANICAL</b></div>
            <div className="site-hero-legend"><span>LOW</span><i /><span>PEAK</span></div>
            <figcaption>Concept visualization · not solver output</figcaption>
          </figure>
          <div className="site-proof-strip" aria-label="Project evidence highlights">
            <article><strong>{siteData.workflows.length}</strong><span>checked workflows</span></article>
            <article><strong>{siteData.scaling.ndof.toLocaleString()}</strong><span>DOF retained solve</span></article>
            <article><strong>{siteData.tsvScreening.baselineViolations} → {siteData.tsvScreening.optimizedViolations}</strong><span>synthetic TSV violations</span></article>
            <article><strong>{measuredSpeedup.toFixed(2)}×</strong><span>measured at 8 ranks</span></article>
          </div>
        </section>

        <section className="site-capabilities site-section" id="capabilities">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> One engineering thread</p><h2>Four physics. One traceable design story.</h2></div>
            <p>Move from design-aware inputs to fields, screening metrics, and retained decisions without losing the identity of the object being analyzed.</p>
          </div>
          <div className="site-capability-grid">
            <article><PhysicsGlyph kind="electrical" /><span>01 / Electrical</span><h3>Current and power become loads</h3><p>Carry PDN, Joule-heating, and design-linked electrical quantities into the coupled workflow.</p><small>PDN · EM · Joule heating</small></article>
            <article><PhysicsGlyph kind="thermal" /><span>02 / Thermal</span><h3>Temperature becomes a field</h3><p>Resolve scalar and 3-D thermal response with declared coupling and boundary assumptions.</p><small>Steady · transient · distributed</small></article>
            <article><PhysicsGlyph kind="mechanical" /><span>03 / Mechanical</span><h3>Stress becomes visible</h3><p>Inspect thermoelastic response around TSVs, joints, and package layers instead of relying on a single scalar.</p><small>Stress · warpage · interfaces</small></article>
            <article><PhysicsGlyph kind="reliability" /><span>04 / Reliability</span><h3>Fields become decisions</h3><p>Screen device proxies and stateful solder observables while keeping stable design IDs attached.</p><small>Mobility proxy · dissipation · gates</small></article>
          </div>
        </section>

        <SimulationReel />

        <section className="site-process site-section" id="workflow">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Workflow</p><h2>From design object to reviewable result.</h2></div>
            <p>The handoffs stay explicit: identity, units, model choice, result, and boundary travel together.</p>
          </div>
          <ol className="site-process-flow">
            <li><span>01</span><strong>Bring the design context</strong><p>Placement, power, package, joint, or synthetic case inputs enter with stable IDs.</p></li>
            <li><span>02</span><strong>Choose the physics path</strong><p>Electrical, thermal, mechanical, and stateful models make assumptions visible.</p></li>
            <li><span>03</span><strong>Run and retain</strong><p>Named runners emit checked outputs, metrics, provenance, and regression oracles.</p></li>
            <li><span>04</span><strong>Screen the decision</strong><p>Map bounded results back to the design object without pretending they are signoff.</p></li>
          </ol>
        </section>

        <section className="site-workbench-feature" id="workbench">
          <div className="site-workbench-visual">
            <div className="site-workbench-window">
              <header><i /><i /><i /><span>TSV DEVICE SCREENING / LIVE PREVIEW</span></header>
              <video
                className="site-workbench-video"
                autoPlay
                muted
                loop
                playsInline
                poster={publicAsset(siteData.tsvScreening.figureAsset)}
                aria-label="Looping interface demonstration of the interactive TSV stress-to-device screening workbench"
              >
                <source src={publicAsset("visuals/tsv-workbench-demo.webm")} type="video/webm" />
              </video>
              <img className="site-workbench-poster" src={publicAsset(siteData.tsvScreening.figureAsset)} alt="Synthetic TSV device screening visualization shown inside the workbench preview" />
              <b className="site-workbench-video-label">INTERFACE DEMO · 00:09</b>
              <span className="site-workbench-scan" aria-hidden="true" />
            </div>
          </div>
          <div className="site-workbench-copy">
            <p className="site-kicker"><span /> Interactive workbench</p>
            <h2>Don’t just read the run record. Watch the field change.</h2>
            <p>The redesigned demo opens on an animated TSV field, lets you switch between stress and device views, and plays the approved workflow lifecycle against reviewed, precomputed evidence.</p>
            <div className="site-feature-metrics">
              <article><span>Synthetic proxy violations</span><strong>{siteData.tsvScreening.baselineViolations} <i>→</i> {siteData.tsvScreening.optimizedViolations}</strong></article>
              <article><span>Peak |mobility proxy|</span><strong>{siteData.tsvScreening.baselinePeakAbsMobilityProxy.toFixed(3)} <i>→</i> {siteData.tsvScreening.optimizedPeakAbsMobilityProxy.toFixed(3)}</strong></article>
            </div>
            <div className="site-hero-actions">
              <a className="site-primary-link" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Launch interactive demo <span>↗</span></a>
              <SourceLink path={siteData.tsvScreening.readmePath}>Read the method</SourceLink>
            </div>
            <Boundary compact>{siteData.tsvScreening.claimBoundary}</Boundary>
          </div>
        </section>

        <section className="site-examples site-section" id="examples">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Runnable cases</p><h2>Start from code that already produces evidence.</h2></div>
            <p>Every case links straight to its runner and retained result. Design-linked demonstrations are visually separated from focused solver checks.</p>
          </div>
          <div className="site-workflow-grid">
            {integrationWorkflows.map((workflow, index) => <WorkflowCard workflow={workflow} kind="integration" displayIndex={index + 1} key={workflow.id} />)}
            {verificationWorkflows.map((workflow, index) => <WorkflowCard workflow={workflow} kind="verification" displayIndex={index + 3} key={workflow.id} />)}
          </div>
        </section>

        <section className="site-performance site-section" id="performance">
          <div className="site-performance-copy">
            <p className="site-kicker"><span /> Measured solve</p>
            <h2>{siteData.scaling.ndof.toLocaleString()} degrees of freedom.<br /><em>{firstMedian.toFixed(2)} s → {lastMedian.toFixed(2)} s.</em></h2>
            <p>A fixed-size, 1/2/4/8-rank sweep with three complete launches per rank count. The result is bounded to the recorded machine and configuration.</p>
            <nav className="site-inline-links" aria-label="Scaling sources">
              <SourceLink path={siteData.scaling.summaryPath}>Every sample</SourceLink>
              <SourceLink path={siteData.scaling.tablePath}>Result table</SourceLink>
              <SourceLink path={siteData.scaling.manifestPath}>Protocol</SourceLink>
            </nav>
          </div>
          <ScalingFigure />
        </section>

        <section className="site-evidence site-section" id="evidence">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Evidence, not theater</p><h2>Clear about what works. Clear about what is still open.</h2></div>
            <p>The visuals make the work easier to understand; they do not expand the scientific claims.</p>
          </div>
          <div className="site-evidence-grid">
            <article><span>Demonstrated now</span><h3>Checked foundations</h3><ul><li>Five runnable, result-bearing workflows</li><li>Stable-ID TSV and solder screening handoffs</li><li>A retained 526,338-DOF MPI timing record</li></ul></article>
            <article><span>Not claimed</span><h3>Production qualification</h3><ul><li>Experiment-matched real-device accuracy</li><li>Predictive package life or manufacturing signoff</li><li>A live production EDA database loop</li></ul></article>
            <article><span>Next proof point</span><h3>3-D TSV reference case</h3><p>Freeze a permitted reference case, match experimental boundary conditions, complete convergence checks, and publish the comparison with uncertainty.</p></article>
          </div>
          <div className="site-evidence-footer">
            <Boundary>{siteData.projectBoundary}</Boundary>
            <nav className="site-inline-links" aria-label="Validation records">
              <SourceLink path={siteData.scorecard.evidenceGuidePath}>Evidence guide</SourceLink>
              <SourceLink path={siteData.scorecard.roadmapPath}>Roadmap</SourceLink>
              <SourceLink path={siteData.scorecard.sourcePath}>Machine-readable status</SourceLink>
            </nav>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <a className="site-brand" href={import.meta.env.BASE_URL}><Mark /><strong>CoupFE<span>–EDA</span></strong></a>
        <div><p>Open research software for EDA-aware multiphysics, built on CoupFE.</p><small>v{siteData.repository.version} · {siteData.repository.releaseStatus} · {siteData.repository.author}</small></div>
        <nav aria-label="Project resources"><a href={siteData.repository.url}>GitHub</a><SourceLink path="docs/README.md">Documentation</SourceLink><SourceLink path={siteData.scorecard.evidenceGuidePath}>Evidence</SourceLink><a href={siteData.repository.issuesUrl}>Issues</a><a href={publicAsset("legal/LICENSE")}>License</a></nav>
      </footer>
    </div>
  );
}

function WorkbenchSurface() {
  const apiMode = import.meta.env.VITE_COUPFE_BACKEND === "fastapi";
  return (
    <div className="prototype-route">
      <div className="prototype-boundary" role="note">
        <a href={import.meta.env.BASE_URL}>← Project website</a>
        <strong>{apiMode ? "Local connected workbench" : "Interactive demonstration — no solver runs in this public page"}</strong>
        <span>{apiMode ? "Only server-approved workflows are available." : "The animated field is a synthetic visualization; lifecycle events link to retained, precomputed evidence."}</span>
      </div>
      <App backend={createBackend()} projectId={apiMode ? "coupfe-eda-local" : "tsv-thermal-001"} />
    </div>
  );
}

export default function SiteApp() {
  const surface = new URLSearchParams(window.location.search).get("surface");
  return surface === "workbench" ? <WorkbenchSurface /> : <PublicSite />;
}
