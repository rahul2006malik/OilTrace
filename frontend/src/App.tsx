import React from 'react';
import { useOilTraceStore } from './store/useOilTraceStore';
import { AppShell } from './components/layout/AppShell';
import { TacticalLoginScreen } from './components/auth/TacticalLoginScreen';

export const App: React.FC = () => {
  const { isLoggedIn } = useOilTraceStore();

  if (!isLoggedIn) {
    return <TacticalLoginScreen />;
  }

  return <AppShell />;
};

export default App;

