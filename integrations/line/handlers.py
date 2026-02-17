from va_sdk import aes_registry, task_registry, reply_registry, TaskType, ServiceRegistry, ExternalIdentity, AsyncSessionLocal
from sqlalchemy import select
from .client import get_line_client

# LINE Integration Handlers
#
# This module registers two handler types for the Worker:
#   1. task_registry ("line_reply")  - Handles LINE reply tasks dispatched via the queue.
#   2. reply_registry ("line")       - Hooks into Worker._handle_external_reply() to send
#                                      agent responses back to LINE (reply token or push).
#

# --- Task Handlers ---

@task_registry.register("line_reply")
async def handle_line_reply_task(task, db_session):
    """
    Worker handler for TaskType.LINE_REPLY
    """
    # specialized handler for LINE replies
    reg_user_id = task.context.get("registry_user_id")
    line_user_id = task.context.get("line_user_id") # The recipient
    
    if not reg_user_id or not line_user_id:
        print("❌ LINE Reply Task missing user IDs")
        return

    client = await get_line_client(reg_user_id, db_session)
    if client:
        reply_text = task.context.get("reply_text")
        await client.push_message(line_user_id, reply_text)
        print(f"[Worker] Replied to LINE (Shared/Individual) via client for task {task.id}")
        
        # Update task status
        from shared.database import ScheduledTask, ScheduledTaskStatus
        t = await db_session.get(ScheduledTask, task.id)
        if t:
            t.status = ScheduledTaskStatus.COMPLETED
            t.result = {"success": True, "channel": "line"}
            await db_session.commit()

# --- Reply Handlers ---
# (worker._handle_external_reply)

@reply_registry.register("line")
async def handle_line_reply_hook(result, context, db_session):
    """
    Registry handler for 'external_reply_channel' == 'line'
    """
    user_id = context.get("user_id")
    # The registry_user_id is the one who configured the bot
    reg_user_id = context.get("registry_user_id") or user_id
    
    # Convert result to string
    message_text = str(result) if not isinstance(result, str) else result

    client = await get_line_client(reg_user_id, db_session)
    
    if client:
        reply_token = context.get("line_reply_token")
        line_user_id = context.get("line_user_id")
        
        if reply_token:
            try:
                await client.reply_message(reply_token, message_text)
                print(f"[Worker/LINE] Replied via token for task {context.get('task_id')}")
                return
            except Exception as re:
                print(f"[Worker/LINE] Reply token failed/expired: {re}")
        
        if line_user_id:
            # Fallback to push message
            await client.push_message(line_user_id, message_text)
            print(f"[Worker/LINE] Sent push message for task {context.get('task_id')}")
    else:
        print(f"[Worker/LINE] No LINE client found for user {reg_user_id}")
