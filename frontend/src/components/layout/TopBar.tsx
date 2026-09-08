import React, { useEffect, useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { Bell, Search, Waves, ChevronDown, RefreshCw, FileText } from 'lucide-react';

export const TopBar: React.FC<{ onDossierOpen?: () => void }> = ({ onDossierOpen }) => {
  const {
    detection,
    attribution,
    backendOnline,
    systemHealth,
    isLoadingPipeline,
    getRealVesselFraction,
    activeScenarioId,
    availableScenarios,
    setActiveScreen,
    selectCandidate,
    setCameraTarget,
  } = useOilTraceStore();

  const [utcTime, setUtcTime] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [livePingsCount, setLivePingsCount] = useState<number>(0);
  const [wsConnected, setWsConnected] = useState<boolean>(false);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const d = now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
      const t = now.toLocaleTimeString('en-GB', { hour12: false, timeZone: 'UTC' });
      setUtcTime(`${d} | ${t} UTC`);
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Real-time WebSocket connection to backend /ws/live-ais with exponential backoff
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let backoff = 2000;
    let isCancelled = false;

    function connect() {
      if (isCancelled) return;
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const isDev = window.location.port === '3000' || window.location.port === '5173';
        const host = isDev ? '127.0.0.1:8000' : window.location.host;
        ws = new WebSocket(`${protocol}//${host}/ws/live-ais`);

        ws.onopen = () => {
          setWsConnected(true);
          backoff = 2000;
        };
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'ais_batch') {
              setLivePingsCount((prev) => prev + (data.pings_count || 1));
            } else if (data.type === 'heartbeat') {
              setLivePingsCount((prev) => prev + 1);
            }
          } catch {
            setLivePingsCount((prev) => prev + 1);
          }
        };
        ws.onclose = () => {
          setWsConnected(false);
          if (!isCancelled) {
            reconnectTimeout = setTimeout(connect, backoff);
            backoff = Math.min(backoff * 1.5, 15000);
          }
        };
        ws.onerror = () => {
          setWsConnected(false);
          if (ws) {
            try { ws.close(); } catch {}
          }
        };
      } catch {
        setWsConnected(false);
        if (!isCancelled) {
          reconnectTimeout = setTimeout(connect, backoff);
          backoff = Math.min(backoff * 1.5, 15000);
        }
      }
    }

    connect();

    return () => {
      isCancelled = true;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  const realFraction = getRealVesselFraction();
  const totalCandidates = attribution?.candidates.length || 0;
  const realCount = Math.round(realFraction * totalCandidates);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim().toLowerCase();
    if (!q) return;

    // Check if query is coordinates e.g. "71.6, 18.4"
    const coordMatch = q.match(/^(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)$/);
    if (coordMatch) {
      const lon = parseFloat(coordMatch[1]);
      const lat = parseFloat(coordMatch[2]);
      if (!isNaN(lon) && !isNaN(lat)) {
        setCameraTarget([lon, lat]);
        setActiveScreen('overview');
        return;
      }
    }

    // Check candidate match
    const candidate = attribution?.candidates.find(
      (c) => c.vessel_id.toLowerCase().includes(q) || (c.vessel_name && c.vessel_name.toLowerCase().includes(q))
    );
    if (candidate) {
      selectCandidate(candidate.vessel_id);
      setActiveScreen('vessels');
    }
  };

  const activeScenarioName = availableScenarios.find((s) => s.scenario_id === activeScenarioId)?.name || 'Arabian Sea – Flagship';

  return (
    <header className="h-14 bg-[#070C14] border-b border-[#1E2C3F] px-4 flex items-center justify-between shrink-0 z-30 gap-4">
      {/* Left: Brand mark & subsystem tag */}
      <div className="flex items-center space-x-3 shrink-0">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 bg-[#2DD4BF]/10 border border-[#2DD4BF]/40 flex items-center justify-center rounded-sm">
            <Waves className="w-4 h-4 text-[#2DD4BF]" />
          </div>
          <div>
            <div className="text-sm font-bold text-white font-mono tracking-widest leading-none">OILTRACE</div>
            <div className="text-[9px] text-[#2DD4BF] font-mono leading-none mt-1 font-semibold tracking-wider">NTRO MDA // FORENSICS</div>
          </div>
        </div>
      </div>

      {/* Center: Scenario Switcher & Global Search */}
      <div className="flex items-center space-x-3 flex-1 max-w-2xl mx-4">
        {/* Scenario selector button */}
        <button
          onClick={() => setActiveScreen('scenarios')}
          className="hidden md:flex items-center space-x-2.5 bg-[#0D1522] border border-[#1E2C3F] hover:border-[#2DD4BF] px-3 py-1.5 text-xs font-mono transition-colors shrink-0 text-left rounded-sm group"
          title="Click to switch incident scenarios"
        >
          <div className="w-1.5 h-1.5 rounded-full bg-[#2DD4BF] group-hover:animate-ping" />
          <div>
            <div className="text-[8px] text-slate-500 uppercase tracking-wider font-semibold">ACTIVE SCENARIO</div>
            <div className="text-slate-200 font-semibold truncate max-w-[220px] text-[11px]">{activeScenarioName}</div>
          </div>
          <ChevronDown className="w-3.5 h-3.5 text-slate-400 group-hover:text-[#2DD4BF]" />
        </button>

        {/* Search bar */}
        <form onSubmit={handleSearchSubmit} className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search MMSI, vessel name, or coords (lon, lat)..."
            className="w-full bg-[#0D1522] border border-[#1E2C3F] pl-9 pr-8 py-1.5 text-xs font-mono text-slate-200 focus:border-[#2DD4BF] focus:outline-none placeholder-slate-500 transition-colors rounded-sm"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-slate-400 hover:text-white font-mono"
            >
              ✕
            </button>
          )}
        </form>
      </div>

      {/* Right: Telemetry KPI strip + user */}
      <div className="flex items-center space-x-3 shrink-0">
        {/* Unified Telemetry Cluster */}
        <div className="hidden lg:flex items-center bg-[#0D1522] border border-[#1E2C3F] px-3 py-1 text-xs font-mono rounded-sm divide-x divide-[#1E2C3F] space-x-3">
          {/* AIS Stream Status */}
          <div className="flex items-center space-x-1.5 pr-1">
            <div className={`w-2 h-2 rounded-full ${backendOnline || wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
            <span className="text-[10px] font-bold tracking-wider text-slate-200">
              {wsConnected ? 'AIS STREAM' : backendOnline ? 'AIS LIVE' : 'OFFLINE'}
            </span>
          </div>

          {/* Suspects count */}
          <div className="flex items-baseline space-x-1.5 pl-3">
            <span className="text-slate-500 text-[10px] uppercase font-semibold">SUSPECTS</span>
            <span className="font-bold text-white tabular-nums text-sm">{totalCandidates}</span>
          </div>

          {/* Real provenance badge */}
          <div className="flex items-baseline space-x-1 pl-3">
            <span className="text-slate-500 text-[10px] uppercase font-semibold">PROVENANCE</span>
            <span className="font-bold text-[#2DD4BF] tabular-nums text-xs">{realCount}/{totalCandidates || 1} REAL</span>
          </div>

          {/* Live pings */}
          {livePingsCount > 0 && (
            <div className="flex items-baseline space-x-1 pl-3">
              <span className="text-slate-500 text-[10px] uppercase font-semibold">PINGS</span>
              <span className="font-bold text-sky-400 tabular-nums text-xs">+{livePingsCount}</span>
            </div>
          )}
        </div>

        {/* Pipeline running spinner */}
        {isLoadingPipeline && (
          <div className="flex items-center space-x-1.5 px-2.5 py-1 bg-[#2DD4BF]/10 border border-[#2DD4BF]/40 text-[#2DD4BF] text-xs font-mono rounded-sm">
            <RefreshCw className="w-3 h-3 animate-spin" />
            <span className="font-bold text-[10px]">ANALYZING</span>
          </div>
        )}

        {/* UTC Clock */}
        <div className="hidden xl:block text-right font-mono text-[11px] text-slate-400 tabular-nums">
          {utcTime}
        </div>

        {/* B3 FIX: Dossier export button — was completely inaccessible before.
            AppShell has isDossierOpen state but had no trigger. Now TopBar owns the button. */}
        {attribution && (
          <button
            onClick={onDossierOpen}
            title="Generate Admiralty Forensic Dossier"
            className="flex items-center space-x-1.5 px-2.5 py-1 bg-[#1E2C3F] border border-[#2DD4BF]/30 hover:border-[#2DD4BF] text-[#2DD4BF] font-mono text-[10px] font-bold transition-colors rounded-sm"
          >
            <FileText className="w-3.5 h-3.5" />
            <span className="hidden xl:inline">DOSSIER</span>
          </button>
        )}

        {/* User initials badge */}
        <div className="w-7 h-7 rounded-sm bg-[#1E2C3F] border border-[#2DD4BF]/40 flex items-center justify-center text-[#2DD4BF] font-bold text-xs font-mono">
          NT
        </div>
      </div>
    </header>
  );
};
