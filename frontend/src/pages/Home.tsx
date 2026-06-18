import SearchBar from "../components/SearchBar";

export default function Home() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center">
      <div
        id="logo-text"
        className="flex items-center justify-center text-9xl font-bold tracking-tight drop-shadow-lg mb-28"
      >
        TTT
      </div>
      <SearchBar size="hero" />
    </div>
  );
}
