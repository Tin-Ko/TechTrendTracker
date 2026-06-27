import type { ProjectRec } from "../types";

type Props = {
  /** Real top skills from the report, used for the "from top skills" line. */
  topSkills?: string[];
  /** Matched projects from /recommendations; null while loading. */
  projects: ProjectRec[] | null;
  loading?: boolean;
  error?: string | null;
};

export default function ProjectRecommendations({
  topSkills = [],
  projects,
  loading = false,
  error = null,
}: Props) {
  return (
    <>
      <div className="phead">
        <h2>Projects to build</h2>
        <p>Each one ships you a few in-demand skills, sized for a student or career-switcher.</p>
        {topSkills.length > 0 && (
          <div className="source">
            <span className="l">FROM TOP SKILLS:</span>
            {topSkills.slice(0, 5).map((s) => (
              <span key={s}>{s}</span>
            ))}
          </div>
        )}
      </div>

      {loading && <div className="state">Matching projects to your skills…</div>}
      {error && <div className="state err">Couldn't load recommendations: {error}</div>}
      {!loading && !error && projects && projects.length === 0 && (
        <div className="state">No project matches for this skill mix yet.</div>
      )}

      {!loading && !error && projects && projects.length > 0 && (
        <div className="pjs">
          {projects.map((p, i) => (
            <div className="pj" key={p.Title}>
              <div className="tag">
                <span className="lv">{p.Level}</span>
                <span>PROJECT {String(i + 1).padStart(2, "0")}</span>
              </div>
              <h4>{p.Title}</h4>
              <p>{p.Blurb}</p>
              <div className="earn">▸ BUILDS THESE SKILLS</div>
              <div className="kws">
                {p.Skills.map((k) => (
                  <span key={k}>{k}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
