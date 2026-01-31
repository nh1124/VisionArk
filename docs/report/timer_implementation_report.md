# Technical Report: Timer & Scheduled Notification Implementation

This report outlines the proposed strategy for implementing a "Timer" and "Scheduled Notification" feature in VisionArk, leveraging the existing Notification System and Automated Execution System (AES).

## 1. Overview

The goal is to allow users (via chat or UI) and agents to set timers or schedule alerts for specific times. When the time expires, a real-time notification should be pushed to the user's interface.

## 2. Backend Architecture

The implementation will utilize the **Automated Execution System (AES)**, which is already designed for decoupled, time-based task execution.

### Database Layer
- **Table**: `scheduled_tasks`
- **Fields for Timer**:
  - `task_type`: `SYSTEM_TIMER`
  - `scheduled_at`: The exact time (UTC) when the timer should fire.
  - `payload`: `{ "title": "...", "content": "...", "link": "..." }`

### AES Handler Registration
A new handler `TimerHandler` will be registered in `aes_system_handlers.py`:

```python
@register_aes_handler("SYSTEM_TIMER")
class TimerHandler(BaseAESHandler):
    async def run(self, context: Dict[str, Any]):
        from services.notification_service import NotificationService
        from models.database import NotificationType
        
        service = NotificationService(self.db)
        await service.create_notification(
            user_id=self.user_id,
            title=context.get("title", "Timer Expired"),
            content=context.get("content", "Your timer has finished."),
            type=NotificationType.INFO,
            link=context.get("link")
        )
```

### Dispatch Flow
1. **Request**: User types `/timer 10m` or Agent uses `set_timer` tool.
2. **Scheduling**: A record is added to `scheduled_tasks` with `scheduled_at = now + 10m`.
3. **Dispatch**: `AESDispatcher` polls the DB, finds the task at the 10-minute mark, and enqueues it to Redis.
4. **Execution**: A Worker picks up the task, runs `TimerHandler`, which calls `NotificationService`.
5. **Delivery**: `NotificationService` publishes to Redis Pub/Sub, and the WebSocket pushes it to the Frontend.

## 3. Frontend UI/UX

To make timers useful, users need to see them *before* they expire.

### Active Timers View
- **Location**: A "Timers" section within the Notification Bell dropdown or a dedicated floating widget.
- **Functionality**:
  - Fetch active `SYSTEM_TIMER` tasks from `/api/scheduler/timers`.
  - Local countdown logic (`setInterval`) to show remaining time.
  - Visuals: Circular progress bar or countdown text.

### Notification Feedback
- When a timer expires, the existing WebSocket integration will trigger a **Toast** notification with a sound (optional).
- The Bell icon will update its badge count.

## 4. Proposed Interaction

### User Commands
- `/timer 15m "Check the oven"`
- `/remind 2026-02-01 10:00 "Team Meeting"`

### Agent Integration
Agents will be given a `SetTimerTool`:
- Input: `minutes_from_now`, `message`.
- This allows agents to say: "I'll start research now and remind you in 30 minutes to review the findings."

---
*Created: 2026-01-30*
