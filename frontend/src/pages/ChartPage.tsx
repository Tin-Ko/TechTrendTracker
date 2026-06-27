import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import NavBar from "../components/NavBar";
import ProjectRecommendations from "../components/ProjectRecommendations";
import RelatedTitles from "../components/RelatedTitles";
import SkillsBarChart from "../components/SkillsBarChart";
import { fetchRecommendations, fetchSkills } from "../api";
import type { ProjectRec, SkillsResponse } from "../types";

export default function ChartPage() {
  const [params] = useSearchParams();
  const jobTitle = params.get("job_title") ?? "";

  const [data, setData] = useState<SkillsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [recs, setRecs] = useState<ProjectRec[] | null>(null);
  const [recsError, setRecsError] = useState<string | null>(null);
  const [recsLoading, setRecsLoading] = useState(false);

  useEffect(() => {
    if (!jobTitle) return;
    setLoading(true);
    setError(null);
    fetchSkills(jobTitle)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [jobTitle]);

  const skills = data?.Skills ?? [];
  const topSkillNames = skills.slice(0, 5).map((s) => s.Name);

  // Recommendations are a separate call keyed on the top skills, so the bar
  // chart renders the moment /skills returns instead of waiting on the lookup.
  const topKey = topSkillNames.join("|");
  useEffect(() => {
    if (topSkillNames.length < 3) {
      setRecs(null);
      return;
    }
    setRecsLoading(true);
    setRecsError(null);
    fetchRecommendations(topSkillNames)
      .then((r) => setRecs(r.Projects ?? []))
      .catch((e: unknown) => setRecsError(e instanceof Error ? e.message : String(e)))
      .finally(() => setRecsLoading(false));
    // topKey captures the only input that should retrigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topKey]);

  return (
    <>
      <NavBar showSearch initialValue={jobTitle} />

      <main className="page">
        <div className="wrap">
          <div className="rhead">
            <div className="kicker">SKILLS REPORT // {jobTitle || "—"}</div>
            <h2>The skills employers are hiring for.</h2>
            {data && (
              <div className="meta">
                <span>SOURCE: {data.JobCount.toLocaleString()} job postings</span>
                <span>SKILLS FOUND: {data.SkillsCount.toLocaleString()}</span>
              </div>
            )}
          </div>

          {loading && <div className="state">Scanning postings…</div>}
          {error && <div className="state err">Error: {error}</div>}
          {!loading && !error && !jobTitle && (
            <div className="state">Search for a job title to see the top skills.</div>
          )}

          {!loading && !error && data && (
            <>
              <div className="layout">
                <div className="box">
                  <h3>Top 10 in-demand skills</h3>
                  <p className="bs">
                    % = share of postings that list the skill · longer bar = more demand
                  </p>
                  <SkillsBarChart skills={skills} />
                </div>

                <div className="box">
                  <h3>Snapshot</h3>
                  <p className="bs">Pulled from this search</p>
                  <div className="stat">
                    <div className="big">{data.JobCount.toLocaleString()}</div>
                    <div className="lab">job postings analyzed</div>
                  </div>
                  <div className="stat">
                    <div className="big">{data.SkillsCount.toLocaleString()}</div>
                    <div className="lab">distinct skills found</div>
                  </div>
                  <RelatedTitles titles={data.RelatedTitles} />
                </div>
              </div>

              <ProjectRecommendations
                topSkills={topSkillNames}
                projects={recs}
                loading={recsLoading}
                error={recsError}
              />
            </>
          )}
        </div>
      </main>

      <footer>
        <div className="wrap row">
          <div>TECH TREND TRACKER · SKILL DEMAND, DECODED</div>
          <div>SEARCH A ROLE ◆ BUILD THE SKILLS</div>
        </div>
      </footer>
    </>
  );
}
