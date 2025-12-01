"""
Demo script to test the MVP backend
Creates sample tasks, expands them, and tests LBS calculations
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from datetime import date, timedelta
from models.database import init_database, get_engine, get_session, Task, SystemConfig
from services.lbs_engine import LBSEngine
from agents.hub_agent import HubAgent
from agents.spoke_agent import SpokeAgent
import uuid


def setup_demo_data(session):
    """Create sample tasks for testing"""
    print("📝 Creating demo tasks...")
    
    # Weekly research seminar
    seminar = Task(
        task_id=f"T-{uuid.uuid4().hex[:8]}",
        task_name="Research Seminar",
        context="research_photonics",
        base_load_score=2.5,
        rule_type="WEEKLY",
        mon=True,
        wed=True,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today() + timedelta(days=90),
        active=True
    )
    
    # Daily literature review
    lit_review = Task(
        task_id=f"T-{uuid.uuid4().hex[:8]}",
        task_name="Literature Review",
        context="research_photonics",
        base_load_score=1.5,
        rule_type="WEEKLY",
        mon=True,
        tue=True,
        wed=True,
        thu=True,
        fri=True,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=60),
        active=True
    )
    
    # Monthly budget review
    budget = Task(
        task_id=f"T-{uuid.uuid4().hex[:8]}",
        task_name="Budget Review",
        context="finance",
        base_load_score=3.0,
        rule_type="MONTHLY_DAY",
        month_day=25,
        start_date=date.today() - timedelta(days=30),
        active=True
    )
    
    # One-time thesis deadline
    thesis = Task(
        task_id=f"T-{uuid.uuid4().hex[:8]}",
        task_name="Thesis Submission",
        context="research_photonics",
        base_load_score=8.0,
        rule_type="ONCE",
        due_date=date.today() + timedelta(days=30),
        active=True
    )
    
    session.add_all([seminar, lit_review, budget, thesis])
    session.commit()
    
    print(f"✅ Created {len([seminar, lit_review, budget, thesis])} demo tasks")
    return [seminar, lit_review, budget, thesis]


def test_lbs_engine(session):
    """Test LBS calculations"""
    print("\n🧮 Testing LBS Engine...")
    
    engine = LBSEngine(session)
    
    # Expand tasks for next 14 days
    start = date.today()
    end = start + timedelta(days=14)
    
    print(f"   Expanding tasks from {start} to {end}...")
    engine.expand_tasks(start, end)
    
    # Calculate today's load
    today_load = engine.calculate_daily_load(date.today())
    print(f"\n📊 Today's Load ({date.today()}):")
    print(f"   Base Load: {today_load['base_load']}")
    print(f"   Task Count: {today_load['task_count']}")
    print(f"   Unique Contexts: {today_load['unique_contexts']}")
    print(f"   Adjusted Load: {today_load['adjusted_load']:.2f} / {today_load['cap']}")
    print(f"   Level: {today_load['level']}")
    
    # Weekly stats
    weekly = engine.get_weekly_stats(start)
    print(f"\n📈 Weekly Stats:")
    print(f"   Average Load: {weekly['average_load']}")
    print(f"   Over-capacity Days: {weekly['over_days']}")
    print(f"   Recovery Rate: {weekly['recovery_rate']}%")
    
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
    print("\n3️⃣ Testing LBS calculations...")
    test_lbs_engine(session)
    
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
