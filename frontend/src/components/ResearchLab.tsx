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

  function selectAndShowDetail(name: string) {
    setSelected(name);
    setActiveTab("Strategy Detail");
  }

  return (
    <div className="p-10 overflow-y-auto h-full">
      <div className="flex gap-4 border-b border-white/5 pb-2 mb-6 text-sm font-mono uppercase">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={tab === activeTab ? "text-accent border-b-2 border-accent pb-1" : "text-ink-muted"}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "Overview" && <ResearchOverview />}
      {activeTab === "Verdicts" && <VerdictsTable onSelect={selectAndShowDetail} />}
      {activeTab === "Strategy Detail" && <StrategyDetail selected={selected} />}
      {activeTab === "Diagnostics" && <Diagnostics selected={selected} />}
      {activeTab === "Piggyback Lab" && <PiggybackLab />}
    </div>
  );
}
