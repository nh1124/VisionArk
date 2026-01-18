
import asyncio
import json
import sys
import os

# Add core/backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from queue_system.manager import QueueManager
from nodes.system.router_node import RouterNode

async def worker():
    print("🚀 Worker started. Waiting for tasks... (V3 Router Enabled)")
    manager = QueueManager()
    
    while True:
        try:
            # Poll Redis (Blocking) in executor to stay async-friendly
            loop = asyncio.get_running_loop()
            task_data = await loop.run_in_executor(None, manager.dequeue)
            
            if task_data:
                task_id = task_data.get("task_id")
                user_id = task_data.get("user_id")
                message = task_data.get("message")
                context = task_data.get("context") or {}
                
                # Inject user_id/task_id into context for Node usage
                context["user_id"] = user_id
                context["task_id"] = task_id
                
                print(f"📦 Processing task {task_id} from {user_id}")
                manager.update_status(task_id, "processing")
                
                try:
                    # Initialize DB Session for this task
                    from models.database import get_async_engine, get_async_session_maker
                    engine = get_async_engine()
                    async_session_cls = get_async_session_maker(engine)
                    
                    async with async_session_cls() as db_session:
                        context["db_session"] = db_session
                        
                        # Initialize Router
                        print(f"Worker: Processing task {task_id}")
                        router = RouterNode(context)
                        
                        # 1. Router Pre-process (Global setup, File Uploads)
                        await router.pre_process()
                        
                        # 2. Routing (Determine Target Node)
                        target_node = await router.route(message)
                        print(f"Worker: Routed to {target_node.__class__.__name__}")
                        
                        # 3. Target Node Lifecycle
                        if target_node != router:
                             # Pre-process target (e.g. Memory Context loading)
                            await target_node.pre_process()
                            # Process
                            result = await target_node.process(message)
                            
                            # IMMEDIATE RESPONSE: Update status to completed so UI gets it
                            manager.update_status(task_id, "completed", result)
                            print(f"Worker: Task {task_id} completed. Result type: {type(result)}. Content: {str(result)[:200]}...")
                        
                            # Post-process (Background tasks: Advocate, Scheduler, etc.)
                            try:
                                print(f"Worker: Starting post-process for {task_id}")
                                await target_node.post_process(result)
                                print(f"Worker: Finished post-process for {task_id}")
                            except Exception as e:
                                print(f"Worker: Post-process warning (non-fatal): {e}")

                        else:
                            # Router handled it (e.g. System Command)
                            result = await router.process(message)
                            # Router tasks usually don't have heavy post-process, but keep consistency
                            manager.update_status(task_id, "completed", result)
                            await router.post_process(result)

                        # Status updated above
                    
                except Exception as e:
                    print(f"❌ Task {task_id} failed: {e}")
                    import traceback
                    traceback.print_exc()
                    manager.update_status(task_id, "failed", str(e))
            
        except Exception as e:
            print(f"⚠️ Worker error: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    asyncio.run(worker())
