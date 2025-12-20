"""
Demo script to test the MVP backend
Creates sample tasks, expands them, and tests LBS calculations
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from datetime import date, timedelta
from models.database import init_database, get_engine, get_session
from agents.hub_agent import HubAgent
from agents.spoke_agent import SpokeAgent
import uuid


def setup_demo_data(session):
    """LBS data migration demo"""
    print("ℹ️ LBS tasks should be created via the new /tasks API or UI.")
    return []


def test_lbs_overview():
    """LBS testing moved to microservice repo"""
    print("\nℹ️ LBS data is now managed by the standalone microservice.")
    return True


def test_hub_agent(session):
    """Test Hub AI agent"""
    print("\n🤖 Testing Hub Agent...")
    
    hub = HubAgent(session)
    
    print("   Asking Hub about current workload...")
    response = hub.chat_with_context("What's my current workload status? Any concerns?")
    
    print(f"\n💬 Hub Response:\n{response}\n")
    
    return True


def test_spoke_agent():
    """Test Spoke AI agent"""
    print("\n💎 Testing Spoke Agent...")
    
    # Create spoke directory
    spoke_dir = Path("spokes/research_photonics")
    spoke_dir.mkdir(parents=True, exist_ok=True)
    (spoke_dir / "artifacts").mkdir(exist_ok=True)
    (spoke_dir / "refs").mkdir(exist_ok=True)
    
    # Create custom spoke prompt
    spoke_prompt = """# Research Photonics Spoke

You are a specialized agent for photonics research.
Focus on experimental design, data analysis, and literature review.
Be rigorous and scientifically precise.
"""
    (spoke_dir / "system_prompt.md").write_text(spoke_prompt)
    
    spoke = SpokeAgent("research_photonics")
    
    print("   Chatting with Spoke...")
    response = spoke.chat("I need to design an experiment to measure outdoor lighting conditions. Any suggestions?")
    
    print(f"\n💬 Spoke Response:\n{response}\n")
    
    # Test meta-action generation
    print("   Generating meta-action for task completion...")
    meta = spoke.generate_completion_report("Literature Review", "T-12345678")
    print(f"\n📤 Meta-action XML:\n{meta}\n")
    
    return True


def main():
    """Run all tests"""
    print("="*60)
    print("🚀 AI TaskManagement OS - MVP Backend Demo")
    print("="*60)
    
    # Initialize database
    print("\n1️⃣ Initializing database...")
    engine = init_database("sqlite:///./hub_data/lbs_master.db")
    session = get_session(engine)
    
    # Create demo data
    print("\n2️⃣ Setting up demo data...")
    tasks = setup_demo_data(session)
    
    # Test LBS engine
    print("\n3️⃣ Skipping local LBS calculations (remote microservice)...")
    test_lbs_overview()
    
    # Test Hub agent
    print("\n4️⃣ Testing Hub AI agent...")
    test_hub_agent(session)
    
    # Test Spoke agent
    print("\n5️⃣ Testing Spoke AI agent...")
    test_spoke_agent()
    
    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)
    print("\n💡 Next steps:")
    print("   - Start backend: cd app/backend && python main.py")
    print("   - Test API: http://localhost:8000/docs")
    print("   - Create frontend for visual interface")
    
    session.close()


if __name__ == "__main__":
    main()
