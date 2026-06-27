import { Link } from "react-router-dom";

type Props = {
  titles: string[] | null | undefined;
};

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
