import { useNavigate } from "react-router-dom";

import NavBar from "../components/NavBar";
import SearchBar from "../components/SearchBar";

const SUGGESTIONS = ["Frontend Developer", "Data Engineer", "DevOps Engineer"];

// A static teaser of what a real report looks like — purely illustrative.
const PREVIEW = [
  ["React", 87],
  ["TypeScript", 79],
  ["AWS", 64],
  ["Docker", 58],
] as const;

export default function Home() {
  const navigate = useNavigate();

  const search = (title: string) =>
    navigate(`/chart?job_title=${encodeURIComponent(title)}`);

  return (
    <>
      <NavBar />

      <main className="page">
        <div className="wrap hero">
          <div>
            <p className="eyebrow">
              <span className="scan" />
              Live skill data from real job postings
            </p>
            <h1>
              The skills employers <span className="mk">actually want</span>. Mapped.
            </h1>
            <p className="lede">
              Search any job title and Tech Trend Tracker shows you the exact skills
              companies are hiring for — pulled from real postings — plus sample projects
              to help you build them.
            </p>

            <SearchBar variant="hero" />

            <div className="sugg">
              <span className="l">TRY:</span>
              {SUGGESTIONS.map((title) => (
                <button key={title} className="chip" onClick={() => search(title)}>
                  {title}
                </button>
              ))}
            </div>
          </div>

          <div className="preview">
            <div className="preview-h">
              <span>TOP SKILLS</span>
              <span>SAMPLE REPORT</span>
            </div>
            <div className="preview-name">Frontend Developer</div>
            <div className="preview-sub">A peek at what you'll see</div>
            {PREVIEW.map(([term, pct], i) => (
              <div className="prow" key={term}>
                <span className="pterm">{term}</span>
                <span className="ppct">{pct}%</span>
                <div className="pbar">
                  <i style={{ width: `${pct}%`, animationDelay: `${i * 90}ms` }} />
                </div>
              </div>
            ))}
          </div>
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
