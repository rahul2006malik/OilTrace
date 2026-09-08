import React from 'react';
import { useOilTraceStore } from '../../store/useOilTraceStore';
import { ScreenType } from '../../types';
import {
  Compass,
  Layers,
  Radar,
  Ship,
  FileText,
  Cpu,
  LogOut,
} from 'lucide-react';

interface NavItem {
  screen: ScreenType;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { screen: 'overview', label: 'Cockpit', icon: <Compass className="w-5 h-5" /> },
  { screen: 'scenarios', label: 'Scenarios', icon: <Layers className="w-5 h-5" /> },
  { screen: 'vessels', label: 'Vessels', icon: <Ship className="w-5 h-5" /> },
  { screen: 'surveillance', label: 'Tasking', icon: <Radar className="w-5 h-5" /> },
  { screen: 'reports', label: 'Admiralty', icon: <FileText className="w-5 h-5" /> },
  { screen: 'governance', label: 'System', icon: <Cpu className="w-5 h-5" /> },
];

export const LeftSidebar: React.FC = () => {
  const activeScreen = useOilTraceStore((s) => s.activeScreen);
  const setActiveScreen = useOilTraceStore((s) => s.setActiveScreen);
  const logout = useOilTraceStore((s) => s.logout);

  const handleNavClick = (screen: ScreenType) => {
    setActiveScreen(screen);
  };

  return (
    <aside className="w-[58px] h-full bg-[#070C14] border-r border-[#1E2C3F] flex flex-col items-center py-3 shrink-0 z-20 select-none">
      {/* Navigation items */}
      <nav className="flex-1 flex flex-col items-center space-y-1.5 w-full px-1.5">
        {NAV_ITEMS.map(({ screen, label, icon }) => {
          const isActive = activeScreen === screen;
          return (
            <button
              key={screen}
              onClick={() => handleNavClick(screen)}
              className={`relative w-full h-11 flex flex-col items-center justify-center transition-all group rounded-sm ${
                isActive
                  ? 'bg-[#2DD4BF]/10 text-[#2DD4BF]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#0D1522]'
              }`}
            >
              {/* Active left indicator */}
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 bg-[#2DD4BF] rounded-r" />
              )}
              {icon}
              <span className="text-[8px] font-mono mt-0.5 tracking-wider uppercase leading-none text-center">
                {label}
              </span>
              {/* Flyout tooltip */}
              <div className="absolute left-full ml-2 px-2.5 py-1 bg-[#0D1522] border border-[#1E2C3F] text-[11px] font-mono text-white whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 shadow-xl rounded-sm hidden sm:block">
                {label}
              </div>
            </button>
          );
        })}
      </nav>

      {/* Logout button */}
      <button
        onClick={logout}
        title="Logout"
        className="w-full h-11 flex flex-col items-center justify-center text-slate-500 hover:text-rose-400 hover:bg-[#0D1522] transition-colors px-1.5 rounded-sm"
      >
        <LogOut className="w-4 h-4" />
        <span className="text-[8px] font-mono mt-0.5 tracking-wider uppercase leading-none">Exit</span>
      </button>
    </aside>
  );
};
