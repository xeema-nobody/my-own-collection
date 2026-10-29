import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { QueryError } from "../components/QueryState";
import { Tabs, TabList, Tab, TabPanel } from "../components/ui";
import CatalogTab from "./settings/CatalogTab";
import PricesTab from "./settings/PricesTab";
import AutomationTab from "./settings/AutomationTab";
import DataTab from "./settings/DataTab";
import JobsTab from "./settings/JobsTab";

const TABS = [["catalog", "Catalog"], ["prices", "Prices"], ["automation", "Automation"], ["data", "Data"], ["jobs", "Jobs"]] as const;

export default function Settings() {
  const [sp, setSp] = useSearchParams();
  const tab = TABS.some(([k]) => k === sp.get("tab")) ? sp.get("tab")! : "catalog";
  const [picked, setPicked] = useState<Set<string>>(new Set()); // shared by Catalog actions and Prices scope
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const sets = useQuery({ queryKey: ["sets", "stats"], queryFn: () => api.sets(true) });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 3000 });
  return (
    <div className="space-y-4">
      <QueryError q={status} label="Status" /><QueryError q={sets} label="Sets" /><QueryError q={jobs} label="Jobs" />
      <Tabs value={tab} onValueChange={(v) => setSp(v === "catalog" ? {} : { tab: v }, { replace: true })}>
        <TabList>{TABS.map(([k, l]) => <Tab key={k} value={k}>{l}</Tab>)}</TabList>
        <TabPanel value="catalog"><CatalogTab sets={sets} jobs={jobs} picked={picked} setPicked={setPicked} /></TabPanel>
        <TabPanel value="prices"><PricesTab status={status} jobs={jobs} picked={picked} /></TabPanel>
        <TabPanel value="automation"><AutomationTab status={status} /></TabPanel>
        <TabPanel value="data"><DataTab /></TabPanel>
        <TabPanel value="jobs"><JobsTab jobs={jobs} /></TabPanel>
      </Tabs>
    </div>);
}
