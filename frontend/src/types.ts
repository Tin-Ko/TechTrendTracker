// Matches backend/services/skills_service.go SkillsResponse.

export type Skill = {
  Name: string;
  Count: number;
  Percentage: number;
};

// Hierarchical search (§9.3): how the backend matched this query. Null until
// the structured path is live server-side.
export type ResolvedInfo = {
  CanonicalTitle: string;
  RoleFamily: string;
  Specializations: string[] | null;
  MatchMode: string; // "structured" | "fallback"
};

export type SkillsResponse = {
  JobTitle: string;
  JobCount: number;
  SkillsCount: number;
  AllSkills: string[] | null;
  Skills: Skill[] | null;
  RelatedTitles: string[] | null;
  Resolved: ResolvedInfo | null;
};

// Matches backend/services/recommend_service.go.

export type ProjectRec = {
  Title: string;
  Level: string;
  Blurb: string;
  Skills: string[];
};

export type RecommendationsResponse = {
  TopSkills: string[] | null;
  Projects: ProjectRec[] | null;
};
