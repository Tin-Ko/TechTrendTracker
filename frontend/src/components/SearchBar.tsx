import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

type Variant = "hero" | "compact";

type Props = {
  initialValue?: string;
  variant?: Variant;
};

export default function SearchBar({ initialValue = "", variant = "hero" }: Props) {
  const [value, setValue] = useState(initialValue);
  const navigate = useNavigate();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    navigate(`/chart?job_title=${encodeURIComponent(trimmed)}`);
  };

  const isHero = variant === "hero";

  return (
    <form onSubmit={onSubmit} className={isHero ? "search" : "search search--compact"}>
      <input
        aria-label="Search for a job title"
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={isHero ? "Enter a job title to scan…" : "Search a job title…"}
        required
      />
      <button type="submit" className="btn" aria-label="Scan">
        {isHero ? "Scan ▸" : "▸"}
      </button>
    </form>
  );
}
