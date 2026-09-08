import React, { useEffect, useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import {
  Play, Pause, RotateCcw, FastForward, Rewind, Layers,
  Clock, History, ArrowRight, ArrowLeft, Target, Disc
} from 'lucide-react';

export const TemporalScrubber: React.FC = () => {
  const {
    playbackTimeHours,
    isPlaying,
    playbackSpeed,
    setPlaybackTime,
    togglePlayback,
    setPlaybackSpeed,
    detection,
    showEnsembleBuildup,
    toggleEnsembleBuildup,
    driftRun,
    attribution,
    getSelectedCandidate,
  } = useOilTraceStore();

  const [playDirection, setPlayDirection] = useState<'forward' | 'backward'>('backward');
  const leadCandidate = getSelectedCandidate();

  // High-performance decoupled slider state: 60/120Hz native slider thumb + throttled map engine
  const [localTime, setLocalTime] = useState<number>(playbackTimeHours);
  const isDraggingRef = React.useRef<boolean>(false);
  const lastSyncTimeRef = React.useRef<number>(0);
  const throttleTimeoutRef = React.useRef<number | null>(null);
  const pendingValueRef = React.useRef<number | null>(null);

  // Sync localTime when playbackTimeHours updates externally (playback animation loop or jump buttons)
  useEffect(() => {
    if (!isDraggingRef.current) {
      setLocalTime(playbackTimeHours);
    }
  }, [playbackTimeHours]);

  // High performance throttle: updates local UI immediately, but throttles store/MapLibre updates to ~25fps (40ms)
  // This completely eliminates WebGL worker queue bottlenecks, GC spikes, and slider input lag!
  const handleSliderChange = (newVal: number) => {
    // 1. Instant local state update for silky 60-144 FPS slider knob tracking
    setLocalTime(newVal);
    pendingValueRef.current = newVal;

    const now = performance.now();
    const elapsed = now - lastSyncTimeRef.current;

    // Throttle map updates to at most once every 40ms (25 FPS is visually continuous for advection)
    if (elapsed >= 40) {
      lastSyncTimeRef.current = now;
      if (throttleTimeoutRef.current !== null) {
        clearTimeout(throttleTimeoutRef.current);
        throttleTimeoutRef.current = null;
      }
      setPlaybackTime(newVal);
    } else if (throttleTimeoutRef.current === null) {
      // Trailing edge sync to ensure the latest scrubbed position is guaranteed to be applied
      throttleTimeoutRef.current = window.setTimeout(() => {
        throttleTimeoutRef.current = null;
        lastSyncTimeRef.current = performance.now();
        if (pendingValueRef.current !== null) {
          setPlaybackTime(pendingValueRef.current);
        }
      }, 40 - elapsed);
    }
  };

  const handlePointerDown = (e: React.PointerEvent<HTMLInputElement>) => {
    isDraggingRef.current = true;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {}
    if (isPlaying) togglePlayback();
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLInputElement>) => {
    isDraggingRef.current = false;
    try {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    } catch {}

    // Flush any pending throttled value immediately upon release
    if (throttleTimeoutRef.current !== null) {
      clearTimeout(throttleTimeoutRef.current);
      throttleTimeoutRef.current = null;
    }
    if (pendingValueRef.current !== null) {
      setPlaybackTime(pendingValueRef.current);
    }
  };

  // Window pointer safety listener so isDraggingRef never gets stuck
  useEffect(() => {
    const handleGlobalUp = () => {
      if (isDraggingRef.current) {
        isDraggingRef.current = false;
        if (throttleTimeoutRef.current !== null) {
          clearTimeout(throttleTimeoutRef.current);
          throttleTimeoutRef.current = null;
        }
        if (pendingValueRef.current !== null) {
          setPlaybackTime(pendingValueRef.current);
        }
      }
    };
    window.addEventListener('pointerup', handleGlobalUp);
    window.addEventListener('mouseup', handleGlobalUp);
    return () => {
      window.removeEventListener('pointerup', handleGlobalUp);
      window.removeEventListener('mouseup', handleGlobalUp);
      if (throttleTimeoutRef.current !== null) {
        clearTimeout(throttleTimeoutRef.current);
      }
    };
  }, [setPlaybackTime]);

  // Dynamically derive the scenario's true discharge/onset window
  const dischargeHour = React.useMemo(() => {
    if (driftRun?.origin_zone?.estimated_onset_time && detection?.detected_at) {
      const onsetMs = new Date(driftRun.origin_zone.estimated_onset_time).getTime();
      const detMs = new Date(detection.detected_at).getTime();
      if (!isNaN(onsetMs) && !isNaN(detMs)) {
        const diffHours = (onsetMs - detMs) / (3600 * 1000);
        if (diffHours >= -48.0 && diffHours <= -0.5) {
          return Math.round(diffHours * 10) / 10;
        }
      }
    }
    // Check candidate reconstructed points
    if (leadCandidate?.ais_positions && detection?.detected_at) {
      const reconPt = leadCandidate.ais_positions.find((p) => p.is_reconstructed);
      if (reconPt) {
        const ptMs = new Date(reconPt.timestamp).getTime();
        const detMs = new Date(detection.detected_at).getTime();
        if (!isNaN(ptMs) && !isNaN(detMs)) {
          const diffHours = (ptMs - detMs) / (3600 * 1000);
          if (diffHours >= -48.0 && diffHours <= -0.5) {
            return Math.round(diffHours * 10) / 10;
          }
        }
      }
    }
    return -20.0;
  }, [driftRun, detection, leadCandidate]);

  // Pre-sort AIS positions once per candidate change rather than sorting on every slider tick
  const sortedAisPositions = React.useMemo(() => {
    if (!leadCandidate?.ais_positions) return [];
    return [...leadCandidate.ais_positions].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }, [leadCandidate]);

  // Dynamically detect if suspect vessel is currently in an AIS blackout gap at scrubbed time
  const isCurrentlyInGap = React.useMemo(() => {
    if (sortedAisPositions.length < 2 || !detection?.detected_at) return false;
    const detMs = new Date(detection.detected_at).getTime();
    const currentMs = detMs + localTime * 3600 * 1000;
    for (let i = 0; i < sortedAisPositions.length - 1; i++) {
      const t1 = new Date(sortedAisPositions[i].timestamp).getTime();
      const t2 = new Date(sortedAisPositions[i + 1].timestamp).getTime();
      if (currentMs >= t1 && currentMs <= t2) {
        return Boolean(sortedAisPositions[i].is_reconstructed || sortedAisPositions[i + 1].is_reconstructed);
      }
    }
    return false;
  }, [sortedAisPositions, detection, localTime]);

  // Dynamically compute the overall AIS blackout gap range for track marking
  const aisGapRange = React.useMemo(() => {
    if (sortedAisPositions.length < 2 || !detection?.detected_at) return null;
    const detMs = new Date(detection.detected_at).getTime();
    let minGapHour = Infinity;
    let maxGapHour = -Infinity;
    let found = false;

    for (let i = 0; i < sortedAisPositions.length - 1; i++) {
      const p1 = sortedAisPositions[i];
      const p2 = sortedAisPositions[i + 1];
      if (p1.is_reconstructed || p2.is_reconstructed) {
        found = true;
        const h1 = (new Date(p1.timestamp).getTime() - detMs) / (3600 * 1000);
        const h2 = (new Date(p2.timestamp).getTime() - detMs) / (3600 * 1000);
        minGapHour = Math.min(minGapHour, h1, h2);
        maxGapHour = Math.max(maxGapHour, h1, h2);
      }
    }

    if (found && minGapHour >= -48.0 && maxGapHour <= 0.0) {
      return { start: Math.max(-48.0, minGapHour), end: Math.min(0.0, maxGapHour) };
    }
    return null;
  }, [sortedAisPositions, detection]);

  // Derive candidate speed during discharge window
  const dischargeSpeedKnots = React.useMemo(() => {
    if (!leadCandidate?.ais_positions || !detection?.detected_at) return 6.1;
    const detMs = new Date(detection.detected_at).getTime();
    const targetMs = detMs + dischargeHour * 3600 * 1000;
    let closestPt = leadCandidate.ais_positions[0];
    let minDiff = Infinity;
    for (const p of leadCandidate.ais_positions) {
      const diff = Math.abs(new Date(p.timestamp).getTime() - targetMs);
      if (diff < minDiff) {
        minDiff = diff;
        closestPt = p;
      }
    }
    return closestPt && typeof closestPt.sog === 'number' ? closestPt.sog : 6.1;
  }, [leadCandidate, detection, dischargeHour]);

  // Buttery-smooth 60 FPS requestAnimationFrame Playback Engine with precise delta-timing
  useEffect(() => {
    if (!isPlaying) return;

    let animFrameId: number;
    let lastTimestamp = performance.now();

    const loop = (currentTimestamp: number) => {
      const deltaSeconds = (currentTimestamp - lastTimestamp) / 1000;
      lastTimestamp = currentTimestamp;

      // Base speed: 1.5 simulation hours per real-time second at 1x speed
      const hoursPerSecond = 1.5 * playbackSpeed;
      const step = deltaSeconds * hoursPerSecond * (playDirection === 'forward' ? 1 : -1);

      const currentTime = useOilTraceStore.getState().playbackTimeHours;
      const nextTime = currentTime + step;

      if (playDirection === 'backward') {
        if (nextTime <= -48.0) {
          setPlaybackTime(-48.0);
          togglePlayback();
          return;
        } else {
          setPlaybackTime(nextTime);
        }
      } else {
        if (nextTime >= 0.0) {
          setPlaybackTime(0.0);
          togglePlayback();
          return;
        } else {
          setPlaybackTime(nextTime);
        }
      }

      animFrameId = requestAnimationFrame(loop);
    };

    animFrameId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animFrameId);
  }, [isPlaying, playbackSpeed, playDirection, setPlaybackTime, togglePlayback]);

  // Compute actual date/time corresponding to the current offset
  const computeScrubberUtc = (offsetHours: number): string => {
    try {
      const baseDate = new Date(detection.detected_at);
      const targetDate = new Date(baseDate.getTime() + offsetHours * 3600 * 1000);
      return targetDate.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    } catch {
      return '2026-08-25 03:45:00 UTC';
    }
  };

  const handlePlayReverse = () => {
    setPlayDirection('backward');
    if (!isPlaying && playbackTimeHours <= -48.0) {
      setPlaybackTime(0.0);
    }
    if (!isPlaying) togglePlayback();
  };

  const handlePlayForward = () => {
    setPlayDirection('forward');
    if (!isPlaying && playbackTimeHours >= 0.0) {
      setPlaybackTime(-48.0);
    }
    if (!isPlaying) togglePlayback();
  };

  return (
    <div className="h-16 bg-[#070C14] border-t border-[#1E2C3F] px-3 md:px-4 flex items-center justify-between select-none z-20 font-mono">
      {/* ── LEFT: Playback Controls (Reverse Hindcast + Forward Confession) ── */}
      <div className="flex items-center space-x-1.5 md:space-x-2 shrink-0">
        {/* Play Reverse (Hindcast Mode) */}
        <button
          onClick={handlePlayReverse}
          className={`px-2 md:px-2.5 py-1.5 flex items-center space-x-1.5 border text-xs font-bold transition-all rounded-sm shadow-sm ${
            isPlaying && playDirection === 'backward'
              ? 'bg-[#2DD4BF] text-[#060B11] border-[#2DD4BF]'
              : 'bg-[#0D1522] border-[#1E2C3F] text-slate-300 hover:border-[#2DD4BF] hover:text-[#2DD4BF]'
          }`}
          title="Play Backward Hindcast: Trace oil from observed slick back in time to discover origin"
        >
          {isPlaying && playDirection === 'backward' ? (
            <Pause className="w-3.5 h-3.5 fill-current" />
          ) : (
            <Rewind className="w-3.5 h-3.5 fill-current" />
          )}
          <span className="hidden 2xl:inline text-[10px]">HINDCAST</span>
        </button>

        {/* Play Forward (Advection Mode) */}
        <button
          onClick={handlePlayForward}
          className={`px-2 md:px-2.5 py-1.5 flex items-center space-x-1.5 border text-xs font-bold transition-all rounded-sm shadow-sm ${
            isPlaying && playDirection === 'forward'
              ? 'bg-[#F59E0B] text-[#060B11] border-[#F59E0B]'
              : 'bg-[#0D1522] border-[#1E2C3F] text-slate-300 hover:border-[#F59E0B] hover:text-[#F59E0B]'
          }`}
          title="Play Forward Confession: Verify if oil released at suspect point advects into observed slick"
        >
          {isPlaying && playDirection === 'forward' ? (
            <Pause className="w-3.5 h-3.5 fill-current" />
          ) : (
            <Play className="w-3.5 h-3.5 fill-current" />
          )}
          <span className="hidden 2xl:inline text-[10px]">FORWARD</span>
        </button>

        {/* Reset */}
        <button
          onClick={() => {
            setPlaybackTime(0.0);
            if (isPlaying) togglePlayback();
          }}
          className="p-1.5 bg-[#0D1522] border border-[#1E2C3F] hover:border-[#2DD4BF] text-slate-400 hover:text-[#2DD4BF] transition-colors rounded-sm"
          title="Reset to Sentinel-1 Detection Horizon (T=0h)"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>

        {/* Playback Multipliers (1x, 4x, 16x, 64x) */}
        <div className="flex items-center space-x-0.5 bg-[#0D1522] border border-[#1E2C3F] p-0.5 rounded-sm">
          {[1, 4, 16, 64].map((spd) => (
            <button
              key={spd}
              onClick={() => setPlaybackSpeed(spd)}
              className={`px-1.5 py-0.5 text-[10px] rounded-sm transition-colors ${
                playbackSpeed === spd
                  ? 'bg-[#2DD4BF] text-[#070C14] font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {spd}x
            </button>
          ))}
        </div>

        {/* Quick Horizon Jump Buttons */}
        <div className="hidden xl:flex items-center space-x-1 border-l border-[#1E2C3F] pl-2">
          <button
            onClick={() => { setPlaybackTime(0.0); if (isPlaying) togglePlayback(); }}
            className={`px-1.5 py-0.5 text-[9px] border transition-colors rounded-sm ${
              playbackTimeHours >= -1.0 ? 'bg-[#2DD4BF]/20 border-[#2DD4BF] text-[#2DD4BF] font-bold' : 'border-[#1E2C3F] text-slate-400 hover:text-white'
            }`}
            title="Jump to Satellite SAR Detection Horizon (T=0h)"
          >
            T=0h (SLICK)
          </button>

          <button
            onClick={() => { setPlaybackTime(dischargeHour); if (isPlaying) togglePlayback(); }}
            className={`px-1.5 py-0.5 text-[9px] border transition-colors rounded-sm ${
              Math.abs(playbackTimeHours - dischargeHour) <= 2.0 ? 'bg-amber-500/20 border-amber-400 text-amber-300 font-bold' : 'border-[#1E2C3F] text-slate-400 hover:text-white'
            }`}
            title={`Jump to Candidate Discharge Window (T=${dischargeHour}h: ${leadCandidate?.vessel_name || 'Suspect'} discharge slowdown)`}
          >
            T={dischargeHour.toFixed(0)}h (DISCHARGE)
          </button>

          <button
            onClick={() => { setPlaybackTime(-48.0); if (isPlaying) togglePlayback(); }}
            className={`px-1.5 py-0.5 text-[9px] border transition-colors rounded-sm ${
              playbackTimeHours <= -47.0 ? 'bg-sky-500/20 border-sky-400 text-sky-300 font-bold' : 'border-[#1E2C3F] text-slate-400 hover:text-white'
            }`}
            title="Jump to Maximum 48-Hour Backward Hindcast Horizon"
          >
            T=-48h (ORIGIN)
          </button>
        </div>
      </div>

      {/* ── CENTER: Visual Timeline Slider with Discharge Beacon Marker ── */}
      <div className="flex-1 min-w-[280px] max-w-2xl xl:max-w-3xl mx-3 md:mx-4 flex flex-col justify-center">
        {/* Anti-Collision High-Contrast Milestone Badges */}
        <div className="relative w-full h-5 mb-1 text-[9px] text-slate-300 font-mono">
          {/* T=-48h Origin Badge */}
          <span className="absolute left-0 text-sky-300 font-bold bg-[#0D1522] border border-sky-500/40 px-1.5 py-0.5 rounded text-[9px] whitespace-nowrap shadow-sm z-10">
            T=-48h ORIGIN
          </span>

          {/* Dynamic Discharge Beacon Marker Badge (Clamped to avoid overlapping endpoints) */}
          <span
            className="absolute text-amber-300 font-bold flex items-center space-x-1 font-mono whitespace-nowrap bg-[#121B2A] border border-amber-500/60 px-1.5 py-0.5 rounded shadow-sm text-[9px] z-20"
            style={{
              left: `${Math.max(26, Math.min(74, ((dischargeHour + 48.0) / 48.0) * 100))}%`,
              transform: 'translateX(-50%)',
            }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping inline-block" />
            <span>T={dischargeHour.toFixed(0)}h DISCHARGE</span>
          </span>

          {/* T=0h SAR Slick Badge */}
          <span className="absolute right-0 text-[#2DD4BF] font-bold bg-[#0D1522] border border-[#2DD4BF]/50 px-1.5 py-0.5 rounded text-[9px] whitespace-nowrap shadow-sm z-10">
            T=0h SAR SLICK
          </span>
        </div>

        <div className="relative flex items-center w-full">
          {/* AIS Blackout Gap Zone highlighted directly on slider track */}
          {aisGapRange && (
            <div
              className="absolute h-2.5 bg-rose-500/20 border-y border-rose-500/50 rounded-xs pointer-events-none z-10"
              style={{
                left: `${((aisGapRange.start + 48.0) / 48.0) * 100}%`,
                width: `${Math.max(2.5, ((aisGapRange.end - aisGapRange.start) / 48.0) * 100)}%`,
              }}
              title={`Suspect AIS Blackout Gap Window (T=${aisGapRange.start.toFixed(0)}h to T=${aisGapRange.end.toFixed(0)}h)`}
            />
          )}

          <input
            type="range"
            min={-48.0}
            max={0.0}
            step={0.1}
            value={localTime}
            onPointerDown={handlePointerDown}
            onPointerUp={handlePointerUp}
            onChange={(e) => handleSliderChange(parseFloat(e.target.value))}
            className="w-full accent-[#2DD4BF] cursor-pointer bg-[#0D1522] h-2 rounded-full z-10"
          />
          {/* Discharge Window marker on slider track */}
          <div
            className="absolute h-3.5 w-1 bg-amber-400 pointer-events-none rounded-full z-20 shadow-[0_0_6px_rgba(245,158,11,0.9)]"
            style={{ left: `${Math.max(0, Math.min(100, ((dischargeHour + 48.0) / 48.0) * 100))}%` }}
            title={`Discharge Corridor: T=${dischargeHour}h (${dischargeSpeedKnots} kn)`}
          />
        </div>
      </div>

      {/* ── RIGHT: Live Telemetry HUD (Fixed Width 320px: ZERO Layout Shift / ZERO Slider Lag) ── */}
      <div className="hidden lg:flex items-center space-x-3 text-right w-[320px] shrink-0 justify-end">
        <div className="min-w-0 flex-1">
          <div className="text-xs text-slate-100 tabular-nums font-bold flex items-center justify-end space-x-1.5">
            <Clock className="w-3.5 h-3.5 text-[#2DD4BF]" />
            <span>{computeScrubberUtc(localTime)}</span>
          </div>
          <div className="text-[9px] tracking-wider font-semibold mt-0.5 truncate flex items-center justify-end">
            {localTime >= -1.0 ? (
              <span className="text-[#2DD4BF]">OBSERVED SENTINEL-1 SAR HORIZON</span>
            ) : isCurrentlyInGap ? (
              <span className="text-rose-400 font-bold flex items-center space-x-1">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-ping inline-block mr-0.5" />
                <span>⚠ AIS BLACKOUT GAP ({dischargeSpeedKnots.toFixed(1)} kn)</span>
              </span>
            ) : Math.abs(localTime - dischargeHour) <= 2.0 ? (
              <span className="text-amber-300 font-bold">
                DISCHARGE INTERSECT WINDOW ({dischargeSpeedKnots.toFixed(1)} kn)
              </span>
            ) : (
              <span className="text-sky-300">BACKWARD HYDRODYNAMIC ADVECTION</span>
            )}
          </div>
        </div>

        <div className="border-l border-[#1E2C3F] pl-3 shrink-0">
          <div className="text-sm font-bold font-mono tabular-nums text-[#2DD4BF]">
            {localTime === 0 ? 'T=0.0h' : `T${localTime.toFixed(1)}h`}
          </div>
          <div className="text-[8px] text-slate-500 uppercase tracking-widest">
            {playDirection === 'backward' ? 'HINDCAST' : 'ADVECTION'}
          </div>
        </div>
      </div>
    </div>
  );
};
