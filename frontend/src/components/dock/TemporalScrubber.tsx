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

  // Dynamically derive the scenario's true discharge/onset window
  const dischargeHour = React.useMemo(() => {
    if (driftRun?.origin_zone?.estimated_onset_time && detection?.detected_at) {
      const onsetMs = new Date(driftRun.origin_zone.estimated_onset_time).getTime();
      const detMs = new Date(detection.detected_at).getTime();
      if (!isNaN(onsetMs) && !isNaN(detMs)) {
        const diffHours = (onsetMs - detMs) / (3600 * 1000);
        if (diffHours >= -48.0 && diffHours <= 0.0) {
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
          if (diffHours >= -48.0 && diffHours <= 0.0) {
            return Math.round(diffHours * 10) / 10;
          }
        }
      }
    }
    return -34.0;
  }, [driftRun, detection, leadCandidate]);

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
    <div className="h-16 bg-[#070C14] border-t border-[#1E2C3F] px-4 flex items-center justify-between select-none z-20 font-mono">
      {/* ── LEFT: Playback Controls (Reverse Hindcast + Forward Confession) ── */}
      <div className="flex items-center space-x-2">
        {/* Play Reverse (Hindcast Mode) */}
        <button
          onClick={handlePlayReverse}
          className={`px-2.5 py-1.5 flex items-center space-x-1.5 border text-xs font-bold transition-all rounded-sm shadow-sm ${
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
          <span className="hidden xl:inline text-[10px]">HINDCAST (BACK IN TIME)</span>
        </button>

        {/* Play Forward (Advection Mode) */}
        <button
          onClick={handlePlayForward}
          className={`px-2.5 py-1.5 flex items-center space-x-1.5 border text-xs font-bold transition-all rounded-sm shadow-sm ${
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
          <span className="hidden xl:inline text-[10px]">FORWARD CONFESSION</span>
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

        {/* Playback Multipliers (1x, 5x, 10x, 25x) */}
        <div className="flex items-center space-x-0.5 bg-[#0D1522] border border-[#1E2C3F] p-0.5 rounded-sm">
          {[1, 5, 10, 25].map((spd) => (
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
        <div className="hidden lg:flex items-center space-x-1 border-l border-[#1E2C3F] pl-2">
          <button
            onClick={() => { setPlaybackTime(0.0); if (isPlaying) togglePlayback(); }}
            className={`px-2 py-0.5 text-[9px] border transition-colors rounded-sm ${
              playbackTimeHours >= -1.0 ? 'bg-[#2DD4BF]/20 border-[#2DD4BF] text-[#2DD4BF] font-bold' : 'border-[#1E2C3F] text-slate-400 hover:text-white'
            }`}
            title="Jump to Satellite SAR Detection Horizon (T=0h)"
          >
            T=0h (SLICK)
          </button>

          <button
            onClick={() => { setPlaybackTime(dischargeHour); if (isPlaying) togglePlayback(); }}
            className={`px-2 py-0.5 text-[9px] border transition-colors rounded-sm ${
              Math.abs(playbackTimeHours - dischargeHour) <= 2.0 ? 'bg-amber-500/20 border-amber-400 text-amber-300 font-bold' : 'border-[#1E2C3F] text-slate-400 hover:text-white'
            }`}
            title={`Jump to Candidate Discharge Window (T=${dischargeHour}h: ${leadCandidate?.vessel_name || 'Suspect'} discharge slowdown)`}
          >
            T={dischargeHour.toFixed(0)}h (DISCHARGE)
          </button>

          <button
            onClick={() => { setPlaybackTime(-48.0); if (isPlaying) togglePlayback(); }}
            className={`px-2 py-0.5 text-[9px] border transition-colors rounded-sm ${
              playbackTimeHours <= -47.0 ? 'bg-sky-500/20 border-sky-400 text-sky-300 font-bold' : 'border-[#1E2C3F] text-slate-400 hover:text-white'
            }`}
            title="Jump to Maximum 48-Hour Backward Hindcast Horizon"
          >
            T=-48h (ORIGIN)
          </button>
        </div>
      </div>

      {/* ── CENTER: Visual Timeline Slider with Discharge Beacon Marker ── */}
      <div className="flex-1 max-w-xl mx-4 flex flex-col justify-center">
        <div className="flex justify-between items-center text-[9px] text-slate-400 mb-1 px-1">
          <span className="text-sky-300">T=-48h (Hindcast Origin)</span>
          <span className="text-amber-300 font-bold flex items-center space-x-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
            <span>T={dischargeHour.toFixed(0)}h (Discharge Window)</span>
          </span>
          <span className="text-[#2DD4BF] font-bold">T=0h (SAR Detection)</span>
        </div>

        <div className="relative flex items-center">
          <input
            type="range"
            min={-48.0}
            max={0.0}
            step={0.05}
            value={playbackTimeHours}
            onChange={(e) => setPlaybackTime(parseFloat(e.target.value))}
            className="w-full accent-[#2DD4BF] cursor-pointer bg-[#0D1522] h-2 rounded-full z-10"
          />
          {/* Discharge Window marker on slider track */}
          <div
            className="absolute h-3 w-1 bg-amber-400/80 pointer-events-none rounded-full"
            style={{ left: `${Math.max(0, Math.min(100, ((dischargeHour + 48.0) / 48.0) * 100))}%` }}
            title={`Discharge Corridor: T=${dischargeHour}h (${dischargeSpeedKnots} kn)`}
          />
        </div>
      </div>

      {/* ── RIGHT: Live Telemetry HUD (Microsecond UTC Clock + Active Phase) ── */}
      <div className="hidden md:flex items-center space-x-3 text-right shrink-0">
        <div>
          <div className="text-xs text-slate-100 tabular-nums font-bold flex items-center justify-end space-x-1.5">
            <Clock className="w-3.5 h-3.5 text-[#2DD4BF]" />
            <span>{computeScrubberUtc(playbackTimeHours)}</span>
          </div>
          <div className="text-[9px] text-slate-400 tracking-wider font-semibold mt-0.5">
            {playbackTimeHours >= -1.0 ? (
              <span className="text-[#2DD4BF]">OBSERVED SENTINEL-1 SAR HORIZON</span>
            ) : Math.abs(playbackTimeHours - dischargeHour) <= 2.0 ? (
              <span className="text-amber-300 font-bold">
                DISCHARGE INTERSECT WINDOW ({dischargeSpeedKnots.toFixed(1)} kn)
              </span>
            ) : (
              <span className="text-sky-300">BACKWARD HYDRODYNAMIC ADVECTION</span>
            )}
          </div>
        </div>

        <div className="border-l border-[#1E2C3F] pl-3">
          <div className="text-sm font-bold font-mono tabular-nums text-[#2DD4BF]">
            {playbackTimeHours === 0 ? 'T=0.0h' : `T${playbackTimeHours.toFixed(1)}h`}
          </div>
          <div className="text-[8px] text-slate-500 uppercase tracking-widest">
            {playDirection === 'backward' ? 'HINDCAST' : 'ADVECTION'}
          </div>
        </div>
      </div>
    </div>
  );
};
