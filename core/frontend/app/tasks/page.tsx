"use client";

import React from "react";
import { useTasksLogic } from "./hooks/useTasksLogic";
import MobileTasksView from "./views/MobileTasksView";
import DesktopTasksView from "./views/DesktopTasksView";
import TaskEditPanel from "../components/TaskEditPanel";
import TaskCreateModal from "../components/TaskCreateModal";
import TaskImportModal from "../components/TaskImportModal";

export default function UnifiedTasksPage() {
    const logic = useTasksLogic();
    const {
        isMobile,
        selectedTask,
        panelOpen,
        createModalOpen,
        importModalOpen,
        availableProjects,
        targetDate,
        viewMode,
        setSelectedTask,
        setPanelOpen,
        setCreateModalOpen,
        setImportModalOpen,
        setIsDayDetailsOpen,
        fetchTasks,
        fetchAllTasks,
        fetchMonthTasks
    } = logic;

    // Shared refresh logic for modals
    const handleRefreshData = () => {
        fetchTasks(targetDate);
        fetchAllTasks();
        // Refetch month tasks to update "Planned" view
        const start = new Date();
        const end = new Date();
        end.setDate(start.getDate() + 30);
        fetchMonthTasks(start.toISOString().split('T')[0], end.toISOString().split('T')[0]);
    };

    return (
        <div className="flex-1 flex flex-col min-h-0 bg-gray-950">
            {/* Conditional View Rendering */}
            {isMobile ? (
                <MobileTasksView logic={logic} />
            ) : (
                <DesktopTasksView logic={logic} />
            )}

            {/* Shared Modals & Panels */}
            <TaskEditPanel
                task={selectedTask}
                isOpen={panelOpen}
                onClose={() => {
                    setPanelOpen(false);
                    if (viewMode === 'calendar') {
                        setIsDayDetailsOpen(true);
                    }
                }}
                onSave={handleRefreshData}
                onDelete={handleRefreshData}
                availableProjects={availableProjects}
            />

            <TaskCreateModal
                isOpen={createModalOpen}
                onClose={() => setCreateModalOpen(false)}
                onTaskCreated={handleRefreshData}
                availableProjects={availableProjects}
            />

            <TaskImportModal
                isOpen={importModalOpen}
                onClose={() => setImportModalOpen(false)}
                onImportComplete={handleRefreshData}
                existingProjects={availableProjects}
            />
        </div>
    );
}
