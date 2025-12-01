"""
Fix existing spokes that are missing directories
Run this once to add artifacts/ and refs/ to all existing spokes
"""
from pathlib import Path
from utils.paths import SPOKES_DIR, get_spoke_dir

def fix_spoke_directories():
    """Add missing directories to existing spokes"""
    if not SPOKES_DIR.exists():
        print("No spokes directory found")
        return
    
    fixed_count = 0
    for spoke_dir in SPOKES_DIR.iterdir():
        if spoke_dir.is_dir():
            # Create artifacts and refs if they don't exist
            artifacts = spoke_dir / "artifacts"
            refs = spoke_dir / "refs"
            
            missing = []
            if not artifacts.exists():
                artifacts.mkdir(exist_ok=True)
                missing.append("artifacts/")
            
            if not refs.exists():
                refs.mkdir(exist_ok=True)
                missing.append("refs/")
            
            if not (spoke_dir / "system_prompt.md").exists():
                default_prompt = f"""# {spoke_dir.name.replace('_', ' ').title()}

You are a specialized execution agent for the {spoke_dir.name} project.
Focus on delivering high-quality work within this context.
"""
                (spoke_dir / "system_prompt.md").write_text(default_prompt, encoding='utf-8')
                missing.append("system_prompt.md")
            
            if missing:
                print(f"✅ Fixed {spoke_dir.name}: added {', '.join(missing)}")
                fixed_count += 1

    print(f"\n🎉 Fixed {fixed_count} spokes")

if __name__ == "__main__":
    fix_spoke_directories()
