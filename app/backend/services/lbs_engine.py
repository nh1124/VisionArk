"""
LBS (Load Balancing System) calculation engine
Implements the expansion algorithm and load calculation formula from BLUEPRINT.md
"""
from datetime import date, timedelta
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
import math
from calendar import monthrange

from models.database import Task, TaskException, LBSDailyCache, SystemConfig, RuleType, ExceptionType


class LBSEngine:
    """Core LBS calculation and expansion logic"""
    
    def __init__(self, db_session: Session):
        self.session = db_session
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, float]:
        """Load system configuration (ALPHA, BETA, CAP, SWITCH_COST)"""
        configs = self.session.query(SystemConfig).all()
        return {c.key: float(c.value) for c in configs}
    
    def expand_tasks(self, start_date: date, end_date: date) -> None:
        """
        Expand task rules into daily cache for the given date range
        F3: Expansion Algorithm from BLUEPRINT
        """
        # Clear existing cache for the date range
        self.session.query(LBSDailyCache).filter(
            LBSDailyCache.target_date >= start_date,
            LBSDailyCache.target_date <= end_date
        ).delete()
        
        # Get all active tasks
        tasks = self.session.query(Task).filter(Task.active == True).all()
        
        current_date = start_date
        while current_date <= end_date:
            for task in tasks:
                if self._should_task_occur(task, current_date):
                    # Check for exceptions
                    exception = self._get_exception(task.task_id, current_date)
                    
                    if exception and exception.exception_type == ExceptionType.SKIP:
                        continue  # Skip this occurrence
                    
                    # Calculate load (base or override)
                    load = task.base_load_score
                    if exception and exception.exception_type == ExceptionType.OVERRIDE_LOAD:
                        load = exception.override_load_value
                    
                    # Create cache entry
                    cache_entry = LBSDailyCache(
                        target_date=current_date,
                        task_id=task.task_id,
                        calculated_load=load,
                        rule_type_snapshot=task.rule_type,
                        status="planned"
                    )
                    self.session.add(cache_entry)
            
            current_date += timedelta(days=1)
        
        self.session.commit()
        
        # Calculate overflow flags
        self._update_overflow_flags(start_date, end_date)
    
    def _should_task_occur(self, task: Task, target_date: date) -> bool:
        """
        F3: Rule Matching Logic
        Determine if a task should occur on the given date based on its rule
        """
        # Period validation
        if task.start_date and target_date < task.start_date:
            return False
        if task.end_date and target_date > task.end_date:
            return False
        
        rule = task.rule_type
        
        # ONCE: Single occurrence
        if rule == RuleType.ONCE:
            matches = target_date == task.due_date
            if task.due_date:  # Only log if due_date exists
                print(f"[LBS ONCE] task_id={task.task_id}, target_date={target_date}, due_date={task.due_date}, matches={matches}")
            return matches
        
        # WEEKLY: Specific weekdays
        if rule == RuleType.WEEKLY:
            weekday = target_date.weekday()  # 0=Mon, 6=Sun
            weekday_flags = [task.mon, task.tue, task.wed, task.thu, task.fri, task.sat, task.sun]
            return weekday_flags[weekday]
        
        # EVERY_N_DAYS: Interval-based
        if rule == RuleType.EVERY_N_DAYS:
            if not task.anchor_date or not task.interval_days:
                return False
            days_diff = (target_date - task.anchor_date).days
            return days_diff >= 0 and days_diff % task.interval_days == 0
        
        # MONTHLY_DAY: Specific day of month
        if rule == RuleType.MONTHLY_DAY:
            if not task.month_day:
                return False
            # Handle months with fewer days
            _, last_day = monthrange(target_date.year, target_date.month)
            target_day = min(task.month_day, last_day)
            return target_date.day == target_day
        
        # MONTHLY_NTH_WEEKDAY: Nth weekday of month (e.g., 3rd Monday)
        if rule == RuleType.MONTHLY_NTH_WEEKDAY:
            if not task.nth_in_month or not task.weekday_mon1:
                return False
            return self._is_nth_weekday(target_date, task.nth_in_month, task.weekday_mon1)
        
        return False
    
    def _is_nth_weekday(self, target_date: date, nth: int, weekday: int) -> bool:
        """Check if target_date is the Nth occurrence of weekday in its month"""
        # weekday: 1=Mon ... 7=Sun (convert to 0=Mon...6=Sun)
        target_weekday = (weekday - 1) % 7
        
        if target_date.weekday() != target_weekday:
            return False
        
        # Calculate which occurrence this is
        occurrence = (target_date.day - 1) // 7 + 1
        
        # Handle -1 (last occurrence)
        if nth == -1:
            # Check if this is the last occurrence in the month
            next_week = target_date + timedelta(days=7)
            return next_week.month != target_date.month
        
        return occurrence == nth
    
    def _get_exception(self, task_id: str, target_date: date) -> Optional[TaskException]:
        """Get exception rule for a specific task and date"""
        return self.session.query(TaskException).filter(
            TaskException.task_id == task_id,
            TaskException.target_date == target_date
        ).first()
    
    def _update_overflow_flags(self, start_date: date, end_date: date) -> None:
        """Mark days that exceed CAP as overflow"""
        cap = self.config.get("CAP", 8.0)
        
        current_date = start_date
        while current_date <= end_date:
            daily_total = self.calculate_daily_load(current_date)
            is_overflow = daily_total["adjusted_load"] > cap
            
            # Update all cache entries for this date
            self.session.query(LBSDailyCache).filter(
                LBSDailyCache.target_date == current_date
            ).update({"is_overflow": is_overflow})
            
            current_date += timedelta(days=1)
        
        self.session.commit()
    
    def calculate_daily_load(self, target_date: date) -> Dict:
        """
        F4: Load Adjustment Calculation
        Formula: Adjusted = Base + ALPHA × N^BETA + SWITCH_COST × max(U-1, 0)
        """
        # Get config
        alpha = self.config.get("ALPHA", 0.1)
        beta = self.config.get("BETA", 1.2)
        switch_cost = self.config.get("SWITCH_COST", 0.5)
        cap = self.config.get("CAP", 8.0)
        
        # Get all tasks for the date
        cache_entries = self.session.query(LBSDailyCache).filter(
            LBSDailyCache.target_date == target_date,
            LBSDailyCache.status != "skipped"
        ).all()
        
        if not cache_entries:
            return {
                "date": target_date,
                "base_load": 0.0,
                "task_count": 0,
                "unique_contexts": 0,
                "adjusted_load": 0.0,
                "level": "SAFE",
                "cap": cap,  # Added missing cap
                "tasks": []
            }
        
        # Calculate components
        base_load = sum(entry.calculated_load for entry in cache_entries)
        task_count = len(cache_entries)
        unique_contexts = len(set(
            self.session.query(Task).filter(Task.task_id == entry.task_id).first().context
            for entry in cache_entries
        ))
        
        # Apply formula
        count_penalty = alpha * (task_count ** beta)
        context_penalty = switch_cost * max(unique_contexts - 1, 0)
        adjusted_load = base_load + count_penalty + context_penalty
        
        # Determine warning level
        level = self._get_warning_level(adjusted_load, cap)
        
        return {
            "date": target_date,
            "base_load": round(base_load, 2),
            "task_count": task_count,
            "unique_contexts": unique_contexts,
            "count_penalty": round(count_penalty, 2),
            "context_penalty": round(context_penalty, 2),
            "adjusted_load": round(adjusted_load, 2),
            "level": level,
            "cap": cap,
            "tasks": [
                {
                    "task_id": entry.task_id,
                    "task_name": self.session.query(Task).filter(Task.task_id == entry.task_id).first().task_name,
                    "context": self.session.query(Task).filter(Task.task_id == entry.task_id).first().context,
                    "load": entry.calculated_load,
                    "status": entry.status
                }
                for entry in cache_entries
            ]
        }
    
    def _get_warning_level(self, adjusted_load: float, cap: float) -> str:
        """
        F5/F6/F7: Warning Indicators
        🟢 SAFE < 6.0
        🟡 WARNING 6.0-8.0
        🔴 DANGER 8.0-CAP
        🟣 CRITICAL > CAP
        """
        if adjusted_load > cap:
            return "CRITICAL"
        elif adjusted_load >= 8.0:
            return "DANGER"
        elif adjusted_load >= 6.0:
            return "WARNING"
        else:
            return "SAFE"
    
    def get_weekly_stats(self, start_date: date) -> Dict:
        """Calculate weekly statistics (7 days from start_date)"""
        end_date = start_date + timedelta(days=6)
        
        daily_loads = []
        over_days = 0
        cap = self.config.get("CAP", 8.0)
        
        current = start_date
        while current <= end_date:
            daily = self.calculate_daily_load(current)
            daily_loads.append(daily["adjusted_load"])
            if daily["adjusted_load"] > cap:
                over_days += 1
            current += timedelta(days=1)
        
        avg_load = sum(daily_loads) / len(daily_loads) if daily_loads else 0
        recovery_days = sum(1 for load in daily_loads if load < 4.0)
        recovery_rate = (recovery_days / 7.0) * 100 if daily_loads else 0
        
        return {
            "start_date": start_date,
            "end_date": end_date,
            "average_load": round(avg_load, 2),
            "over_days": over_days,
            "recovery_days": recovery_days,
            "recovery_rate": round(recovery_rate, 1),
            "daily_loads": daily_loads
        }
