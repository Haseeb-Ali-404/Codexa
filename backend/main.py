from agents.planner import PlannerAgent
from agents.developer import DeveloperAgent
from agents.debugger import DebuggerAgent
from dotenv import load_dotenv
import os

load_dotenv()  # Load GEMINI_API_KEY

def main():
    print("🚀 Welcome to Codexa - Full-Stack AI Project Builder")
    print("Type 'exit' to quit.\n")

    while True:
        project_name = input("▶ Enter your project idea / project name: ").strip()
        if project_name.lower() in ["exit", "quit"]:
            print("👋 Exiting Codexa.")
            break
        if not project_name:
            print("⚠️ Please enter a valid project name.")
            continue

        # --- Step 1: Planning ---
        planner = PlannerAgent()
        plan = planner.create_plan(project_name)
        if not plan:
            print("❌ Failed to generate plan.\n")
            continue

        print("\n📌 Generated Plan:")
        for i, step in enumerate(plan, 1):
            print(f"{i}. {step}")

        # --- Step 2: Development ---
        developer = DeveloperAgent()
        project_dir = developer.generate_project(project_name, plan)
        if not project_dir:
            print("❌ Code generation failed.\n")
            continue

        # --- Step 3: Debugging ---
        debugger = DebuggerAgent(verbose=True)
        success = debugger.debug(project_dir)
        if not success:
            print("❌ Debugging failed. Check backend/frontend code.\n")
            continue

        print(f"\n✅ Project generated and validated successfully in 'project_dir'!\n")
        print("--- Ready for next project ---\n")


if __name__ == "__main__":
    main()
