"""
Project Creator Node - System node for generating project names and system prompts from user prompts.
"""
from typing import Any, Dict, Optional
from nodes.base_node import BaseNode
from models.message import Message, MessageRole
from datetime import datetime


class ProjectCreatorNode(BaseNode):
    """
    System node that creates new projects from user prompts.
    Uses LLM to generate:
    1. A concise project name from the initial prompt
    2. A tailored system prompt for the project agent
    """
    
    def __init__(self, context: Dict[str, Any], status_callback: Optional[Any] = None):
        super().__init__(context, status_callback)
        self.tools = []  # No tools needed for this node
    
    async def on_enter(self):
        """Load API key for LLM access."""
        from models.database import get_async_engine, get_async_session_maker, UserSettings
        from sqlalchemy import select
        
        engine = get_async_engine()
        async_session_cls = get_async_session_maker(engine)
        session = async_session_cls()
        
        try:
            result = await session.execute(
                select(UserSettings).filter(UserSettings.user_id == self.user_id)
            )
            settings = result.scalars().first()
            
            if settings and settings.gemini_api_key:
                self.context['api_key'] = settings.gemini_api_key
            else:
                self.context['api_key'] = None
        finally:
            await session.close()
    
    async def generate_project_name_and_prompt(self, user_prompt: str) -> Dict[str, str]:
        """
        Use LLM to generate both a project name and a tailored system prompt.
        Returns dict with 'name' and 'system_prompt' keys.
        """
        system_prompt = """You are a project setup assistant. Given a user's project description, generate:
1. A concise project name (snake_case, 2-4 words)
2. A tailored system prompt for an AI assistant that will help with this specific project

RULES FOR PROJECT NAME:
- Use snake_case format (lowercase with underscores)
- Keep it short: 2-4 words maximum
- Make it descriptive but concise
- No special characters except underscores

RULES FOR SYSTEM PROMPT:
- Start with "You are a specialized AI assistant for..."
- Include specific guidance about the project domain
- Mention relevant capabilities the assistant should have
- Keep it between 100-300 words
- Be specific to the user's needs

OUTPUT FORMAT (JSON only, no markdown):
{
  "name": "project_name_here",
  "system_prompt": "You are a specialized AI assistant for..."
}

Examples:
User: "Help me build a web scraper for news articles"
{
  "name": "news_web_scraper",
  "system_prompt": "You are a specialized AI assistant for web scraping and data extraction. You help design, implement, and maintain web scrapers for news articles. Your expertise includes: Python libraries like BeautifulSoup, Scrapy, and Selenium; handling dynamic content and JavaScript-rendered pages; managing rate limits and respecting robots.txt; parsing HTML and extracting structured data; storing scraped data efficiently. You provide clean, well-documented code and follow best practices for ethical web scraping."
}

User: "Plan my thesis research on machine learning"
{
  "name": "thesis_ml_research",
  "system_prompt": "You are a specialized AI assistant for academic research in machine learning. You help plan, structure, and execute thesis research. Your expertise includes: literature review and synthesis; research methodology design; experiment planning and evaluation metrics; academic writing and citation management; statistical analysis and result interpretation. You understand academic standards, can help formulate research questions, and guide through the thesis writing process from proposal to defense."
}
"""
        
        if not self.context.get('api_key'):
            # Fallback: generate defaults
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return {
                "name": f"project_{timestamp}",
                "system_prompt": "You are a specialized AI assistant for this project. Help the user manage tasks, analyze data, and generate insights."
            }
        
        messages = [
            Message(
                role=MessageRole.USER,
                content=f"Create a project setup for: {user_prompt}",
                timestamp=datetime.now()
            )
        ]
        
        try:
            response = await self.chat_with_tools(
                system_prompt=system_prompt,
                message_history=messages,
                tool_definitions=[],
                tool_functions={}
            )
            
            # Parse JSON response
            import json
            import re
            
            content = response.content.strip()
            # Try to extract JSON from the response
            json_match = re.search(r'\{[^{}]*"name"[^{}]*"system_prompt"[^{}]*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group()
            
            try:
                data = json.loads(content)
                name = data.get("name", "").strip().lower()
                name = name.replace('"', '').replace("'", '').replace(' ', '_')
                name = ''.join(c for c in name if c.isalnum() or c == '_')
                
                if len(name) < 3:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    name = f"project_{timestamp}"
                
                return {
                    "name": name[:50],
                    "system_prompt": data.get("system_prompt", "You are a specialized AI assistant for this project.")
                }
            except json.JSONDecodeError:
                # Fallback parsing
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                return {
                    "name": f"project_{timestamp}",
                    "system_prompt": "You are a specialized AI assistant for this project. Help the user manage tasks, analyze data, and generate insights."
                }
                
        except Exception as e:
            print(f"[ProjectCreatorNode] LLM error: {e}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return {
                "name": f"project_{timestamp}",
                "system_prompt": "You are a specialized AI assistant for this project. Help the user manage tasks, analyze data, and generate insights."
            }
    
    async def create_project(self, name: str, system_prompt: str) -> Dict[str, Any]:
        """
        Create the project in the database and on disk.
        Does NOT save initial message - that will be handled by the queue/worker.
        Returns project details.
        """
        from models.database import (
            get_async_engine, get_async_session_maker, 
            Node, Project
        )
        from utils.paths import get_project_dir, validate_name, update_project_name_cache as update_cache
        from sqlalchemy import select
        from uuid import uuid4
        
        # Validate name
        valid, error = validate_name(name, "project_name")
        if not valid:
            name = name.replace('-', '_').replace(' ', '_')
            name = ''.join(c for c in name if c.isalnum() or c == '_')
        
        engine = get_async_engine()
        async_session_cls = get_async_session_maker(engine)
        session = async_session_cls()
        
        try:
            # Check if project name exists, append number if needed
            display_name = name.replace('_', ' ').title()
            base_display_name = display_name
            counter = 1
            while True:
                result = await session.execute(
                    select(Project).filter(
                        Project.user_id == self.user_id,
                        Project.name == display_name,
                        Project.status != "archived"
                    )
                )
                if not result.scalars().first():
                    break
                display_name = f"{base_display_name} {counter}"
                counter += 1
            
            # 1. Create Project
            project_id = str(uuid4())
            new_project = Project(
                id=project_id,
                user_id=self.user_id,
                name=display_name,
                status="active"
            )
            session.add(new_project)
            
            # 2. Create Primary Node (Agent)
            node_id = str(uuid4()) # We can use the same as project_id if we want, but let's decouple
            new_node = Node(
                id=node_id,
                project_id=project_id,
                node_type="PROJECT",
                display_name="Orchestrator",
                system_prompt=system_prompt,
                status="active",
                version=1
            )
            session.add(new_node)
            
            # Update cache for folder resolution
            update_cache(self.user_id, project_id, display_name)
            
            # 3. Create directory structure
            project_dir = get_project_dir(self.user_id, project_id)
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "files").mkdir(exist_ok=True)
            (project_dir / "artifacts").mkdir(exist_ok=True)
            (project_dir / "refs").mkdir(exist_ok=True)
            
            await session.commit()
            
            return {
                "success": True,
                "project_name": display_name,
                "project_id": project_id,
                "node_id": node_id
            }
            
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()
    
    async def on_execute(self, message: str) -> Dict[str, Any]:
        """
        Main processing: generate name + system prompt, create project.
        The initial prompt will be processed by the queue/worker after redirect.
        """
        print(f"[ProjectCreatorNode] Creating project from prompt: {message[:50]}...")
        
        # 1. Generate project name and system prompt
        generated = await self.generate_project_name_and_prompt(message)
        project_name = generated["name"]
        system_prompt = generated["system_prompt"]
        
        print(f"[ProjectCreatorNode] Generated name: {project_name}")
        print(f"[ProjectCreatorNode] Generated prompt: {system_prompt[:100]}...")
        
        # 2. Create the project (without saving initial message)
        result = await self.create_project(project_name, system_prompt)
        
        return result
    
    async def on_exit(self, result: Any):
        pass
