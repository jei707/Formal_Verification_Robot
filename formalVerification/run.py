"""
Helper script to run both backend and frontend simultaneously.
"""
import subprocess
import sys
import time
import os

def run_apps():
    """Start both Flask backend and Tkinter frontend."""
    print("Starting Formal Verification Engine...")
    print("\nStarting Flask backend server...")
    
    # Start Flask backend in a separate process
    backend = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    
    # Wait a moment for Flask to start
    print("Waiting for backend to initialize...")
    time.sleep(3)
    
    print("Starting Tkinter frontend...")
    # Start Tkinter frontend (this will block until GUI is closed)
    frontend = subprocess.Popen(
        [sys.executable, "ui.py"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    
    print("\nBoth applications are running!")
    print("Close the GUI window to stop the frontend.")
    print("Press Ctrl+C to stop the backend server.")
    
    try:
        # Wait for frontend to close
        frontend.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Terminate backend when frontend closes
        backend.terminate()
        backend.wait()
        print("Backend server stopped.")

if __name__ == "__main__":
    run_apps()

