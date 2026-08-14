import { useState } from "react";
import ResearchOverview from "./ResearchOverview";
import VerdictsTable from "./VerdictsTable";
import StrategyDetail from "./StrategyDetail";
import Diagnostics from "./Diagnostics";
import PiggybackLab from "./PiggybackLab";

const TABS = ["Overview", "Verdicts", "Strategy Detail", "Diagnostics", "Piggyback Lab"] as const;
type Tab = (typeof TABS)[number];

export default function ResearchLab() {
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [selected, setSelected] = useState<string | null>(null);
  // Design spec: each tab lazy-fetches its own endpoint on first activation, then stays
  // cached -- switching tabs must not refetch. Conditionally RENDERING a tab (the old
  // approach) unmounts it on every switch-away, so its useEffect refires on switch-back.
  // Instead: mount a tab's component the first time it's activated, then keep it mounted
  // forever and just show/hide it with CSS.
  const [activatedTabs, setActivatedTabs] = useState<Set<Tab>>(new Set(["Overview"]));

  function activate(tab: Tab) {
    setActiveTab(tab);
    setActivatedTabs((prev) => (prev.has(tab) ? prev : new Set(prev).add(tab)));
  }

  function selectAndShowDetail(name: string) {
    setSelected(name);
    activate("Strategy Detail");
  }

  return (
    <div className="p-10 overflow-y-auto h-full">
      <div className="flex gap-4 border-b border-white/5 pb-2 mb-6 text-sm font-mono uppercase">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => activate(tab)}
            className={tab === activeTab ? "text-accent border-b-2 border-accent pb-1" : "text-ink-muted"}
          >
            {tab}
          </button>
        ))}
      </div>

      {activatedTabs.has("Overview") && (
        <div style={{ display: activeTab === "Overview" ? "block" : "none" }}>
          <ResearchOverview />
        </div>
      )}
      {activatedTabs.has("Verdicts") && (
        <div style={{ display: activeTab === "Verdicts" ? "block" : "none" }}>
          <VerdictsTable onSelect={selectAndShowDetail} />
        </div>
      )}
      {activatedTabs.has("Strategy Detail") && (
        <div style={{ display: activeTab === "Strategy Detail" ? "block" : "none" }}>
          <StrategyDetail selected={selected} />
        </div>
      )}
      {activatedTabs.has("Diagnostics") && (
        <div style={{ display: activeTab === "Diagnostics" ? "block" : "none" }}>
          <Diagnostics selected={selected} />
        </div>
      )}
      {activatedTabs.has("Piggyback Lab") && (
        <div style={{ display: activeTab === "Piggyback Lab" ? "block" : "none" }}>
          <PiggybackLab />
        </div>
      )}
    </div>
  );
}
