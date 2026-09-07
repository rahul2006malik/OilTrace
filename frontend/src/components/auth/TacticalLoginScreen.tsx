import React, { useState } from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import {
  Shield,
  Lock,
  KeyRound,
  Radio,
  Terminal,
  Compass,
  ArrowRight,
} from 'lucide-react';

export const TacticalLoginScreen: React.FC = () => {
  const { login, backendOnline } = useOilTraceStore();
  const [callsign, setCallsign] = useState('NTRO-FORENSIC-01');
  const [accessKey, setAccessKey] = useState('DEFENSE-MDA-2026');
  const [isAuthorizing, setIsAuthorizing] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsAuthorizing(true);
    setTimeout(() => {
      login(callsign, accessKey);
      setIsAuthorizing(false);
    }, 300);
  };

  const handleQuickEnter = () => {
    setIsAuthorizing(true);
    setTimeout(() => {
      login('DEMO-OFFICER', 'INSTANT-ACCESS');
      setIsAuthorizing(false);
    }, 200);
  };

  return (
    <div className="flex h-screen w-screen bg-[#060B11] text-[#F1F5F9] font-mono select-none overflow-hidden relative items-center justify-center">
      {/* Background tactical grid and radar sweep decoration */}
      <div className="absolute inset-0 opacity-10 bg-[radial-gradient(circle_at_50%_50%,#2DD4BF_1px,transparent_1px)] bg-[length:24px_24px] pointer-events-none" />
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-[#2DD4BF]/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl pointer-events-none" />

      {/* Main Terminal Card */}
      <div className="relative z-10 w-full max-w-md mx-4 border border-[#1D2E42] bg-[#0A121C]/95 backdrop-blur-xl shadow-2xl p-6 sm:p-8 rounded-sm">
        {/* Terminal Header Bar */}
        <div className="flex items-center justify-between border-b border-[#1D2E42] pb-4 mb-6">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 bg-[#2DD4BF]/10 border border-[#2DD4BF]/40 flex items-center justify-center rounded-sm">
              <Shield className="w-5 h-5 text-[#2DD4BF]" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-base font-bold tracking-wider text-slate-100">OILTRACE</span>
                <span className="text-[9px] bg-[#2DD4BF]/20 text-[#2DD4BF] border border-[#2DD4BF]/40 px-1.5 py-0.5 rounded font-bold">
                  v2.4.1-DEFENSE
                </span>
              </div>
              <div className="text-[10px] text-slate-400 tracking-wider">
                NTRO SPATIO-TEMPORAL FORENSICS
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-1 text-[10px]">
            <span
              className={`w-2 h-2 rounded-full ${
                backendOnline ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
            />
            <span className={backendOnline ? 'text-emerald-400' : 'text-amber-400'}>
              {backendOnline ? 'CORE ONLINE' : 'STANDBY'}
            </span>
          </div>
        </div>

        {/* Clearance Classification Banner */}
        <div className="mb-6 p-2.5 bg-[#060B11] border border-amber-500/30 text-center rounded-sm">
          <div className="text-[10px] text-amber-300 font-bold tracking-widest uppercase">
            RESTRICTED ACCESS // MARITIME DOMAIN AWARENESS
          </div>
          <div className="text-[9px] text-slate-400 mt-0.5">
            SIH26143 · RADAR ADVECTION & AIS FORENSICS ENGINE
          </div>
        </div>

        {/* Authentication Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[10px] text-slate-400 uppercase tracking-wider mb-1.5">
              Operator Call-Sign / Badge ID
            </label>
            <div className="relative">
              <Terminal className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={callsign}
                onChange={(e) => setCallsign(e.target.value)}
                required
                className="w-full bg-[#060B11] border border-[#1D2E42] focus:border-[#2DD4BF] focus:outline-none pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-600 rounded-sm font-mono"
                placeholder="e.g. NTRO-FORENSIC-01"
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] text-slate-400 uppercase tracking-wider mb-1.5">
              Security Token / HSM Key
            </label>
            <div className="relative">
              <KeyRound className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="password"
                value={accessKey}
                onChange={(e) => setAccessKey(e.target.value)}
                required
                className="w-full bg-[#060B11] border border-[#1D2E42] focus:border-[#2DD4BF] focus:outline-none pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-600 rounded-sm font-mono"
                placeholder="Enter authorization key"
              />
            </div>
          </div>

          {/* Primary Submit Button */}
          <button
            type="submit"
            disabled={isAuthorizing}
            className="w-full mt-2 py-2.5 bg-[#2DD4BF] hover:bg-[#26bba7] text-[#060B11] font-bold text-xs flex items-center justify-center space-x-2 transition-all rounded-sm shadow-md disabled:opacity-50"
          >
            {isAuthorizing ? (
              <>
                <Radio className="w-4 h-4 animate-spin text-[#060B11]" />
                <span>AUTHORIZING TERMINAL SESSION...</span>
              </>
            ) : (
              <>
                <Lock className="w-3.5 h-3.5 text-[#060B11]" />
                <span>AUTHENTICATE & ENTER COCKPIT</span>
                <ArrowRight className="w-3.5 h-3.5 text-[#060B11]" />
              </>
            )}
          </button>
        </form>

        {/* Quick Demo Access Bypass */}
        <div className="mt-4 pt-4 border-t border-[#1D2E42] flex flex-col space-y-2">
          <button
            type="button"
            onClick={handleQuickEnter}
            disabled={isAuthorizing}
            className="w-full py-2 bg-[#1D2E42]/60 hover:bg-[#1D2E42] text-slate-200 hover:text-white font-bold text-xs border border-[#1D2E42] transition-colors flex items-center justify-center space-x-2 rounded-sm"
          >
            <Compass className="w-3.5 h-3.5 text-[#2DD4BF]" />
            <span>DIRECT TACTICAL ACCESS (EVALUATION MODE)</span>
          </button>

          <div className="flex items-center justify-between text-[9px] text-slate-500 pt-1">
            <span>TLS 1.3 / ECDHE-RSA</span>
            <span>AUDIT TRAIL LOGGED</span>
          </div>
        </div>
      </div>

      {/* Footer Legal & Security Notice */}
      <div className="absolute bottom-4 text-center text-[10px] text-slate-500">
        FOR AUTHORIZED MARITIME DEFENSE & COAST GUARD USE ONLY · UNCLOS ART. 211(5)
      </div>
    </div>
  );
};
