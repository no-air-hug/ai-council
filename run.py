#!/usr/bin/env python3
"""
AI Council - Entry Point
Run the Flask application
"""

import os
import sys

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import create_app

if __name__ == "__main__":
    app = create_app()
    
    # Get host and port from environment or use defaults
    host = os.environ.get("AI_COUNCIL_HOST", "127.0.0.1")
    port = int(os.environ.get("AI_COUNCIL_PORT", "5000"))
    debug = os.environ.get("AI_COUNCIL_DEBUG", "true").lower() == "true"
    
    print(f"\n{'='*50}")
    print("  AI Council - Local Multi-Agent LLM System")
    print(f"{'='*50}")
    print(f"  Server: http://{host}:{port}")
    print(f"  Debug Mode: {debug}")
    print(f"{'='*50}\n")
    
    app.run(host=host, port=port, debug=debug, threaded=True)


