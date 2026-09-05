/**
 * LiveAisMonitor.tsx
 *
 * Compact status widget for the AIS ingestion feed. Runs in one of two
 * modes:
 *
 *   - "simulated": no real WS endpoint configured. Emits realistic,
 *     gently-jittered telemetry around the flagship demo baseline
 *     (18 pings/min, 1,642 vessels) so the widget doesn't look frozen,
 *     without pretending to be a live feed it isn't.
 *   - "live": a WS endpoint was supplied (via the `wsUrl` prop or the
 *     `VITE_AIS_WS_URL` env var). Connects for real, tracks a rolling
 *     60-second ping window to derive pings/min, and reconnects with
 *     exponential-ish backoff on drop.
 *
 * Per the app's provenance manifesto ("Aggressive Ambient Provenance" —
 * never silently pass off synthetic data as real), the widget always shows
 * a small LIVE FEED / SIMULATED badge regardless of which mode it's in.
 *
 * No pulsing/glow/animated dial treatments — the status dot is a static,
 * color-coded indicator only.
 */
import { useEffect, useRef, useState } from "react";
import { WifiOff } from "lucide-react";

export type AisFeedMode = "simulated" | "live";
export type AisConnectionStatus =
  | "connecting"
  | "streaming"
  | "reconnecting"
  | "offline";

export interface LiveAisMonitorProps {
  /**
   * Explicit WS URL override. Falls back to `import.meta.env.VITE_AIS_WS_URL`.
   * When neither is set, the widget runs on the labeled simulated feed.
   */
  wsUrl?: string;
  className?: string;
}

interface AisFeedState {
  mode: AisFeedMode;
  status: AisConnectionStatus;
  pingsPerMinute: number;
  vesselCount: number;
}

const SIM_BASE_PINGS = 18;
const SIM_BASE_VESSELS = 1642;
const SIM_TICK_MS = 4000;
const RECONNECT_BACKOFF_MS = [1000, 2000, 5000, 10000, 15000];
const PING_WINDOW_MS = 60_000;

function resolveWsUrl(explicit?: string): string | null {
  if (explicit) return explicit;
  // Vite exposes env vars on import.meta.env; cast defensively since this
  // file may be type-checked outside a full Vite project setup.
  const envUrl = (import.meta as unknown as { env?: Record<string, string> })
    ?.env?.VITE_AIS_WS_URL;
  return typeof envUrl === "string" && envUrl.length > 0 ? envUrl : null;
}

export default function LiveAisMonitor({ wsUrl, className }: LiveAisMonitorProps) {
  const resolvedUrl = resolveWsUrl(wsUrl);

  const [state, setState] = useState<AisFeedState>({
    mode: resolvedUrl ? "live" : "simulated",
    status: resolvedUrl ? "connecting" : "streaming",
    pingsPerMinute: SIM_BASE_PINGS,
    vesselCount: SIM_BASE_VESSELS,
  });

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingWindowRef = useRef<number[]>([]);

  // --- Simulated feed -------------------------------------------------
  useEffect(() => {
    if (resolvedUrl) return; // real feed handles state below
    const interval = setInterval(() => {
      setState((prev) => ({
        ...prev,
        pingsPerMinute: Math.max(
          0,
          Math.round(SIM_BASE_PINGS + (Math.random() * 6 - 3))
        ),
        vesselCount: Math.max(
          0,
          SIM_BASE_VESSELS + Math.round(Math.random() * 20 - 10)
        ),
      }));
    }, SIM_TICK_MS);
    return () => clearInterval(interval);
  }, [resolvedUrl]);

  // --- Real feed --------------------------------------------------------
  useEffect(() => {
    if (!resolvedUrl) return;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setState((prev) => ({
        ...prev,
        status: prev.status === "streaming" ? "reconnecting" : "connecting",
      }));

      const socket = new WebSocket(resolvedUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        reconnectAttemptRef.current = 0;
        setState((prev) => ({ ...prev, status: "streaming" }));
      };

      socket.onmessage = (event) => {
        const now = Date.now();
        pingWindowRef.current.push(now);
        pingWindowRef.current = pingWindowRef.current.filter(
          (t) => now - t <= PING_WINDOW_MS
        );

        let vesselCount: number | undefined;
        try {
          const parsed = JSON.parse(event.data);
          if (typeof parsed?.vessel_count === "number") {
            vesselCount = parsed.vessel_count;
          } else if (typeof parsed?.indexed_vessels === "number") {
            vesselCount = parsed.indexed_vessels;
          }
        } catch {
          // Raw/non-JSON AIS frames still count toward the ping rate.
        }

        setState((prev) => ({
          ...prev,
          pingsPerMinute: pingWindowRef.current.length,
          vesselCount: vesselCount ?? prev.vesselCount,
        }));
      };

      socket.onerror = () => {
        socket.close();
      };

      socket.onclose = () => {
        if (cancelled) return;
        setState((prev) => ({ ...prev, status: "reconnecting" }));
        const attempt = reconnectAttemptRef.current;
        const delay =
          RECONNECT_BACKOFF_MS[
            Math.min(attempt, RECONNECT_BACKOFF_MS.length - 1)
          ];
        reconnectAttemptRef.current += 1;
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      socketRef.current?.close();
    };
  }, [resolvedUrl]);

  const dotColor =
    state.status === "streaming"
      ? state.mode === "live"
        ? "#38BDF8" // real_aisstream_live
        : "#927B56" // synthetic/simulated brass
      : state.status === "connecting" || state.status === "reconnecting"
      ? "#F59E0B"
      : "#526573";

  const statusLabel =
    state.status === "streaming"
      ? "LIVE STREAMING"
      : state.status === "connecting"
      ? "CONNECTING..."
      : state.status === "reconnecting"
      ? "RECONNECTING..."
      : "OFFLINE";

  return (
    <div
      className={`flex items-center gap-3 border border-[#1D2E42] bg-[#0F1926] px-3 py-1.5 text-[11px] text-[#E6EDF3] font-['IBM_Plex_Mono',_monospace] ${
        className ?? ""
      }`}
    >
      <span className="flex items-center gap-1.5">
        {state.status === "offline" ? (
          <WifiOff className="h-3 w-3 text-[#526573]" strokeWidth={2} aria-hidden />
        ) : (
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: dotColor }}
            aria-hidden
          />
        )}
        <span className="uppercase tracking-[0.02em] text-[#8D9EA8] font-['IBM_Plex_Sans',_sans-serif]">
          AIS FEED:
        </span>
        <span className="uppercase tracking-[0.02em]">{statusLabel}</span>
      </span>

      {state.status === "streaming" && (
        <>
          <span className="text-[#526573]">//</span>
          <span className="tabular-nums">{state.pingsPerMinute} PINGS/MIN</span>
        </>
      )}

      <span className="text-[#526573]">//</span>
      <span className="tabular-nums">
        {state.vesselCount.toLocaleString("en-US")} VESSELS IN SPATIO-TEMPORAL
        BUFFER
      </span>

      <span
        className={`ml-1 rounded-none border px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-[0.04em] font-['IBM_Plex_Sans',_sans-serif] ${
          state.mode === "live"
            ? "border-[#38BDF8]/40 text-[#38BDF8]"
            : "border-[#927B56]/50 text-[#927B56]"
        }`}
      >
        {state.mode === "live" ? "LIVE FEED" : "SIMULATED"}
      </span>
    </div>
  );
}
