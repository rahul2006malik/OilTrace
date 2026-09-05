/**
 * PrintDossierView.tsx
 *
 * The actual courtroom-ready evidentiary dossier. Deliberately breaks from
 * the app's dark ECDIS tactical theme: this is a physical/printable legal
 * document intended for judges and naval commissions, so it renders as a
 * formal white-background, black-ink government instrument with serif body
 * text — matching real legal filings, not the cockpit UI.
 *
 * Isolation strategy: this component is always mounted in the DOM (so
 * `window.print()` has something to print) but hidden on screen and
 * revealed only inside `@media print`, using a scoped `visibility` trick
 * that hides everything else on the page without touching any shared
 * layout file outside this directory. All rules are scoped under
 * `.otd-print-root` to avoid leaking into the rest of the app.
 *
 * Fields not present in the shared `schemas.ts` contract (IMO, flag,
 * call sign, metocean current/wind vectors) are accepted as optional,
 * separately-typed props here rather than widening the shared schema —
 * per the note at the top of schemas.ts, that file must not drift.
 * Missing optional fields render as explicit "NOT RESOLVED" /
 * "UNAVAILABLE" labels rather than being silently omitted, consistent
 * with the app's data-provenance honesty requirement.
 */
import type {
  AttributionResult,
  Candidate,
  OriginEnsemble,
  ScenarioSummary,
  SlickDetection,
} from "../../types/schemas";

export interface DossierMetocean {
  currentSpeedMs: number;
  currentDirectionDeg: number;
  currentSource: string;
  windSpeedMs: number;
  windDirectionDeg: number;
  windSource: string;
}

export interface DossierSuspectRegistry {
  imo?: string | null;
  flag?: string | null;
  callSign?: string | null;
}

export interface PrintDossierViewProps {
  scenario: ScenarioSummary;
  slick: SlickDetection;
  origin: OriginEnsemble;
  attribution: AttributionResult;
  metocean?: DossierMetocean;
  primeSuspectRegistry?: DossierSuspectRegistry;
  caseId: string;
  checksum: string;
  generatedAt: string;
}

function formatUtc(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = d.getUTCDate().toString().padStart(2, "0");
  const month = d
    .toLocaleString("en-US", { month: "short", timeZone: "UTC" })
    .toUpperCase();
  const year = d.getUTCFullYear();
  const hh = d.getUTCHours().toString().padStart(2, "0");
  const mm = d.getUTCMinutes().toString().padStart(2, "0");
  return `${day} ${month} ${year}, ${hh}:${mm} UTC`;
}

function formatLonLat([lon, lat]: [number, number]): string {
  const lonLabel = `${Math.abs(lon).toFixed(4)}°${lon >= 0 ? "E" : "W"}`;
  const latLabel = `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? "N" : "S"}`;
  return `${lonLabel}, ${latLabel}`;
}

function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "N/A";
  return `${(value * 100).toFixed(digits)}%`;
}

function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return value.toFixed(3);
}

function topCandidate(attribution: AttributionResult): Candidate | null {
  if (attribution.candidates.length === 0) return null;
  return [...attribution.candidates].sort(
    (a, b) => (b.suspicion_score ?? -Infinity) - (a.suspicion_score ?? -Infinity)
  )[0];
}

export default function PrintDossierView({
  scenario,
  slick,
  origin,
  attribution,
  metocean,
  primeSuspectRegistry,
  caseId,
  checksum,
  generatedAt,
}: PrintDossierViewProps) {
  const suspect = topCandidate(attribution);

  return (
    <div className="otd-print-root">
      <style>{`
        .otd-print-root {
          display: none;
        }

        @media print {
          @page {
            size: A4;
            margin: 18mm 16mm;
          }

          html, body {
            background: #ffffff !important;
          }

          /* Hide everything else on the page, show only the dossier. */
          body * {
            visibility: hidden;
          }
          .otd-print-root, .otd-print-root * {
            visibility: visible;
          }
          .otd-print-root {
            display: block !important;
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
          }

          .otd-page {
            font-family: Georgia, "Times New Roman", serif;
            color: #111111;
            background: #ffffff;
            font-size: 10.5pt;
            line-height: 1.45;
          }

          .otd-mono {
            font-family: "IBM Plex Mono", "Courier New", monospace;
            font-variant-numeric: tabular-nums;
          }

          .otd-header {
            text-align: center;
            border-bottom: 2px solid #111111;
            padding-bottom: 10pt;
            margin-bottom: 14pt;
          }

          .otd-header .otd-emblem-line {
            font-size: 8.5pt;
            letter-spacing: 0.06em;
            color: #444444;
            margin-bottom: 3pt;
          }

          .otd-header h1 {
            font-size: 14pt;
            font-weight: 700;
            letter-spacing: 0.02em;
            margin: 4pt 0 2pt 0;
          }

          .otd-header .otd-subtitle {
            font-size: 9.5pt;
            color: #333333;
          }

          .otd-section {
            margin-bottom: 14pt;
            break-inside: avoid;
          }

          .otd-section h2 {
            font-family: "IBM Plex Mono", "Courier New", monospace;
            font-size: 9pt;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            border-bottom: 1px solid #999999;
            padding-bottom: 3pt;
            margin-bottom: 6pt;
          }

          table.otd-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 9.5pt;
          }

          table.otd-table td, table.otd-table th {
            border: 1px solid #bbbbbb;
            padding: 4pt 6pt;
            text-align: left;
            vertical-align: top;
          }

          table.otd-table th {
            background: #f2f2f2;
            font-weight: 700;
            width: 34%;
            font-family: "IBM Plex Mono", "Courier New", monospace;
            font-size: 8.5pt;
            letter-spacing: 0.03em;
          }

          .otd-caveat {
            border: 1px solid #111111;
            padding: 6pt 8pt;
            font-size: 9pt;
            margin-bottom: 8pt;
          }

          .otd-attestation {
            border-top: 1px solid #111111;
            padding-top: 10pt;
            margin-top: 18pt;
          }

          .otd-attestation p {
            margin: 0 0 8pt 0;
          }

          .otd-checksum-block {
            border: 1px solid #111111;
            padding: 8pt;
            font-size: 9pt;
            word-break: break-all;
          }

          .otd-footer {
            margin-top: 16pt;
            font-size: 8pt;
            color: #555555;
            border-top: 1px solid #cccccc;
            padding-top: 6pt;
          }
        }
      `}</style>

      <div className="otd-page">
        <header className="otd-header">
          <div className="otd-emblem-line">GOVERNMENT OF INDIA</div>
          <h1>
            NATIONAL TECHNICAL RESEARCH ORGANISATION (NTRO)
            <br />
            MARITIME OIL SPILL FORENSIC DOSSIER
          </h1>
          <div className="otd-subtitle otd-mono">
            CASE {caseId} &nbsp;//&nbsp; GENERATED {formatUtc(generatedAt)}
          </div>
        </header>

        {attribution.dark_vessel_alert && (
          <div className="otd-caveat">
            <strong>DARK VESSEL FINDING:</strong> no broadcasting AIS vessel
            met the attribution confidence threshold for this incident. The
            suspect profile below reflects the highest-ranked candidate
            despite falling under threshold and is retained for forensic
            logging, not presented as a confirmed attribution.
          </div>
        )}

        <section className="otd-section">
          <h2>Incident Metadata</h2>
          <table className="otd-table">
            <tbody>
              <tr>
                <th>Case ID</th>
                <td className="otd-mono">{caseId}</td>
              </tr>
              <tr>
                <th>Spill ID</th>
                <td className="otd-mono">{slick.spill_id}</td>
              </tr>
              <tr>
                <th>Scenario</th>
                <td>{scenario.name}</td>
              </tr>
              <tr>
                <th>Detected (UTC)</th>
                <td className="otd-mono">{formatUtc(slick.detected_at)}</td>
              </tr>
              <tr>
                <th>Coordinate Centroid</th>
                <td className="otd-mono">{formatLonLat(slick.centroid)}</td>
              </tr>
              <tr>
                <th>Observed Area</th>
                <td className="otd-mono">{slick.area_km2.toFixed(2)} km²</td>
              </tr>
              <tr>
                <th>Elongation Ratio</th>
                <td className="otd-mono">{slick.elongation_ratio.toFixed(2)}x</td>
              </tr>
              <tr>
                <th>Thickness Class</th>
                <td>{slick.thickness_class.toUpperCase()}</td>
              </tr>
              <tr>
                <th>Lookalike Suppressed</th>
                <td>{slick.lookalike_suppressed ? "TRUE" : "FALSE"}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section className="otd-section">
          <h2>Metocean &amp; Satellite Ground Truth</h2>
          <table className="otd-table">
            <tbody>
              <tr>
                <th>SAR Scene ID</th>
                <td className="otd-mono">{slick.source_scene_id}</td>
              </tr>
              <tr>
                <th>Ocean Surface Current</th>
                <td className="otd-mono">
                  {metocean
                    ? `${metocean.currentSpeedMs.toFixed(2)} m/s @ ${metocean.currentDirectionDeg
                        .toFixed(0)
                        .padStart(3, "0")}° (${metocean.currentSource})`
                    : "UNAVAILABLE"}
                </td>
              </tr>
              <tr>
                <th>10m Surface Wind</th>
                <td className="otd-mono">
                  {metocean
                    ? `${metocean.windSpeedMs.toFixed(2)} m/s @ ${metocean.windDirectionDeg
                        .toFixed(0)
                        .padStart(3, "0")}° (${metocean.windSource})`
                    : "UNAVAILABLE"}
                </td>
              </tr>
              <tr>
                <th>Estimated Spill Age</th>
                <td className="otd-mono">
                  ~{origin.age_estimate_hours.value.toFixed(0)}h (
                  {origin.age_estimate_hours.confidence_range[0].toFixed(0)}h–
                  {origin.age_estimate_hours.confidence_range[1].toFixed(0)}h
                  CI)
                </td>
              </tr>
              <tr>
                <th>Drift Ensemble Size</th>
                <td className="otd-mono">
                  {origin.ensemble_members.length} members
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <section className="otd-section">
          <h2>Prime Suspect Profile</h2>
          {suspect ? (
            <table className="otd-table">
              <tbody>
                <tr>
                  <th>Vessel Name</th>
                  <td>{suspect.vessel_name ?? "NOT RESOLVED"}</td>
                </tr>
                <tr>
                  <th>MMSI</th>
                  <td className="otd-mono">{suspect.vessel_id}</td>
                </tr>
                <tr>
                  <th>IMO</th>
                  <td className="otd-mono">
                    {primeSuspectRegistry?.imo ?? "NOT RESOLVED IN GFW REGISTRY"}
                  </td>
                </tr>
                <tr>
                  <th>Flag State</th>
                  <td>
                    {primeSuspectRegistry?.flag ?? "NOT RESOLVED IN GFW REGISTRY"}
                  </td>
                </tr>
                <tr>
                  <th>Call Sign</th>
                  <td className="otd-mono">
                    {primeSuspectRegistry?.callSign ?? "NOT RESOLVED"}
                  </td>
                </tr>
                <tr>
                  <th>Last Known Position</th>
                  <td className="otd-mono">
                    {suspect.last_known_position
                      ? formatLonLat(suspect.last_known_position)
                      : "N/A"}
                  </td>
                </tr>
                <tr>
                  <th>Suspicion Probability</th>
                  <td className="otd-mono">
                    {formatPercent(suspect.suspicion_score)}
                  </td>
                </tr>
                <tr>
                  <th>Bootstrap 95% CI</th>
                  <td className="otd-mono">
                    {suspect.confidence_interval
                      ? `[${formatPercent(
                          suspect.confidence_interval[0]
                        )} — ${formatPercent(suspect.confidence_interval[1])}]`
                      : "N/A"}
                  </td>
                </tr>
                <tr>
                  <th>Data Provenance</th>
                  <td className="otd-mono">
                    {suspect.data_provenance.toUpperCase()}
                  </td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p>NO CANDIDATE VESSELS WERE INDEXED FOR THIS INCIDENT.</p>
          )}
        </section>

        <section className="otd-section">
          <h2>Evidence Breakdown</h2>
          {suspect ? (
            <table className="otd-table">
              <thead>
                <tr>
                  <th>Factor</th>
                  <th style={{ width: "20%" }}>Score</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Distance from Drift Origin</td>
                  <td className="otd-mono">
                    {formatScore(suspect.evidence_trace.proximity_score)}
                  </td>
                </tr>
                <tr>
                  <td>Forward-Simulation Match (IoU)</td>
                  <td className="otd-mono">
                    {formatScore(suspect.evidence_trace.confession_match_score)}
                  </td>
                </tr>
                <tr>
                  <td>AIS Behavior Anomaly</td>
                  <td className="otd-mono">
                    {formatScore(suspect.evidence_trace.anomaly_score)}
                  </td>
                </tr>
                <tr>
                  <td>Vessel-Type Prior Likelihood</td>
                  <td className="otd-mono">
                    {formatScore(suspect.evidence_trace.vessel_type_prior)}
                  </td>
                </tr>
                <tr>
                  <td>
                    <strong>Dominant Evidence Factor</strong>
                  </td>
                  <td>{suspect.evidence_trace.dominant_factor}</td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p>N/A — NO SUSPECT VESSEL TO DECOMPOSE.</p>
          )}
        </section>

        <section className="otd-attestation">
          <p>
            I hereby certify that this evidentiary dossier was compiled
            directly from immutable satellite telemetry and hydrodynamic
            hindcast logs.
          </p>
          <div className="otd-checksum-block otd-mono">
            SHA-256 CHECKSUM: {checksum}
            <br />
            (Calculated client-side over raw GeoJSON &amp; attribution
            artifacts)
          </div>
        </section>

        <footer className="otd-footer">
          Compiled by the OilTrace automated forensic attribution pipeline
          (SIH26143 / NTRO). This dossier is a decision-support instrument
          and does not by itself establish legal chain of custody.
        </footer>
      </div>
    </div>
  );
}
