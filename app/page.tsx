"use client";

import { useMemo, useState } from "react";
import { runAdaptiveRehearsal } from "../runtime/rehearsal.mjs";
import { IMMUTABLE_GOVERNOR, ROBINHOOD_MCP_URL, runRedTeamHarness } from "../runtime/governor.mjs";
import { NOT_YET_IMPLEMENTED, OPERATIONAL_STATUS } from "../runtime/status.mjs";

const CODEX_COMMAND = `codex mcp add robinhood-trading --url ${ROBINHOOD_MCP_URL}`;
const LOOP = [
  { step: "01", name: "Research", detail: "Point-in-time evidence" },
  { step: "02", name: "Forge", detail: "Competing hypotheses" },
  { step: "03", name: "Validate", detail: "Temporal falsification" },
  { step: "04", name: "Live", detail: "Governed capital only" },
  { step: "05", name: "Post-mortem", detail: "Forecast vs reality" },
  { step: "06", name: "Adapt", detail: "Controlled promotion" },
];

const PLANES = [
  { index: "01", title: "Robinhood authority", state: "READY FOR OAUTH", text: "Account, positions, buying power, tax lots, orders, reviews, and fills come from the official Trading MCP. No reconstructed brokerage state." },
  { index: "02", title: "Research intelligence", state: "PARTIAL", text: "Point-in-time feature contracts and research isolation are designed. Live feature adapters wait for authenticated Robinhood schemas." },
  { index: "03", title: "Strategy forge", state: "BUILT", text: "Adaptive candidate generation, competing strategy families, temporal folds, an untouched holdout, and a permanent rejection ledger." },
  { index: "04", title: "Portfolio constructor", state: "CORE BUILT", text: "Geometric-growth objective, uncertainty haircuts, endogenous cash, transaction costs, and concentration that must earn its way in." },
  { index: "05", title: "Risk governor", state: "BUILT + TESTED", text: "A deterministic fail-closed authority that the research loop cannot rewrite, weaken, or route around." },
  { index: "06", title: "Execution enclave", state: "LOCKED", text: "The research host can review orders but cannot place or cancel them. Live execution remains a separate unimplemented security boundary." },
  { index: "07", title: "Decision audit", state: "SCHEMA BUILT", text: "Every future forecast, alternative, intervention, review, order, fill, outcome, and model version is designed to be point-in-time reconstructable." },
  { index: "08", title: "Control plane", state: "BUILT", text: "Operational truth, research diagnostics, governor tests, connection instructions, deployment gates, and explicit limitations." },
];

const MODEL_STACK = [
  ["Bayesian cross-section", "Posterior return distributions and estimation-risk shrinkage", "DESIGNED"],
  ["Penalized linear baseline", "Stable factor/revision effects with sparse feature selection", "DESIGNED"],
  ["Nonlinear challenger", "Interactions only if nested out-of-sample log score improves", "NOT YET"],
  ["Regime ensemble", "Change-point and state models; regime uncertainty never hidden", "DESIGNED"],
  ["Portfolio optimizer", "Robust expected-log growth after costs and tail constraints", "CORE BUILT"],
  ["Meta allocator", "Model influence earned by rolling out-of-sample evidence", "NOT YET"],
];

const fmtPct = (value: number | undefined, digits = 1) => value === undefined || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(digits)}%`;
function StatusPill({ state }: { state: string }) {
  const tone = state === "YES" || state.includes("BUILT") || state === "CORE BUILT" ? "good" : state === "NO" || state === "LOCKED" || state === "NOT YET" ? "bad" : "warn";
  return <span className={`status-pill ${tone}`}>{state}</span>;
}

export default function Home() {
  const [rehearsal, setRehearsal] = useState<ReturnType<typeof runAdaptiveRehearsal> | null>(null);
  const [redTeam, setRedTeam] = useState<ReturnType<typeof runRedTeamHarness> | null>(null);
  const [running, setRunning] = useState<"research" | "risk" | "">("");
  const [copied, setCopied] = useState("");

  const machineState = rehearsal?.champion ? "SHADOW CANDIDATE" : rehearsal ? "NO_TRADE" : "LAB LOCKED";
  const summary = useMemo(() => ({
    configs: rehearsal?.candidateCount ?? 0,
    killRate: rehearsal?.killRate ?? 0,
    survivors: rehearsal?.survivors ?? 0,
    folds: rehearsal?.foldCount ?? 0,
  }), [rehearsal]);

  const copy = async (text: string, label: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(label); }
    catch { setCopied("Copy blocked"); }
    setTimeout(() => setCopied(""), 1700);
  };

  const runResearch = () => {
    setRunning("research");
    window.setTimeout(() => { setRehearsal(runAdaptiveRehearsal()); setRunning(""); }, 80);
  };

  const runRisk = () => {
    setRunning("risk");
    window.setTimeout(() => { setRedTeam(runRedTeamHarness()); setRunning(""); }, 80);
  };

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="EdgeLoop home"><b>EL</b><span><strong>EdgeLoop</strong><small>ROBINHOOD-NATIVE PORTFOLIO INTELLIGENCE</small></span></a>
        <nav aria-label="Page sections">
          <a href="#machine">Machine</a><a href="#validation">Validation</a><a href="#governor">Governor</a><a href="#status">Status</a><a href="#connect">Connect</a>
        </nav>
        <div className="mode-chip"><i /> LAB LOCKED</div>
      </header>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">QUANTITATIVE CONTROL SYSTEM · REVISION 02</p>
          <h1>Autonomous<br /><em>portfolio</em><br />intelligence.</h1>
          <p className="hero-deck">A Robinhood-native machine for maximizing long-run geometric growth while making permanent capital impairment increasingly difficult.</p>
          <div className="hero-actions">
            <button className="primary" onClick={runResearch} disabled={!!running}>{running === "research" ? "RUNNING TEMPORAL FOLDS…" : "RUN RESEARCH REHEARSAL"}</button>
            <a className="secondary" href="#connect">CONNECT ROBINHOOD</a>
          </div>
          <div className="truth-line"><span>NO API KEY</span><span>OAUTH REQUIRED</span><span>NO LIVE ORDERS</span><span>NO FAKE HOLDINGS</span></div>
        </div>

        <div className="loop-console" aria-label="Six-stage EdgeLoop operating cycle">
          <div className="orbit">
            {LOOP.map((item, index) => <div className={`orbit-node node-${index}`} key={item.step}><b>{item.step}</b><span>{item.name}</span></div>)}
            <div className="orbit-core"><small>SYSTEM STATE</small><strong>{machineState}</strong><span>{rehearsal ? `${summary.configs} hypotheses tested` : "Awaiting authenticated evidence"}</span></div>
          </div>
          <p>RESEARCH → FORGE → VALIDATE → LIVE → POST-MORTEM → ADAPT</p>
        </div>

        <aside className="connection-card">
          <div className="card-kicker"><span>ROBINHOOD MCP</span><b>NOT CONNECTED</b></div>
          <h2>Brokerage truth starts after OAuth.</h2>
          <p>The hosted interface stores no Robinhood password, API key, OAuth token, account number, or reconstructed portfolio.</p>
          <dl>
            <div><dt>Portfolio value</dt><dd>—</dd></div>
            <div><dt>Buying power</dt><dd>—</dd></div>
            <div><dt>Positions</dt><dd>—</dd></div>
            <div><dt>Open orders</dt><dd>—</dd></div>
          </dl>
          <button className="command" onClick={() => copy(CODEX_COMMAND, "MCP command")}><span>$ {CODEX_COMMAND}</span><b>{copied === "MCP command" ? "COPIED" : "COPY"}</b></button>
          <small>Desktop authentication opens Robinhood’s Agentic-account onboarding.</small>
        </aside>
      </section>

      <section className="telemetry">
        <div className="shell telemetry-grid">
          <div><span>CONFIGS</span><strong>{summary.configs.toLocaleString()}</strong><small>adaptive, not fixed</small></div>
          <div><span>KILL RATE</span><strong>{fmtPct(summary.killRate)}</strong><small>rejection is success</small></div>
          <div><span>SURVIVORS</span><strong>{summary.survivors}</strong><small>holdout-gated</small></div>
          <div><span>TEMPORAL FOLDS</span><strong>{summary.folds}</strong><small>anchored walk-forward</small></div>
          <div><span>GOVERNOR</span><strong>v{IMMUTABLE_GOVERNOR.version}</strong><small>immutable to learning</small></div>
          <div><span>EXECUTION</span><strong className="red">DISABLED</strong><small>placement tool absent</small></div>
        </div>
      </section>

      <section className="section shell" id="machine">
        <div className="section-head">
          <div><p className="eyebrow">SYSTEM ARCHITECTURE</p><h2>One portfolio.<br />Eight isolated planes.</h2></div>
          <p>The intelligence loop may learn. The brokerage boundary, account binding, governor, and deployment permissions may not silently evolve with it.</p>
        </div>
        <div className="plane-grid">
          {PLANES.map((plane) => <article key={plane.index}><div><span>{plane.index}</span><StatusPill state={plane.state} /></div><h3>{plane.title}</h3><p>{plane.text}</p></article>)}
        </div>
      </section>

      <section className="math-section" id="validation">
        <div className="shell">
          <div className="section-head inverse">
            <div><p className="eyebrow">MATHEMATICAL CORE</p><h2>Optimize survival-adjusted compounding.</h2></div>
            <p>Raw return is not the objective. EdgeLoop compares entire posterior outcome distributions after uncertainty, implementation costs, liquidity, tail behavior, and portfolio interaction.</p>
          </div>
          <div className="formula-strip">
            <article><span>01 · OBJECTIVE</span><code>max median[log(1 + w′r)] − U − Tail − Cost</code><p>Growth is rewarded only after uncertainty and implementation drag.</p></article>
            <article><span>02 · UNCERTAINTY</span><code>μ̃ = E[μ | data], score ∝ lower credible bound</code><p>Concentration requires evidence, not a noisy point estimate.</p></article>
            <article><span>03 · RISK</span><code>Σ̃ = shrink(Σsample) + stressed correlation states</code><p>Sample covariance is stabilized before it touches capital.</p></article>
            <article><span>04 · PROMOTION</span><code>DSR + PBO + fold stability + untouched holdout</code><p>The best-looking backtest can still be killed.</p></article>
          </div>

          <div className="lab-grid">
            <article className="lab-card">
              <div className="card-title"><div><p className="eyebrow">RESEARCH REHEARSAL</p><h3>Adaptive temporal tournament</h3></div><StatusPill state={rehearsal ? (rehearsal.champion ? "CANDIDATE" : "NO_TRADE") : "NOT RUN"} /></div>
              <p className="muted">The fixture is sanitized and deterministic. It tests machinery only; it never impersonates Robinhood data or an investable result.</p>
              <div className="lab-metrics">
                <div><span>Candidates</span><b>{rehearsal?.candidateCount ?? "—"}</b></div>
                <div><span>Walk-forward folds</span><b>{rehearsal?.foldCount ?? "—"}</b></div>
                <div><span>Untouched holdout</span><b>{rehearsal ? `${rehearsal.holdoutObservations}d` : "—"}</b></div>
                <div><span>PBO</span><b>{fmtPct(rehearsal?.pbo)}</b></div>
              </div>
              <div className="decision-box">
                <span>REHEARSAL DECISION</span><strong>{rehearsal?.champion ? rehearsal.champion.id : rehearsal ? "NO_TRADE" : "NOT RUN"}</strong>
                <p>{rehearsal?.note ?? "Run the deterministic tournament to exercise the validation and kill-ledger path."}</p>
              </div>
              <button className="acid" onClick={runResearch} disabled={!!running}>{running === "research" ? "FALSIFYING…" : "RUN ADAPTIVE TOURNAMENT"}</button>
            </article>

            <article className="lab-card kill-card">
              <div className="card-title"><div><p className="eyebrow">PERMANENT MEMORY</p><h3>Kill ledger</h3></div><span>{rehearsal?.killLedger.length ?? 0} SHOWN</span></div>
              <div className="kill-list">
                {(rehearsal?.killLedger ?? []).slice(0, 7).map((entry) => <div key={entry.id}><b>{entry.id}</b><span>{entry.family}</span><p>{entry.reasons.join(" · ")}</p></div>)}
                {!rehearsal && <div className="empty"><p>No hypotheses have been evaluated in this browser session.</p></div>}
              </div>
            </article>
          </div>

          <div className="model-table">
            <div className="table-head"><span>MODEL FAMILY</span><span>ROLE</span><span>TRUTHFUL STATE</span></div>
            {MODEL_STACK.map(([name, role, state]) => <div key={name}><b>{name}</b><p>{role}</p><StatusPill state={state} /></div>)}
          </div>
        </div>
      </section>

      <section className="section shell" id="governor">
        <div className="section-head">
          <div><p className="eyebrow">INDEPENDENT RISK GOVERNOR</p><h2>The model proposes.<br />The governor decides.</h2></div>
          <p>Every live action must survive deterministic checks against fresh Robinhood state. A research model cannot argue its way around a hard block.</p>
        </div>
        <div className="governor-grid">
          <article className="governor-console">
            <div className="console-top"><span>POLICY / {IMMUTABLE_GOVERNOR.version}</span><b>FAIL CLOSED</b></div>
            {[
              ["Account binding", "Dedicated Agentic account only"],
              ["Data integrity", "Fresh + reconciled + schema-hashed"],
              ["Instrument scope", "Long equities / ETFs only"],
              ["Capital", "Owner ceiling required; margin forbidden"],
              ["Decision", "Positive net log utility after uncertainty"],
              ["Execution", "Review → place → reconcile; never infer fill"],
              ["Concurrency", "Idempotency + open-order conflict checks"],
              ["Emergency", "Independent kill switch + drawdown breaker"],
            ].map(([label, value]) => <div className="rule" key={label}><span>{label}</span><b>{value}</b></div>)}
          </article>

          <article className="attack-card">
            <div className="attack-score"><span>ADVERSARIAL HARNESS</span><strong>{redTeam ? `${redTeam.passed}/${redTeam.total}` : "—"}</strong><small>{redTeam ? (redTeam.failed ? "FAILURES FOUND" : "EXPECTED OUTCOMES VERIFIED") : "NOT RUN IN THIS SESSION"}</small></div>
            <div className="attack-bars">
              {(redTeam?.results ?? []).slice(0, 9).map((result) => <div key={result.name}><i className={result.passed ? "pass" : "fail"} /><span>{result.name}</span><b>{result.observed}</b></div>)}
            </div>
            <button className="primary dark" onClick={runRisk} disabled={!!running}>{running === "risk" ? "ATTACKING…" : "RUN RED-TEAM HARNESS"}</button>
          </article>
        </div>
      </section>

      <section className="truth-section" id="status">
        <div className="shell">
          <div className="section-head inverse">
            <div><p className="eyebrow">OPERATIONAL TRUTH</p><h2>No autonomy by adjective.</h2></div>
            <p>Each label below is evidence-gated. A beautiful interface, a passed backtest, or a copied MCP URL does not make the system connected or live.</p>
          </div>
          <div className="status-matrix">
            {OPERATIONAL_STATUS.map((item) => <article key={item.label}><div><h3>{item.label}</h3><StatusPill state={item.state} /></div><p>{item.detail}</p></article>)}
          </div>
          <div className="not-built">
            <div><p className="eyebrow">NOT YET IMPLEMENTED</p><h3>What still separates a research machine from real autonomy.</h3></div>
            <ol>{NOT_YET_IMPLEMENTED.map((item, index) => <li key={item}><span>{String(index + 1).padStart(2, "0")}</span>{item}</li>)}</ol>
          </div>
        </div>
      </section>

      <section className="connect-section shell" id="connect">
        <div className="connect-copy">
          <p className="eyebrow">OWNER ACTION REQUIRED</p>
          <h2>Connect the official Robinhood MCP.</h2>
          <p>Robinhood requires desktop OAuth and personally completed Agentic-account onboarding. EdgeLoop never asks for your password, two-factor code, account number, or an API key.</p>
          <a href="https://robinhood.com/us/en/support/articles/agentic-trading-overview/" target="_blank" rel="noreferrer">OPEN ROBINHOOD’S OFFICIAL SETUP GUIDE ↗</a>
        </div>
        <div className="steps">
          <article><b>01</b><div><h3>Add the server</h3><code>{CODEX_COMMAND}</code><button onClick={() => copy(CODEX_COMMAND, "setup")}>{copied === "setup" ? "COPIED" : "COPY COMMAND"}</button></div></article>
          <article><b>02</b><div><h3>Authenticate on desktop</h3><p>Run <code>codex mcp login robinhood-trading</code>, complete Robinhood OAuth, and finish the dedicated Agentic-account onboarding.</p></div></article>
          <article><b>03</b><div><h3>Begin read-only shadow evidence</h3><p>Discover live tool schemas, bind the exact Agentic account, reconcile state, and accumulate shadow decisions. Live placement remains disabled.</p></div></article>
        </div>
      </section>

      <section className="source-section">
        <div className="shell source-grid">
          <div><p className="eyebrow">PRIMARY SOURCE LEDGER</p><h2>Methods with provenance.</h2></div>
          <div className="sources">
            <a href="https://robinhood.com/us/en/support/articles/agentic-trading-overview/" target="_blank" rel="noreferrer"><b>Robinhood</b><span>Agentic Trading account, OAuth, access scope, and risk disclosure</span></a>
            <a href="https://robinhood.com/us/en/support/articles/trading-with-your-agent/" target="_blank" rel="noreferrer"><b>Robinhood</b><span>Current Trading MCP account, market, equity, review, and order tools</span></a>
            <a href="https://learn.chatgpt.com/docs/extend/mcp?surface=cli" target="_blank" rel="noreferrer"><b>OpenAI Docs</b><span>Codex MCP OAuth, project config, tool allowlists, and approval controls</span></a>
            <a href="https://learn.chatgpt.com/docs/automations" target="_blank" rel="noreferrer"><b>OpenAI Docs</b><span>Scheduled task runtime, local-project requirements, and unattended permissions</span></a>
            <a href="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253" target="_blank" rel="noreferrer"><b>Bailey et al.</b><span>Probability of Backtest Overfitting</span></a>
            <a href="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551" target="_blank" rel="noreferrer"><b>Bailey & López de Prado</b><span>Deflated Sharpe Ratio and multiple-selection bias</span></a>
            <a href="https://www.ledoit.net/honey.pdf" target="_blank" rel="noreferrer"><b>Ledoit & Wolf</b><span>Covariance shrinkage for portfolio optimization</span></a>
          </div>
        </div>
      </section>

      <footer><div className="shell"><div className="brand"><b>EL</b><span><strong>EdgeLoop 2.0</strong><small>ROBINHOOD-NATIVE · LAB LOCKED</small></span></div><p>Capital decisions may eventually be autonomous. Accountability never is.</p></div></footer>
    </main>
  );
}
