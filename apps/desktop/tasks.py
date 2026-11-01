#!/usr/bin/env python3
"""
TasksManager — Manages task creation, listing, completion, and deletion.
"""
import datetime


class TasksManager:
    def __init__(self):
        self.tasks = []
        
    def create_task(self, text):
        """Create a new task."""
        words = text.split()
        task_name = " ".join([w for w in words if w not in ["create", "task", "add", "new"]])
        
        if not task_name:
            return "Please specify what task you want to create."
            
        # Extract frequency
        frequency = "daily"
        if "weekly" in text:
            frequency = "weekly"
        elif "monthly" in text:
            frequency = "monthly"
            
        task = {
            "name": task_name,
            "frequency": frequency,
            "created": datetime.datetime.now().strftime("%Y-%m-%d"),
            "completed": False,
            "id": len(self.tasks) + 1
        }
        
        self.tasks.append(task)
        return "Task '{}' created with {} frequency (ID: {}).".format(task_name, frequency, task["id"])
        
    def list_tasks(self, text):
        """List tasks."""
        if not self.tasks:
            return "You have no tasks yet."
            
        result = "Your tasks:\n"
        for task in self.tasks:
            status = "[ ]" if not task["completed"] else "[✓]"
            result += "{} ID {}: {} ({}, created: {})\n".format(
                status, task["id"], task["name"], task["frequency"], task["created"]
            )
        return result
        
    def complete_task(self, text):
        """Complete a task."""
        try:
            task_id = int([w for w in text.split() if w.isdigit()][0])
        except (IndexError, ValueError):
            return "Please specify a task ID to complete."
            
        for task in self.tasks:
            if task["id"] == task_id:
                task["completed"] = True
                return "Task '{}' marked as completed.".format(task["name"])

        return "Task ID {} not found.".format(task_id)
        
    def delete_task(self, text):
        """Delete a task."""
        try:
            task_id = int([w for w in text.split() if w.isdigit()][0])
        except (IndexError, ValueError):
            return "Please specify a task ID to delete."
            
        for task in self.tasks:
            if task["id"] == task_id:
                self.tasks.remove(task)
                # Renumber remaining tasks
                for i, t in enumerate(self.tasks, 1):
                    t["id"] = i
                return "Task '{}' deleted.".format(task["name"])
                
        return "Task ID {} not found.".format(task_id)


class NotesManager:
    def __init__(self):
        self.notes = []
        
    def create_note(self, text):
        """Create a new note."""
        words = text.split()
        note_words = [w for w in words if w not in ["create", "note", "write", "memo", "remember", "new"]]
        
        if not note_words:
            return "Please specify what you want to write in your note."
            
        note_content = " ".join(note_words)
        for lead in ("a note:", "a note", "note:", "a "):
            if note_content.lower().startswith(lead):
                note_content = note_content[len(lead):].strip()
                break
        note = {
            "content": note_content,
            "created": datetime.datetime.now().strftime("%Y-%m-%d"),
            "id": len(self.notes) + 1
        }
        
        self.notes.append(note)
        return "Note created (ID: {}).".format(note["id"])
        
    def list_notes(self, text):
        """List notes."""
        if not self.notes:
            return "You have no notes yet."
            
        result = "Your notes:\n"
        for note in self.notes:
            content_preview = "Note" if len(note["content"]) < 50 else note["content"][:47] + "..."
            result += "{} ID {}: {} (created: {})\n".format(
                content_preview, note["id"], note["content"], note["created"]
            )
        return result
        
    def delete_note(self, text):
        """Delete a note."""
        try:
            note_id = int([w for w in text.split() if w.isdigit()][0])
        except (IndexError, ValueError):
            return "Please specify a note ID to delete."
            
        for note in self.notes:
            if note["id"] == note_id:
                self.notes.remove(note)
                # Renumber remaining notes
                for i, n in enumerate(self.notes, 1):
                    n["id"] = i
                return "Note ID {} deleted.".format(note_id)

        return "Note ID {} not found.".format(note_id)


class ProjectsManager:
    def __init__(self):
        self.projects_dir = "/run/media/hatem/2A3AE01E311C617F/Career/cloned_repos"
        
    def list_projects(self, text):
        """List all projects in cloned_repos."""
        import os
        if not os.path.exists(self.projects_dir):
            return "Projects directory not found."
            
        projects = []
        for item in os.listdir(self.projects_dir):
            item_path = os.path.join(self.projects_dir, item)
            if os.path.isdir(item_path):
                projects.append(item)
                
        if not projects:
            return "No projects found in cloned_repos."
            
        result = "Available projects:\n"
        for project in sorted(projects):
            result += "• {}\n".format(project)
        return result
        
    def explore_apps(self, text):
        """Explore released .exe apps from projects."""
        import os
        import glob
        
        result = "Released .exe apps from all projects:\n"
        
        if not os.path.exists(self.projects_dir):
            return "Projects directory not found."
            
        for project in os.listdir(self.projects_dir):
            project_path = os.path.join(self.projects_dir, project)
            if os.path.isdir(project_path):
                # Look for .exe files in dist/, build/, bin/, or root
                exe_files = glob.glob(os.path.join(project_path, "**", "*.exe"), recursive=True)
                if exe_files:
                    result += "\n{}:\n".format(project)
                    for exe_file in exe_files:
                        rel_path = os.path.relpath(exe_file, self.projects_dir)
                        result += "  • {}\n".format(rel_path)
                        
        if "explorer" not in text.lower() and "apps" not in text.lower() and ".exe" not in text.lower():
            result += "\nTo explore all released apps, say 'open explorer' or 'show apps'."
            
        return result


class CalendarManager:
    def __init__(self):
        self.tasks_by_date = {}
        
    def get_tasks_for_date(self, text):
        """Get tasks for a specific date."""
        today = datetime.datetime.now()
        
        if "today" in text:
            date_str = today.strftime("%Y-%m-%d")
        elif "tomorrow" in text:
            tomorrow = today + datetime.timedelta(days=1)
            date_str = tomorrow.strftime("%Y-%m-%d")
        elif "week" in text:
            result = "Tasks for this week (starting {}):\n".format(today.strftime("%Y-%m-%d"))
            for date in [today + datetime.timedelta(days=i) for i in range(7)]:
                date_str = date.strftime("%Y-%m-%d")
                if date_str in self.tasks_by_date and self.tasks_by_date[date_str].strip():
                    result += "{} ({}):\n{}\n".format(
                        date.strftime("%A"), date_str, self.tasks_by_date[date_str].rstrip())
            return result
        elif "month" in text:
            result = "Tasks for this month ({}):\n".format(today.strftime("%Y-%m-%d"))
            for date in [today + datetime.timedelta(days=i) for i in range(30)]:
                date_str = date.strftime("%Y-%m-%d")
                if date_str in self.tasks_by_date and self.tasks_by_date[date_str].strip():
                    result += "{}: {}\n".format(date_str, self.tasks_by_date[date_str].rstrip())
            return result
        elif text.strip() in self.tasks_by_date:      # exact ISO date given
            return "Tasks for {}:\n{}".format(text.strip(), self.tasks_by_date[text.strip()].rstrip())
        else:
            return "I can show you tasks for today, tomorrow, this week, or this month. What would you like?"
            
        # Default: just return today's tasks
        tasks = self.tasks_by_date.get(date_str, "No tasks scheduled.")
        return "Tasks for {}:\n{}".format(date_str, tasks)
        
    def schedule_task(self, task_name, date_str, time_str=None):
        """Schedule a task for a specific date/time."""
        if date_str not in self.tasks_by_date:
            self.tasks_by_date[date_str] = ""
            
        time_str = " {} - {}".format(time_str, task_name) if time_str else " - {}".format(task_name)
        self.tasks_by_date[date_str] += time_str + "\n"
        
        return "Task scheduled for {} at {}.".format(date_str, time_str)


class LauncherManager:
    def __init__(self):
        self.study_studio_path = "/run/media/hatem/2A3AE01E311C617F/Career/cloned_repos/Study-Studio"
        self.ld_command_center_path = "/run/media/hatem/2A3AE01E311C617F/Career/cloned_repos/L-D-Command-Center"
        
    def launch_study_studio(self, text):
        """Launch Study Studio application."""
        import subprocess
        import os
        
        if not os.path.exists(self.study_studio_path):
            return "Study Studio not found at {}.".format(self.study_studio_path)
            
        try:
            # Try to launch using python
            subprocess.Popen(["python", "-m", "streamlit", "run", "app.py"],
                           cwd=self.study_studio_path)
            return "Launching Study Studio..."
        except Exception as e:
            return "Failed to launch Study Studio: {}".format(str(e))
            
    def launch_ld_command_center(self, text):
        """Launch L-D Command Center application."""
        import subprocess
        import os
        
        if not os.path.exists(self.ld_command_center_path):
            return "L-D Command Center not found at {}.".format(self.ld_command_center_path)
            
        try:
            # Try to launch using streamlit
            subprocess.Popen(["python", "-m", "streamlit", "run", "main.py"],
                           cwd=self.ld_command_center_path)
            return "Launching L-D Command Center..."
        except Exception as e:
            return "Failed to launch L-D Command Center: {}".format(str(e))