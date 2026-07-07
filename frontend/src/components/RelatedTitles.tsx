import { Link } from "react-router-dom";

type Props = {
  titles: string[] | null | undefined;
};

// TODO(hierarchical search §9.3) 1. What to do:
//    Two display-only changes once the structured backend path is live:
//    (a) titles arriving here become lowercase CANONICAL names ("backend
//        engineer") instead of raw scraped strings — title-case them for
//        display (the links must keep the original lowercase value, which
//        round-trips through resolution to the same plan anyway);
//    (b) optionally render a small caption from SkillsResponse.Resolved on
//        the chart page ("Showing: backend engineer · family: software
//        engineer") — pass Resolved down from the page component.
// TODO 2. Recommended approach:
//    A 3-line titleCase helper in this file (split on space, upper the
//    first letter of each word) is enough; don't reach for a library.
//    Guard the caption behind `resolved && resolved.MatchMode ===
//    "structured"` — a fallback match has no family worth announcing.
// TODO 3. Implementation details:
//    - Acronyms will look off ("Ml Engineer", "Qa Engineer") — either keep
//      a tiny uppercase-list {ml, qa, ai, ios, llm, nlp, sre} in the helper
//      or accept it for v1. Decide; don't half-fix in two places.
export default function RelatedTitles({ titles }: Props) {
  if (!titles || titles.length === 0) return null;
  return (
    <div className="related">
      <div className="h">▸ RELATED ROLES</div>
      <div className="chips">
        {titles.map((title) => (
          <Link key={title} to={`/chart?job_title=${encodeURIComponent(title)}`}>
            {title}
          </Link>
        ))}
      </div>
    </div>
  );
}
