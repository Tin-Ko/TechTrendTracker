import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import RelatedTitles from "../components/RelatedTitles";
import SearchBar from "../components/SearchBar";
import SkillsBarChart from "../components/SkillsBarChart";
import StatCard from "../components/StatCard";
import { fetchSkills } from "../api";
import type { SkillsResponse } from "../types";

export default function ChartPage() {
  const [params] = useSearchParams();
  const jobTitle = params.get("job_title") ?? "";

  const [data, setData] = useState<SkillsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!jobTitle) return;
    setLoading(true);
    setError(null);
    fetchSkills(jobTitle)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [jobTitle]);

  return (
    <div className="flex-1 flex flex-col w-full">
      <div className="flex-1 flex flex-row items-center justify-between w-full">
        <div className="flex-1 h-full">
          <Link
            to="/"
            className="flex text-7xl items-center justify-center font-bold tracking-tight drop-shadow-lg w-fit h-fit mt-10 ml-12"
          >
            TTT
          </Link>
        </div>
        <div className="flex h-full lg:w-[60%] w-[60%] items-center justify-center">
          <SearchBar size="compact" initialValue={jobTitle} />
        </div>
        <div className="flex-1 h-full" />
      </div>

      <div className="flex flex-row lg:w-[60%] w-[60%] justify-center mx-auto">
        <div className="bg-zinc-600/50 rounded-xl overflow-hidden w-full border border-zinc-400 border-opacity-50">
          <div className="w-full" style={{ height: 480 }}>
            {loading && (
              <div className="text-white/70 text-center py-16">Loading…</div>
            )}
            {error && (
              <div className="text-red-300 text-center py-16">Error: {error}</div>
            )}
            {!loading && !error && data && <SkillsBarChart skills={data.Skills ?? []} />}
          </div>
        </div>
      </div>

      <RelatedTitles titles={data?.RelatedTitles} />

      <div className="flex flex-1 w-full justify-center items-center mt-6">
        <div className="flex flex-row items-center justify-evenly w-[60%] h-full">
          <StatCard value={data?.JobCount ?? 0} label="Jobs Found" />
          <StatCard value={data?.SkillsCount ?? 0} label="Skills Found" />
        </div>
      </div>
    </div>
  );
}
