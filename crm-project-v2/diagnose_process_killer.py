#!/usr/bin/env python3
"""
Diagnose what's killing our processes.
"""

import time
import os
import signal
import sys
import subprocess
from pathlib import Path

def signal_handler(signum, frame):
    print(f"\n⚠️  Received signal {signum} ({signal.Signals(signum).name})")
    print("Process is being terminated!")
    sys.exit(signum)

def main():
    print("🔍 Process Killer Diagnostic")
    print("=" * 40)
    print(f"PID: {os.getpid()}")
    print(f"Working directory: {os.getcwd()}")
    print(f"User: {os.getenv('USER', 'unknown')}")
    
    # Register signal handlers
    for sig in [signal.SIGTERM, signal.SIGKILL, signal.SIGINT, signal.SIGHUP]:
        try:
            signal.signal(sig, signal_handler)
        except (OSError, ValueError):
            pass  # Can't catch SIGKILL
    
    # Check system resources
    print("\n📊 System Resources:")
    try:
        result = subprocess.run(['free', '-h'], capture_output=True, text=True)
        print(result.stdout)
    except:
        pass
    
    # Check for process limits
    print("\n⚡ Process Limits:")
    try:
        import resource
        print(f"Max processes: {resource.getrlimit(resource.RLIMIT_NPROC)}")
        print(f"Max memory: {resource.getrlimit(resource.RLIMIT_AS)}")
    except:
        pass
    
    # Check for systemd or other process managers
    print("\n🔧 Process Environment:")
    env_vars = ['SYSTEMD_EXEC_PID', 'SUPERVISOR_ENABLED', 'TMUX', 'STY']
    for var in env_vars:
        if os.getenv(var):
            print(f"{var}: {os.getenv(var)}")
    
    # Check cgroup limits
    try:
        if Path('/proc/self/cgroup').exists():
            with open('/proc/self/cgroup') as f:
                print("\n📦 Control Groups:")
                print(f.read()[:500])
    except:
        pass
    
    print(f"\n⏰ Starting 60-second survival test...")
    print("This will help identify what's killing processes")
    
    for i in range(60):
        print(f"  Second {i+1}/60 - Still alive (PID {os.getpid()})")
        time.sleep(1)
        
        # Check if parent changed (process was adopted)
        if i % 10 == 0:
            print(f"    Parent PID: {os.getppid()}")
    
    print("✅ 60-second test completed successfully!")
    print("Process was not killed - the issue may be specific to Streamlit")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()