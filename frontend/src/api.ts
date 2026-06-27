import type { RecommendationsResponse, SkillsResponse } from "./types";

export async function fetchSkills(jobTitle: string): Promise<SkillsResponse> {
  const resp = await fetch(`/skills?job_title=${encodeURIComponent(jobTitle)}`);
  if (!resp.ok) {
    throw new Error(`/skills failed: ${resp.status} ${resp.statusText}`);
  }
  return (await resp.json()) as SkillsResponse;
}

export async function fetchRecommendations(skills: string[]): Promise<RecommendationsResponse> {
  const q = encodeURIComponent(skills.join(","));
  const resp = await fetch(`/recommendations?skills=${q}`);
  if (!resp.ok) {
    throw new Error(`/recommendations failed: ${resp.status} ${resp.statusText}`);
  }
  return (await resp.json()) as RecommendationsResponse;
}
