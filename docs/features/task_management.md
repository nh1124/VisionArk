# Task Management Feature

The Task Management system in VisionArk provides a unified interface for tracking, scheduling, and prioritizing tasks across different projects.

## Key Features

### 1. View Modes
The task page supports three distinct view modes:
- **List View**: A focused list of pending and completed tasks.
- **Monthly Calendar**: A grid-based month view for long-term planning and scheduling.
- **Weekly Timeline**: A time-block based weekly view for daily scheduling.

### 2. Navigation & Date Shifting
- In **Calendar** and **Timeline** views, users can navigate between months/weeks using the header controls (`<`, `Today`, `>`).
- The **Today** button instantly resets the view to the current period.
- Selecting **Today** or **My Day** filters in the sidebar also synchronizes the navigation to the current date.

### 3. Smart Filtering
- **Sidebar Categories**:
    - **Today**: Pending tasks due today.
    - **My Day**: Personal focus list (flagged via the star icon). This filter is global and shows focus tasks regardless of the current navigation date.
    - **Planned**: All future tasks with a due date.
    - **Inbox**: All active tasks without specific project filters.
- **Project Filtering**: 
    - Users can filter tasks by specific projects (contexts).
    - An **All Tasks** button is available in the project section to quickly reset project-specific filters.
    - Filtering is consistently applied across all view modes (List, Calendar, Heatmap, and Timeline).

### 4. Focused Day Details (Calendar View)
- In the Monthly Calendar, clicking on a day cell opens a **Focus List** overlay.
- This panel allows for quick task viewing and addition without leaving the calendar grid.
- It supports a sequential flow to the **Task Edit** panel and back.

## Technical Implementation

- **State Management**: Managed via `useTaskStore` (Zustand), ensuring synchronization across sidebar, headers, and calendar components.
- **State Synchronization**: Toggling priorities (My Day) or updating task details triggers global state updates to maintain consistency.
- **UI Components**:
    - `UnifiedTasksPage`: Main page component handling navigation logic.
    - `GridCalendar`: Monthly grid renderer.
    - `TimelineCalendar`: Weekly scheduler.
    - `TaskSidebar`: Contextual filter management.
