import os
import shutil
from typing import Tuple

class IntegratorAgent:
    """Combines backend and frontend files into a structured project folder."""

    def __init__(self, base_output_dir="output"):
        self.base_output_dir = base_output_dir
        os.makedirs(self.base_output_dir, exist_ok=True)

    def combine(self, backend_path: str, frontend_path: str, project_title: str) -> str:
        """
        Organize backend and frontend files into a single project folder.
        Returns the path to the final project folder.
        """
        # Make project folder dynamic based on title
        safe_title = "".join(c for c in project_title if c.isalnum() or c in (" ", "_")).rstrip()
        project_dir = os.path.join(self.base_output_dir, safe_title.replace(" ", "_"))
        
        # Create backend/frontend subfolders
        backend_dir = os.path.join(project_dir, "backend")
        frontend_dir = os.path.join(project_dir, "frontend")
        os.makedirs(backend_dir, exist_ok=True)
        os.makedirs(frontend_dir, exist_ok=True)

        # Move files if they exist
        if backend_path and os.path.exists(backend_path):
            shutil.move(backend_path, os.path.join(backend_dir, os.path.basename(backend_path)))
        if frontend_path and os.path.exists(frontend_path):
            shutil.move(frontend_path, os.path.join(frontend_dir, os.path.basename(frontend_path)))

        print(f"✅ Project organized at: {project_dir}")
        return project_dir
