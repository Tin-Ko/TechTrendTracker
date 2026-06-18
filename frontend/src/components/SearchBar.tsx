import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

type Size = "hero" | "compact";

type Props = {
  initialValue?: string;
  size?: Size;
};

export default function SearchBar({ initialValue = "", size = "hero" }: Props) {
  const [value, setValue] = useState(initialValue);
  const navigate = useNavigate();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    navigate(`/chart?job_title=${encodeURIComponent(trimmed)}`);
  };

  const isHero = size === "hero";
  const wrapperClasses = isHero
    ? "flex flex-row items-center border-4 border-gray-300 rounded-full py-3 pr-3 pl-10 lg:w-[50%] w-[95%] lg:h-[100px] h-[70px]"
    : "flex flex-row items-center border-2 border-gray-300 border-opacity-70 rounded-full py-2 pr-2 pl-7 lg:h-[60px] h-[40px] w-full";
  const inputClasses = isHero
    ? "flex-grow bg-transparent border-none outline-none text-white text-lg lg:text-2xl placeholder-gray-300"
    : "flex-grow bg-transparent border-none outline-none text-white text-lg lg:text-xl placeholder-gray-300";
  const buttonSizeClasses = isHero
    ? "lg:w-[48px] lg:h-[48px] w-[30px] h-[30px]"
    : "lg:w-[32px] lg:h-[32px] w-[24px] h-[24px]";

  return (
    <form className={wrapperClasses} onSubmit={onSubmit}>
      <input
        type="text"
        name="job_title"
        className={inputClasses}
        placeholder="What positions are you looking for?"
        required
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button
        className="bg-gray-300 aspect-square h-full rounded-full flex items-center justify-center"
        type="submit"
        aria-label="Search"
      >
        <svg
          className={`${buttonSizeClasses} text-gray-800`}
          aria-hidden="true"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <path
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1"
            d="M19 12H5m14 0-4 4m4-4-4-4"
          />
        </svg>
      </button>
    </form>
  );
}
