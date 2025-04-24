import re
from typing import List, Dict, Any


class RequirementsParser:
    def __init__(self, canonical_skill_map: Dict[str, str] = None, tech_capitalization_map: Dict[str, str] = None) -> None:
        self.canonical_skill_map = canonical_skill_map or {}
        self.tech_capitalization_map = tech_capitalization_map


    
    def normalize_skill(self, skill: str) -> str:
        skill_normalized = skill.strip().lower()

        if "/" in skill_normalized:
            parts = skill_normalized.split("/")
            return [self.normalize_skill(part) for part in parts]
            

        if skill_normalized in self.canonical_skill_map.keys():
            skill_normalized = self.canonical_skill_map[skill_normalized]

        if skill_normalized in self.tech_capitalization_map.keys():
            skill_normalized = self.tech_capitalization_map[skill_normalized]

        skill_normalized = re.sub(r"[^\w\s\+\#]", "", skill_normalized)

        return skill_normalized

    
    def clean_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        raw_skills = data.get("skills", [])     # data.get() because it can still return something when the key doesn't exist

        if not isinstance(raw_skills, list):
            raw_skills = [raw_skills]
        
        cleaned_skills = set()

        for skill in raw_skills:
            if not isinstance(skill, str):
                continue

            normalized_skill = self.normalize_skill(skill)
            if isinstance(normalized_skill, list):
                for skill in normalized_skill:
                    cleaned_skills.add(skill)
            else:
                cleaned_skills.add(normalized_skill)

        return {
            **data,
            "skills": sorted(cleaned_skills)
        }
