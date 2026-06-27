// Matches backend/services/skills_service.go SkillsResponse.

export type Skill = {
  Name: string;
  Count: number;
  Percentage: number;
};

export type SkillsResponse = {
  JobTitle: string;
  JobCount: number;
  SkillsCount: number;
  AllSkills: string[] | null;
  Skills: Skill[] | null;
  RelatedTitles: string[] | null;
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
