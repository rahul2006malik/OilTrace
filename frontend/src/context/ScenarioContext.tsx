import React, { createContext, useContext, useMemo, useState } from "react";
import type {
  AttributionResult,
  OriginEnsemble,
  SandboxWeights,
  ScenarioSummary,
  SlickDetection,
  TrajectoryMember,
} from "../types/schemas";

export const DEFAULT_SANDBOX_WEIGHTS: SandboxWeights = {
  proximity: 0.35,
  confession_match: 0.35,
  anomaly: 0.2,
  vessel_type_prior: 0.1,
};

interface ScenarioContextValue {
  currentScenario: ScenarioSummary | null;
  setCurrentScenario: (scenario: ScenarioSummary | null) => void;

  slickData: SlickDetection | null;
  setSlickData: (data: SlickDetection | null) => void;

  originConeData: OriginEnsemble | null;
  setOriginConeData: (data: OriginEnsemble | null) => void;
  originEnsemble: OriginEnsemble | null;
  setOriginEnsemble: (data: OriginEnsemble | null) => void;

  trajectoriesData: TrajectoryMember[];
  setTrajectoriesData: (data: TrajectoryMember[]) => void;

  attributionData: AttributionResult | null;
  setAttributionData: (data: AttributionResult | null) => void;

  selectedCandidateId: string | null;
  setSelectedCandidateId: (vesselId: string | null) => void;

  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;

  errorMessage: string | null;
  setErrorMessage: (message: string | null) => void;

  sandboxWeights: SandboxWeights;
  setSandboxWeights: (weights: SandboxWeights) => void;
}

const ScenarioContext = createContext<ScenarioContextValue | undefined>(undefined);

export function ScenarioProvider({ children }: { children: React.ReactNode }) {
  const [currentScenario, setCurrentScenario] = useState<ScenarioSummary | null>(null);
  const [slickData, setSlickData] = useState<SlickDetection | null>(null);
  const [originConeData, setOriginConeData] = useState<OriginEnsemble | null>(null);
  const [trajectoriesData, setTrajectoriesData] = useState<TrajectoryMember[]>([]);
  const [attributionData, setAttributionData] = useState<AttributionResult | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [sandboxWeights, setSandboxWeights] = useState<SandboxWeights>(
    DEFAULT_SANDBOX_WEIGHTS
  );

  const value = useMemo<ScenarioContextValue>(
    () => ({
      currentScenario,
      setCurrentScenario,
      slickData,
      setSlickData,
      originConeData,
      setOriginConeData,
      originEnsemble: originConeData,
      setOriginEnsemble: setOriginConeData,
      trajectoriesData,
      setTrajectoriesData,
      attributionData,
      setAttributionData,
      selectedCandidateId,
      setSelectedCandidateId,
      isLoading,
      setIsLoading,
      errorMessage,
      setErrorMessage,
      sandboxWeights,
      setSandboxWeights,
    }),
    [
      currentScenario,
      slickData,
      originConeData,
      trajectoriesData,
      attributionData,
      selectedCandidateId,
      isLoading,
      errorMessage,
      sandboxWeights,
    ]
  );

  return (
    <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>
  );
}

export function useScenario(): ScenarioContextValue {
  const ctx = useContext(ScenarioContext);
  if (!ctx) {
    throw new Error("useScenario must be used within a ScenarioProvider");
  }
  return ctx;
}
