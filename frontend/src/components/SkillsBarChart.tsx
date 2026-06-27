import type { Skill } from "../types";

type Props = {
  skills: Skill[];
};

// Ranked list of the top screened skills, each with a horizontal demand bar.
export default function SkillsBarChart({ skills }: Props) {
  if (!skills || skills.length === 0) {
    return <p className="empty">No skills to show for this query yet.</p>;
  }

  const top = skills.slice(0, 10);
  // Scale bars relative to the most-demanded skill so the leader fills the row.
  const max = Math.max(...top.map((s) => s.Percentage), 1);

  return (
    <div>
      {top.map((skill, i) => (
        <div className="kw" key={skill.Name}>
          <div className="rk">{String(i + 1).padStart(2, "0")}</div>
          <div className="term">{skill.Name}</div>
          <div className="freq">
            <b>{Math.round(skill.Percentage)}%</b>
          </div>
          <div className="matchbar">
            <i
              style={{
                width: `${(skill.Percentage / max) * 100}%`,
                animationDelay: `${i * 55}ms`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
