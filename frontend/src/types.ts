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
