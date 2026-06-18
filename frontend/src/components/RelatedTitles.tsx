import { Link } from "react-router-dom";

type Props = {
  titles: string[] | null | undefined;
};

export default function RelatedTitles({ titles }: Props) {
  if (!titles || titles.length === 0) return null;
  return (
    <div className="flex flex-row flex-wrap gap-2 justify-center lg:w-[60%] w-[80%] mt-6 min-h-[40px]">
      {titles.map((title) => (
        <Link
          key={title}
          to={`/chart?job_title=${encodeURIComponent(title)}`}
          className="px-4 py-2 rounded-full bg-zinc-600/50 border border-zinc-400 border-opacity-50 text-white text-sm hover:bg-zinc-500/70 transition"
        >
          {title}
        </Link>
      ))}
    </div>
  );
}
