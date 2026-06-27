import { Link } from "react-router-dom";

import SearchBar from "./SearchBar";

type Props = {
  /** Show the compact search box in the nav (used on the report page). */
  showSearch?: boolean;
  initialValue?: string;
};

export default function NavBar({ showSearch = false, initialValue = "" }: Props) {
  return (
    <div className="nav">
      <div className="wrap row">
        <Link to="/" className="brand" aria-label="Tech Trend Tracker — home">
          <span className="sq" />
          Tech Trend Tracker
        </Link>

        {showSearch ? (
          <div className="nav-search">
            <SearchBar variant="compact" initialValue={initialValue} />
          </div>
        ) : (
          <div className="spacer" />
        )}

        <span className="badge">REAL POSTINGS · LIVE SKILLS</span>
      </div>
    </div>
  );
}
