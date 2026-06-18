import type { SkillsResponse } from "./types";

export async function fetchSkills(jobTitle: string): Promise<SkillsResponse> {
  const resp = await fetch(`/skills?job_title=${encodeURIComponent(jobTitle)}`);
  if (!resp.ok) {
    throw new Error(`/skills failed: ${resp.status} ${resp.statusText}`);
  }
  return (await resp.json()) as SkillsResponse;
}
