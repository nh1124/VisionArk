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
        viewMode,
        setPanelOpen,
        setCreateModalOpen,
        setImportModalOpen,
        setIsDayDetailsOpen,
        handleRefresh
    } = logic;

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
                onSave={handleRefresh}
                onDelete={handleRefresh}
                availableProjects={availableProjects}
            />

            <TaskCreateModal
                isOpen={createModalOpen}
                onClose={() => setCreateModalOpen(false)}
                onTaskCreated={handleRefresh}
                availableProjects={availableProjects}
            />

            <TaskImportModal
                isOpen={importModalOpen}
                onClose={() => setImportModalOpen(false)}
                onImportComplete={handleRefresh}
                existingProjects={availableProjects}
            />
        </div>
    );
}
