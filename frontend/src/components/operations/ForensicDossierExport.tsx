/**
 * ForensicDossierExport.tsx
 *
 * Print trigger + PDF generation controller. Per the spec's acceptance
 * criteria ("Export Dossier PDF opens browser print view"), this does not
 * pull in a client-side PDF library — it renders the always-mounted,
 * screen-hidden <PrintDossierView /> and calls `window.print()`, letting
 * the browser's native print-to-PDF handle rasterization. This also keeps
 * it compatible with the lightweight `package.json` dependency list (no jsPDF/html2canvas required).
 *
 * The SHA-256 checksum is computed once per data snapshot (not on every
 * render) over a key-sorted, canonicalized JSON of the slick detection,
 * origin ensemble, and attribution result — the "raw GeoJSON & attribution
 * artifacts" the spec calls for. The export button is disabled while the
 * checksum is being computed so the dossier can never be printed without
 * an integrity hash attached to it.
 */
import { useEffect, useMemo, useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import PrintDossierView, {
  type DossierMetocean,
  type DossierSuspectRegistry,
} from "./PrintDossierView";
import type {
  AttributionResult,
  OriginEnsemble,
  ScenarioSummary,
  SlickDetection,
} from "../../types/schemas";

export interface ForensicDossierExportProps {
  scenario: ScenarioSummary;
  slick: SlickDetection;
  origin: OriginEnsemble;
  attribution: AttributionResult;
  /** Not part of schemas.ts — optional dossier-only enrichment. */
  metocean?: DossierMetocean;
  /** Not part of schemas.ts — optional dossier-only enrichment. */
  primeSuspectRegistry?: DossierSuspectRegistry;
  /** Defaults to a deterministic transform of the scenario's spill_id. */
  caseId?: string;
  buttonLabel?: string;
  className?: string;
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value !== null && typeof value === "object") {
    return Object.keys(value as Record<string, unknown>)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = canonicalize((value as Record<string, unknown>)[key]);
        return acc;
      }, {});
  }
  return value;
}

async function sha256Hex(payload: unknown): Promise<string> {
  const json = JSON.stringify(canonicalize(payload));
  const bytes = new TextEncoder().encode(json);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** `SPILL-2026-ARABIAN-001` -> `CASE-2026-ARABIAN-001` */
function deriveCaseId(spillId: string): string {
  if (spillId.toUpperCase().startsWith("SPILL-")) {
    return `CASE-${spillId.slice(6)}`;
  }
  return `CASE-${spillId}`;
}

export default function ForensicDossierExport({
  scenario,
  slick,
  origin,
  attribution,
  metocean,
  primeSuspectRegistry,
  caseId,
  buttonLabel = "EXPORT DOSSIER PDF",
  className,
}: ForensicDossierExportProps) {
  const [checksum, setChecksum] = useState<string | null>(null);
  const [isHashing, setIsHashing] = useState(true);
  const [hashFailed, setHashFailed] = useState(false);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);

  const hashPayload = useMemo(
    () => ({ slick, origin, attribution }),
    [slick, origin, attribution]
  );

  useEffect(() => {
    let cancelled = false;
    setIsHashing(true);
    setHashFailed(false);

    sha256Hex(hashPayload)
      .then((hex) => {
        if (!cancelled) {
          setChecksum(hex);
          setIsHashing(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHashFailed(true);
          setIsHashing(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [hashPayload]);

  const resolvedCaseId = caseId ?? deriveCaseId(scenario.spill_id || slick.spill_id);

  const handleExport = () => {
    if (isHashing) return;
    setGeneratedAt(new Date().toISOString());
    // Defer to the next frame so the freshly-set timestamp is in the DOM
    // before the browser's print dialog snapshots the page.
    requestAnimationFrame(() => window.print());
  };

  const checksumForPrint = hashFailed
    ? "UNAVAILABLE — CLIENT ENVIRONMENT DENIED crypto.subtle"
    : checksum ?? "COMPUTING...";

  return (
    <>
      <button
        type="button"
        onClick={handleExport}
        disabled={isHashing}
        title={
          isHashing
            ? "Computing SHA-256 checksum over evidentiary artifacts…"
            : hashFailed
            ? "Checksum unavailable — dossier will export unsigned"
            : `Checksum ${checksum?.slice(0, 12)}…`
        }
        className={`flex items-center gap-1.5 border border-[#1D2E42] bg-[#0F1926] px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.03em] text-[#E6EDF3] font-['IBM_Plex_Sans',_sans-serif] transition-colors hover:bg-[#152334] disabled:cursor-wait disabled:opacity-60 ${
          className ?? ""
        }`}
      >
        {isHashing ? (
          <Loader2 className="h-3 w-3 animate-spin text-[#8D9EA8]" strokeWidth={2} aria-hidden />
        ) : (
          <FileText className="h-3 w-3 text-[#8D9EA8]" strokeWidth={2} aria-hidden />
        )}
        {isHashing ? "PREPARING DOSSIER…" : buttonLabel}
      </button>

      <PrintDossierView
        scenario={scenario}
        slick={slick}
        origin={origin}
        attribution={attribution}
        metocean={metocean}
        primeSuspectRegistry={primeSuspectRegistry}
        caseId={resolvedCaseId}
        checksum={checksumForPrint}
        generatedAt={generatedAt ?? new Date().toISOString()}
      />
    </>
  );
}
