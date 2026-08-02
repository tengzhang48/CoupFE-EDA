import App from "./App";
import { createBackend } from "./backend/factory";
import siteData from "../site-data.json";

type Workflow = (typeof siteData.workflows)[number];
type ScorecardCategory = (typeof siteData.scorecard.categories)[number];

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

function WorkflowCard({ workflow }: { workflow: Workflow }) {
  return (
    <article className="site-workflow-card">
      <header>
        <span>{workflow.index}</span>
        <div><small>Checked guided workflow</small><h3>{workflow.title}</h3></div>
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

function ScorecardRow({ category }: { category: ScorecardCategory }) {
  return (
    <article className="site-score-row">
      <div><span className={`site-status site-status-${category.status}`}>{category.status.replace("_", " ")}</span><h3>{category.label}</h3></div>
      <p>{category.reason}</p>
    </article>
  );
}

function PublicSite() {
  const blocked = siteData.scorecard.categories.filter((item) => item.status === "blocked").length;
  const notStarted = siteData.scorecard.categories.filter((item) => item.status === "not_started").length;
  const thresholdPercent = siteData.tsvScreening.threshold * 100;
  const firstMedian = siteData.scaling.medianSeconds[0]!;
  const lastMedian = siteData.scaling.medianSeconds.at(-1)!;
  const firstRank = siteData.scaling.ranks[0]!;
  const lastRank = siteData.scaling.ranks.at(-1)!;
  const measuredSpeedup = siteData.scaling.speedup.at(-1)!;

  return (
    <div className="site-shell">
      <header className="site-header">
        <a className="site-brand" href={import.meta.env.BASE_URL}><Mark /><strong>CoupFE<span>–EDA</span></strong></a>
        <nav aria-label="Project website">
          <a href="#workflows">Workflows</a>
          <a href="#device-screening">Device screening</a>
          <a href="#scaling">Scaling</a>
          <a href="#validation">Validation status</a>
        </nav>
        <a className="site-header-action" href={`${import.meta.env.BASE_URL}?surface=workbench`}>Interface demo <span>→</span></a>
      </header>

      <main>
        <section className="site-hero">
          <div className="site-hero-copy">
            <p className="site-kicker"><span /> Open research software · built on CoupFE</p>
            <h1>EDA-aware multiphysics workflows, with the evidence boundary visible.</h1>
            <p className="site-lede">
              CoupFE-EDA shows how design identities, generated geometry, coupled fields,
              stateful materials, and reliability screens can be connected. It is an early
              research platform and demonstration—not a signoff tool or a completed
              real-device validation program.
            </p>
            <div className="site-hero-actions">
              <a className="site-primary-link" href="#workflows">Explore checked workflows <span>↓</span></a>
              <a className="site-secondary-link" href={siteData.repository.url}>View source on GitHub <span>↗</span></a>
            </div>
          </div>
          <aside className="site-hero-panel">
            <div className="site-hero-panel-head"><span>Current public record</span><b>{siteData.recordDate}</b></div>
            <dl>
              <div><dt>Guided workflows</dt><dd>{siteData.workflows.length}<small>retained regression oracles</small></dd></div>
              <div><dt>Distributed record</dt><dd>{siteData.scaling.ndof.toLocaleString()}<small>degrees of freedom</small></dd></div>
              <div><dt>TSV validation scorecard</dt><dd>{blocked} / {notStarted}<small>blocked / not started</small></dd></div>
            </dl>
            <Boundary>{siteData.tsvScreening.claimBoundary}</Boundary>
          </aside>
        </section>

        <section className="site-principles" aria-label="Project principles">
          <article><span>01</span><div><strong>Trace the design object</strong><p>Stable IDs and provenance survive handoffs into analysis records.</p></div></article>
          <article><span>02</span><div><strong>Keep model levels explicit</strong><p>Component checks, examples, timings, and experimental comparisons are not collapsed into one label.</p></div></article>
          <article><span>03</span><div><strong>Fail closed</strong><p>Stateful examples emit results only after every accepted increment satisfies the solver rule.</p></div></article>
        </section>

        <section className="site-section" id="workflows">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Runnable examples</p><h2>Five paths from inputs to reviewable results</h2></div>
            <p>Every card links to its runner, retained numerical oracle, and full limitations. These checks show what the stated model computes; they are not experimental qualification.</p>
          </div>
          <div className="site-workflow-grid">
            {siteData.workflows.map((workflow) => <WorkflowCard workflow={workflow} key={workflow.id} />)}
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
            <p className="site-kicker"><span /> Real retained example output</p>
            <h2>Identity-preserving TSV screening</h2>
            <p>
              The project runner maps {siteData.tsvScreening.nDevices} synthetic device IDs
              through a classical Lamé far-field stress proxy and channel-oriented mobility
              proxies. A deterministic orientation action is then re-screened at a {thresholdPercent}% threshold.
            </p>
            <div className="site-feature-metrics">
              <article><span>Threshold violations</span><strong>{siteData.tsvScreening.baselineViolations} <i>→</i> {siteData.tsvScreening.optimizedViolations}</strong></article>
              <article><span>Peak |mobility proxy|</span><strong>{siteData.tsvScreening.baselinePeakAbsMobilityProxy.toFixed(4)} <i>→</i> {siteData.tsvScreening.optimizedPeakAbsMobilityProxy.toFixed(4)}</strong></article>
            </div>
            <Boundary>{siteData.tsvScreening.claimBoundary}</Boundary>
            <nav className="site-inline-links" aria-label="TSV screening evidence">
              <a href={publicAsset(siteData.tsvScreening.evidenceAsset)}>Evidence JSON</a>
              <a href={publicAsset(siteData.tsvScreening.csvAsset)}>Device CSV</a>
              <SourceLink path={siteData.tsvScreening.readmePath}>Method and limits</SourceLink>
              <SourceLink path={siteData.tsvScreening.expectedPath}>Regression oracle</SourceLink>
            </nav>
          </div>
        </section>

        <section className="site-scaling site-section" id="scaling">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Retained benchmark bundle</p><h2>{siteData.scaling.ndof.toLocaleString()}-DOF fixed-size solve</h2></div>
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

        <section className="site-section" id="figures">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> Project-authored figures</p><h2>Read the checks before reading the claims</h2></div>
            <p>These figures are generated from the repository's validation-guide records. Their role is to make component and toolchain evidence easier to inspect.</p>
          </div>
          <div className="site-figure-grid">
            {siteData.figures.map((figure) => (
              <figure key={figure.assetName}>
                <a href={repositoryFile(figure.sourcePath)}>
                  <img src={publicAsset(`repository-assets/validation-guide/${figure.assetName}`)} alt={figure.title} />
                </a>
                <figcaption><strong>{figure.title}</strong><p>{figure.caption}</p><span>Open source figure ↗</span></figcaption>
              </figure>
            ))}
          </div>
        </section>

        <section className="site-validation site-section" id="validation">
          <div className="site-section-heading">
            <div><p className="site-kicker"><span /> TSV device-validation program</p><h2>The open work remains part of the public record</h2></div>
            <p>The current scorecard has {blocked} blocked categories and {notStarted} not-started categories. “Blocked” means useful components exist but the named qualification evidence is incomplete.</p>
          </div>
          <div className="site-scorecard">
            {siteData.scorecard.categories.map((category) => <ScorecardRow category={category} key={category.id} />)}
          </div>
          <div className="site-scorecard-footer">
            <Boundary>Real-device claims require accepted 3-D fields, comparison curves, uncertainty, mesh/domain convergence, and EDA round-trip evidence. The synthetic screening example does not substitute for those records.</Boundary>
            <nav className="site-inline-links">
              <SourceLink path={siteData.scorecard.sourcePath}>Machine-readable scorecard</SourceLink>
              <SourceLink path={siteData.scorecard.evidenceGuidePath}>Evidence guide</SourceLink>
            </nav>
          </div>
        </section>

        <section className="site-workbench-invite">
          <div><p className="site-kicker"><span /> Interface direction</p><h2>A GUI for supervising models, runs, evidence, and decisions</h2></div>
          <p>The browser prototype demonstrates the interaction contract. Its public mode simulates run lifecycle events and does not execute CoupFE-EDA. A real local service exposes only approved workflow IDs and owns every command, path, and output directory.</p>
          <a href={`${import.meta.env.BASE_URL}?surface=workbench`}>Open the clearly labeled interface demonstration <span>→</span></a>
        </section>
      </main>

      <footer className="site-footer">
        <a className="site-brand" href={import.meta.env.BASE_URL}><Mark /><strong>CoupFE<span>–EDA</span></strong></a>
        <p>One open implementation of EDA-aware multiphysics workflows, built on CoupFE. The framework is extensible; the current evidence limits remain explicit.</p>
        <nav><a href={siteData.repository.url}>GitHub</a><SourceLink path="docs/README.md">Documentation</SourceLink><a href={publicAsset("legal/LICENSE")}>Code license</a><a href={publicAsset("legal/LICENSE-SCOPE.md")}>License scope</a><a href={publicAsset("legal/THIRD_PARTY.md")}>Third-party notices</a></nav>
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
