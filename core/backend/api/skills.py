from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from models.database import get_async_db, Skill, NodeSkill, Node
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/api/skills", tags=["skills"])

class SkillUpdate(BaseModel):
    name: str
    description: str
    content: str
    is_active: bool

@router.get("")
async def list_skills(db: AsyncSession = Depends(get_async_db)):
    res = await db.execute(select(Skill).order_by(Skill.created_at.desc()))
    return res.scalars().all()

@router.get("/{skill_id}")
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_async_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill

@router.put("/{skill_id}")
async def update_skill(skill_id: str, update: SkillUpdate, db: AsyncSession = Depends(get_async_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    skill.name = update.name
    skill.description = update.description
    skill.content = update.content
    skill.is_active = update.is_active
    
    await db.commit()
    return skill

@router.delete("/{skill_id}")
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_async_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    await db.delete(skill)
    await db.commit()
    return {"message": "Skill deleted"}

# --- Node-Skill Association Endpoints ---

@router.get("/node/{node_id}")
async def list_node_skills(node_id: str, db: AsyncSession = Depends(get_async_db)):
    """List skills assigned to a node strictly by Node ID."""
    stmt = select(Skill).join(NodeSkill).filter(NodeSkill.node_id == node_id)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.put("/node/{node_id}")
async def update_node_skills(node_id: str, skill_ids: List[str], db: AsyncSession = Depends(get_async_db)):
    """Batch update skills assigned to a node strictly by Node ID."""
    # Verify node exists
    node = await db.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
        
    # Remove existing associations
    await db.execute(delete(NodeSkill).where(NodeSkill.node_id == node_id))
    
    # Add new associations
    for sid in skill_ids:
        # Verify skill exists
        skill = await db.get(Skill, sid)
        if skill:
            new_assoc = NodeSkill(node_id=node_id, skill_id=sid)
            db.add(new_assoc)
            
    await db.commit()
    return {"status": "success", "assigned_count": len(skill_ids)}

# --- Project-Aware Skill Endpoints ---

@router.get("/project/{project_id}")
async def list_project_skills(project_id: str, db: AsyncSession = Depends(get_async_db)):
    """List skills assigned to the main orchestrator agent of a project."""
    # Resolve project_id to its main PROJECT node
    stmt_node = select(Node.id).filter(Node.project_id == project_id, Node.node_type == "PROJECT")
    res_node = await db.execute(stmt_node)
    actual_node_id = res_node.scalar()

    if not actual_node_id:
        return []

    stmt = select(Skill).join(NodeSkill).filter(NodeSkill.node_id == actual_node_id)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.put("/project/{project_id}")
async def update_project_skills(project_id: str, skill_ids: List[str], db: AsyncSession = Depends(get_async_db)):
    """Batch update skills for the main orchestrator agent of a project."""
    # Resolve project_id to its main PROJECT node
    stmt_node = select(Node.id).filter(Node.project_id == project_id, Node.node_type == "PROJECT")
    res_node = await db.execute(stmt_node)
    actual_node_id = res_node.scalar()

    if not actual_node_id:
        raise HTTPException(status_code=404, detail="Project or Orchestrator Node not found")
        
    # Remove existing associations
    await db.execute(delete(NodeSkill).where(NodeSkill.node_id == actual_node_id))
    
    # Add new associations
    for sid in skill_ids:
        # Verify skill exists
        skill = await db.get(Skill, sid)
        if skill:
            new_assoc = NodeSkill(node_id=actual_node_id, skill_id=sid)
            db.add(new_assoc)
            
    await db.commit()
    return {"status": "success", "assigned_count": len(skill_ids)}
