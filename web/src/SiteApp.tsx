import App from "./App";
import { createBackend } from "./backend/factory";
import siteData from "../site-data.json";

type Workflow = (typeof siteData.workflows)[number];
type WorkflowKind = "integration" | "verification";

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
  const thresholdPercent = siteData.tsvScreening.threshold * 100;
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
    workflowFor("etv_partitioned_cycle"),
    workflowFor("solder_3d_cycle"),
    workflowFor("solder_plane_cycle"),
  ];

  return (
    <div className="site-shell">
      <header className="site-header">
        <a className="site-brand" href={import.meta.env.BASE_URL}><Mark /><strong>CoupFE<span>–EDA</span></strong></a>
        <nav className="site-desktop-nav" aria-label="Project website">
          <a href="#how-it-works">How it works</a>
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
            <a href="#examples">Examples</a>
            <a href="#validation">Evidence</a>
            <a href="#performance">Performance</a>
            <a href={repositoryFile("docs/README.md")}>Documentation</a>
          </nav>
        </details>
        <a className="site-header-action" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Interface demo <span>→</span></a>
      </header>

      <main>
        <section className="site-hero">
          <div className="site-hero-copy">
            <p className="site-kicker"><span /> Open research software · built on CoupFE</p>
            <h1>EDA-aware multiphysics, from design inputs to reviewable evidence.</h1>
            <p className="site-lede">
              CoupFE-EDA connects stable design identities and generated analysis representations
              to documented electrical, thermal, mechanical, and reliability workflows. The public
              repository provides runnable research examples and retained evidence records; it does
              not establish real-device accuracy, predictive package life, manufacturing qualification,
              or EDA signoff.
            </p>
            <div className="site-hero-actions">
              <a className="site-primary-link" href="#how-it-works">See how it works <span>↓</span></a>
              <a className="site-secondary-link" href={siteData.repository.url}>View source on GitHub <span>↗</span></a>
            </div>
          </div>
          <aside className="site-hero-panel">
            <div className="site-hero-panel-head"><span>Current public record</span><b>{siteData.recordDate}</b></div>
            <dl>
              <div><dt>Guided workflows</dt><dd>{siteData.workflows.length}<small>runners and retained oracles</small></dd></div>
              <div><dt>Retained benchmark</dt><dd>{siteData.scaling.ndof.toLocaleString()}<small>degrees of freedom</small></dd></div>
              <div><dt>Real-device validation</dt><dd className="site-record-status">Not established<small>experiment-matched qualification</small></dd></div>
            </dl>
            <Boundary>{siteData.projectBoundary}</Boundary>
          </aside>
        </section>

        <section className="site-process site-section" id="how-it-works">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> How CoupFE-EDA works</p><h2>A traceable path from design inputs to engineering evidence</h2></div>
            <p>{siteData.process.summary}</p>
          </div>
          <ol className="site-process-flow">
            {siteData.process.steps.map((step, index) => (
              <li key={step.id}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{step.title}</strong>
                <p>{step.detail}</p>
              </li>
            ))}
          </ol>
          <Boundary>{siteData.process.boundary}</Boundary>
          <div className="site-process-principles" aria-label="Project principles">
            <article><span>01</span><div><strong>Trace the design object</strong><p>Stable IDs and provenance survive handoffs into analysis records.</p></div></article>
            <article><span>02</span><div><strong>Keep model levels explicit</strong><p>Components, examples, timings, and experimental comparisons retain separate evidence labels.</p></div></article>
            <article><span>03</span><div><strong>Fail closed</strong><p>Stateful examples emit results only after every accepted increment satisfies the solver rule.</p></div></article>
          </div>
        </section>

        <section className="site-feature" id="device-screening">
          <div className="site-feature-visual">
            <img
              src={publicAsset(siteData.tsvScreening.figureAsset)}
              alt="Synthetic TSV device sites before and after the deterministic orientation-screening action"
            />
            <a href={publicAsset(siteData.tsvScreening.figureAsset)}>Open full-size SVG <span>↗</span></a>
          </div>
          <div className="site-feature-copy">
            <p className="site-kicker"><span /> Retained synthetic integration demonstration</p>
            <div className="site-feature-title"><h2>Identity-preserving TSV-to-device screening</h2><span>Synthetic inputs</span></div>
            <p>
              The project runner maps {siteData.tsvScreening.nDevices} synthetic device IDs
              through a classical Lamé far-field stress proxy and channel-oriented mobility
              proxies. A deterministic orientation action is then re-screened at a {thresholdPercent}% threshold.
            </p>
            <div className="site-feature-process" aria-label="Synthetic TSV screening process">
              <span>Stable IDs</span><span>Stress proxy</span><span>Mobility proxy</span><span>Threshold screen</span><span>Synthetic orientation action</span>
            </div>
            <div className="site-feature-metrics">
              <article><span>Synthetic proxy violations</span><strong>{siteData.tsvScreening.baselineViolations} <i>→</i> {siteData.tsvScreening.optimizedViolations}</strong></article>
              <article><span>Peak |mobility proxy|</span><strong>{siteData.tsvScreening.baselinePeakAbsMobilityProxy.toFixed(4)} <i>→</i> {siteData.tsvScreening.optimizedPeakAbsMobilityProxy.toFixed(4)}</strong></article>
            </div>
            <Boundary>{siteData.tsvScreening.displayBoundary}</Boundary>
            <nav className="site-inline-links" aria-label="TSV screening evidence">
              <a href={publicAsset(siteData.tsvScreening.evidenceAsset)}>Evidence JSON</a>
              <a href={publicAsset(siteData.tsvScreening.csvAsset)}>Device CSV</a>
              <SourceLink path={siteData.tsvScreening.readmePath}>Method and limits</SourceLink>
              <SourceLink path={siteData.tsvScreening.expectedPath}>Regression oracle</SourceLink>
            </nav>
          </div>
        </section>

        <section className="site-interface-cta" id="interface">
          <div><p className="site-kicker"><span /> Supervision interface</p><h2>Explore models, evidence, and simulated lifecycle events</h2></div>
          <p>The public interface demonstrates the review and supervision contract. It does not execute CoupFE-EDA solvers; connected execution remains a separate loopback-only local setup.</p>
          <nav aria-label="Interface demonstration">
            <a className="site-primary-link" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Open interface demonstration <span>→</span></a>
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
    <div className="prototype-route">
      <div className="prototype-boundary" role="note">
        <a href={import.meta.env.BASE_URL}>← Project website</a>
        <strong>{apiMode ? "Local connected workbench" : "Interface demonstration — no solver runs in this public page"}</strong>
        <span>{apiMode ? "Only server-approved workflows are available." : "Values and lifecycle events inside the cockpit are illustrative unless linked to the retained TSV demonstration record."}</span>
      </div>
      <App backend={createBackend()} projectId={apiMode ? "coupfe-eda-local" : "tsv-thermal-001"} />
    </div>
  );
}

export default function SiteApp() {
  const surface = new URLSearchParams(window.location.search).get("surface");
  return surface === "workbench" ? <WorkbenchSurface /> : <PublicSite />;
}
