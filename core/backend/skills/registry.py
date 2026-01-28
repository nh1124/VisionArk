import os
import yaml
import uuid
from typing import Dict, Any, List
from sqlalchemy import select
from models.database import AsyncSessionLocal, Skill

class SkillRegistry:
    def __init__(self, search_paths: List[str]):
        self.search_paths = search_paths

    def parse_skill_file(self, file_path: str) -> Dict[str, Any]:
        """Parse SKILL.md with YAML frontmatter."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if content.startswith('---'):
            try:
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    body = parts[2]
                    data = yaml.safe_load(frontmatter) or {}
                    data['content'] = body.strip()
                    return data
            except Exception as e:
                print(f"[SkillRegistry] Yaml error in {file_path}: {e}")
        
        return {"content": content.strip()}

    async def sync_skills(self):
        """Scan all search_paths and sync with database."""
        async with AsyncSessionLocal() as db:
            for root_dir in self.search_paths:
                if not os.path.exists(root_dir):
                    continue
                
                print(f"[SkillRegistry] Scanning {root_dir}...")
                
                # Recursive search for SKILL.md
                for root, dirs, files in os.walk(root_dir):
                    if "SKILL.md" in files:
                        md_path = os.path.join(root, "SKILL.md")
                        
                        # Generate a skill_id. 
                        # If in global skills/ folder: use folder name
                        # If in integrations/ folder: use path-based unique ID
                        rel_path = os.path.relpath(root, root_dir)
                        if rel_path == ".":
                             # Standalone SKILL.md in a root dir (e.g. integrations/line/SKILL.md)
                             # ID = parent folder name
                             skill_id = os.path.basename(root)
                        else:
                             # Skill in a subfolder (e.g. skills/competitor-analysis/ or integrations/line/skills/auth/)
                             skill_id = os.path.basename(root)

                        try:
                            skill_data = self.parse_skill_file(md_path)
                            name = skill_data.get('name', skill_id)
                            description = skill_data.get('description', '')
                            content = skill_data.get('content', '')
                            
                            # Prefix integration skills to avoid collisions if nested
                            if "integrations" in root_dir:
                                integration_name = os.path.basename(root_dir)
                                # Actually root_dir is 'core/backend/integrations' usually
                                # So rel_path might be 'line/skills/foo'
                                parts = rel_path.split(os.sep)
                                prefix = parts[0]
                                if skill_id != prefix:
                                    skill_id = f"{prefix}-{skill_id}"
                            
                            metadata = {k: v for k, v in skill_data.items() if k != 'content'}

                            res = await db.execute(select(Skill).filter(Skill.id == skill_id))
                            existing = res.scalars().first()

                            if existing:
                                existing.name = name
                                existing.description = description
                                existing.content = content
                                existing.metadata_payload = metadata
                                print(f"[SkillRegistry] Updated skill: {skill_id}")
                            else:
                                new_skill = Skill(
                                    id=skill_id,
                                    name=name,
                                    description=description,
                                    content=content,
                                    metadata_payload=metadata,
                                    is_draft=False
                                )
                                db.add(new_skill)
                                print(f"[SkillRegistry] Created skill: {skill_id}")
                        except Exception as e:
                            print(f"[SkillRegistry] Error parsing {md_path}: {e}")

            await db.commit()
            print("[SkillRegistry] Sync complete.")

# Global instance
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
search_paths = [
    os.path.join(backend_dir, "skills"),
    os.path.join(backend_dir, "integrations") # Support integration-embedded skills
]
skill_registry = SkillRegistry(search_paths)
