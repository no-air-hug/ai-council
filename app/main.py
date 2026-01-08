"""
AI Council - Main Flask Application
Entry point for the web server and API routes.
"""

import os
import json
from pathlib import Path
from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS

from .config import get_config_manager, get_config, RAMMode


def create_app(config_path: str = None) -> Flask:
    """
    Create and configure the Flask application.
    
    Args:
        config_path: Optional path to configuration directory.
    
    Returns:
        Configured Flask application.
    """
    # Determine base path
    if config_path:
        base_path = Path(config_path)
    else:
        base_path = Path(__file__).parent.parent
    
    # Initialize config manager
    config_manager = get_config_manager(base_path)
    config = config_manager.load()
    
    # Create Flask app
    app = Flask(
        __name__,
        template_folder=str(base_path / "templates"),
        static_folder=str(base_path / "static")
    )
    
    # Enable CORS for development
    CORS(app)
    
    # Store config manager in app context
    app.config["AI_COUNCIL_CONFIG_MANAGER"] = config_manager
    app.config["AI_COUNCIL_BASE_PATH"] = base_path
    
    # Ensure data directories exist
    ensure_data_directories(base_path)
    
    # Register routes
    register_routes(app)
    
    return app


def ensure_data_directories(base_path: Path):
    """Ensure all required data directories exist."""
    directories = [
        base_path / "data" / "sessions",
        base_path / "data" / "personas" / "raw_imports",
        base_path / "data" / "exports"
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def register_routes(app: Flask):
    """Register all application routes."""
    
    # =========================================================================
    # Page Routes
    # =========================================================================
    
    @app.route("/")
    def index():
        """Render the main application page."""
        return render_template("index.html")
    
    # =========================================================================
    # Configuration API
    # =========================================================================
    
    @app.route("/api/config", methods=["GET"])
    def get_configuration():
        """Get current configuration summary."""
        config_manager = app.config["AI_COUNCIL_CONFIG_MANAGER"]
        return jsonify(config_manager.get_mode_summary())
    
    @app.route("/api/config/mode", methods=["POST"])
    def set_mode():
        """Switch RAM mode."""
        data = request.get_json()
        mode_str = data.get("mode", "").upper()
        
        if mode_str not in ["16GB", "32GB"]:
            return jsonify({"error": "Invalid mode. Use '16GB' or '32GB'"}), 400
        
        config_manager = app.config["AI_COUNCIL_CONFIG_MANAGER"]
        new_mode = RAMMode.MODE_16GB if mode_str == "16GB" else RAMMode.MODE_32GB
        config_manager.switch_mode(new_mode)
        
        # Also update environment variable for persistence
        os.environ["AI_COUNCIL_RAM_MODE"] = mode_str
        
        return jsonify(config_manager.get_mode_summary())
    
    # =========================================================================
    # Persona API
    # =========================================================================
    
    @app.route("/api/personas", methods=["GET"])
    def get_personas():
        """Get all available personas."""
        from .personas import PersonaManager
        base_path = app.config["AI_COUNCIL_BASE_PATH"]
        manager = PersonaManager(base_path)
        personas = manager.get_all_personas()
        return jsonify({"personas": personas})
    
    @app.route("/api/personas", methods=["POST"])
    def create_persona():
        """Create a new persona."""
        from .personas import PersonaManager
        base_path = app.config["AI_COUNCIL_BASE_PATH"]
        manager = PersonaManager(base_path)
        
        data = request.get_json()
        try:
            persona = manager.create_persona(
                name=data["name"],
                system_prompt=data["system_prompt"],
                reasoning_style=data.get("reasoning_style", "structured"),
                tone=data.get("tone", "formal")
            )
            return jsonify(persona), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.route("/api/personas/<persona_id>", methods=["PUT"])
    def update_persona(persona_id: str):
        """Update an existing persona."""
        from .personas import PersonaManager
        base_path = app.config["AI_COUNCIL_BASE_PATH"]
        manager = PersonaManager(base_path)
        
        data = request.get_json()
        try:
            persona = manager.update_persona(persona_id, data)
            if persona:
                return jsonify(persona)
            return jsonify({"error": "Persona not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.route("/api/personas/<persona_id>", methods=["DELETE"])
    def delete_persona(persona_id: str):
        """Delete a persona."""
        from .personas import PersonaManager
        base_path = app.config["AI_COUNCIL_BASE_PATH"]
        manager = PersonaManager(base_path)
        
        if manager.delete_persona(persona_id):
            return jsonify({"success": True})
        return jsonify({"error": "Persona not found"}), 404
    
    # =========================================================================
    # Session API
    # =========================================================================
    
    @app.route("/api/session/start", methods=["POST"])
    def start_session():
        """Start a new council session."""
        from .orchestrator import Orchestrator
        base_path = app.config["AI_COUNCIL_BASE_PATH"]
        config_manager = app.config["AI_COUNCIL_CONFIG_MANAGER"]
        
        data = request.get_json()
        prompt = data.get("prompt", "")
        persona_assignments = data.get("personas", {})
        debate_rounds = data.get("debate_rounds")  # Optional, defaults to config value
        argument_rounds = data.get("argument_rounds")  # Optional, defaults to config value
        collaboration_rounds = data.get("collaboration_rounds")  # Optional, defaults to config value
        axiom_rounds = data.get("axiom_rounds")  # Optional, defaults to config value
        worker_count = data.get("worker_count")  # Optional, UI override (2-4 workers)
        worker_max_tokens = data.get("worker_max_tokens")  # Optional, for session override
        synth_max_tokens = data.get("synth_max_tokens")  # Optional, for session override
        worker_context_window = data.get("worker_context_window")  # Optional, UI override (1K-32K)
        synth_context_window = data.get("synth_context_window")  # Optional, UI override (1K-32K)
        architect_max_tokens = data.get("architect_max_tokens")
        engineer_max_tokens = data.get("engineer_max_tokens")
        architect_context_window = data.get("architect_context_window")
        engineer_context_window = data.get("engineer_context_window")
        
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400
        
        # Create orchestrator with potentially overridden token settings (UI overrides config)
        orchestrator = Orchestrator(
            base_path, 
            config_manager.config,
            worker_max_tokens=worker_max_tokens,
            synth_max_tokens=synth_max_tokens,
            worker_context_window=worker_context_window,
            synth_context_window=synth_context_window,
            architect_max_tokens=architect_max_tokens,
            architect_context_window=architect_context_window,
            engineer_max_tokens=engineer_max_tokens,
            engineer_context_window=engineer_context_window
        )
        session_id = orchestrator.create_session(
            prompt, 
            persona_assignments,
            debate_rounds=debate_rounds,
            argument_rounds=argument_rounds,
            collaboration_rounds=collaboration_rounds,
            axiom_rounds=axiom_rounds,
            worker_count=worker_count
        )
        
        # Store orchestrator for this session
        if "sessions" not in app.config:
            app.config["sessions"] = {}
        app.config["sessions"][session_id] = orchestrator
        
        return jsonify({
            "session_id": session_id,
            "status": "created",
            "mode": config_manager.config.mode.value,
            "worker_count": len(orchestrator.workers),
            "debate_rounds": orchestrator.debate_rounds,
            "argument_rounds": orchestrator.argument_rounds,
            "collaboration_rounds": orchestrator.collaboration_rounds,
            "axiom_rounds": orchestrator.axiom_rounds
        })
    
    @app.route("/api/session/<session_id>/run", methods=["GET"])
    def run_session(session_id: str):
        """Run the full pipeline for a session (SSE stream)."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        def generate():
            """Generate SSE events for pipeline progress."""
            try:
                for event in orchestrator.run_pipeline():
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"
        
        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    @app.route("/api/session/<session_id>/status", methods=["GET"])
    def get_session_status(session_id: str):
        """Get current session status."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        return jsonify(orchestrator.get_status())
    
    @app.route("/api/session/<session_id>/full-state", methods=["GET"])
    def get_session_full_state(session_id: str):
        """Get complete session state for UI restoration after page reload."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        return jsonify(orchestrator.get_full_state())
    
    @app.route("/api/session/<session_id>/swap-persona", methods=["POST"])
    def swap_worker_persona(session_id: str):
        """Swap a worker's persona mid-session."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        data = request.get_json()
        worker_id = data.get("worker_id")
        new_persona_id = data.get("persona_id")
        action = data.get("action", "restart")  # keep_all, archive, restart
        
        if not worker_id or not new_persona_id:
            return jsonify({"error": "worker_id and persona_id required"}), 400
        
        try:
            result = orchestrator.swap_worker_persona(worker_id, new_persona_id, action)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.route("/api/session/<session_id>/diversify", methods=["GET"])
    def diversify_workers(session_id: str):
        """Diversify workers - let them see each other's proposals (SSE stream)."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        def generate():
            """Generate SSE events for diversify progress."""
            try:
                for event in orchestrator.diversify_workers():
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    @app.route("/api/session/<session_id>/round-feedback", methods=["POST"])
    def submit_round_feedback(session_id: str):
        """Submit feedback for a specific debate round."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        data = request.get_json()
        round_num = data.get("round", 1)
        worker_feedback = data.get("worker_feedback", {})  # {worker_id: feedback_text}
        skip_to_synthesis = data.get("skip_to_synthesis", False)
        
        try:
            result = orchestrator.submit_round_feedback(
                round_num=round_num,
                worker_feedback=worker_feedback,
                skip_to_synthesis=skip_to_synthesis
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.route("/api/session/<session_id>/argument-feedback", methods=["POST"])
    def submit_argument_feedback(session_id: str):
        """Submit feedback for a specific argumentation round."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        data = request.get_json()
        round_num = data.get("round", 1)
        worker_feedback = data.get("worker_feedback", {})  # {worker_id: feedback_text}
        skip_to_voting = data.get("skip_to_voting", False)
        
        try:
            result = orchestrator.submit_argument_feedback(
                round_num=round_num,
                worker_feedback=worker_feedback,
                skip_to_voting=skip_to_voting
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.route("/api/session/<session_id>/collab-feedback", methods=["POST"])
    def submit_collab_feedback(session_id: str):
        """Submit feedback for a specific collaboration round."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        data = request.get_json()
        round_num = data.get("round", 1)
        worker_feedback = data.get("worker_feedback", {})  # {worker_id: feedback_text}
        skip_to_synthesis = data.get("skip_to_synthesis", False)
        
        try:
            result = orchestrator.submit_collab_feedback(
                round_num=round_num,
                worker_feedback=worker_feedback,
                skip_to_synthesis=skip_to_synthesis
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.route("/api/session/<session_id>/continue", methods=["GET"])
    def continue_session(session_id: str):
        """Continue the pipeline after round feedback (SSE stream)."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        def generate():
            """Generate SSE events for pipeline continuation."""
            try:
                for event in orchestrator.continue_pipeline():
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            finally:
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"
        
        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    # =========================================================================
    # Voting API
    # =========================================================================
    
    @app.route("/api/session/<session_id>/vote", methods=["POST"])
    def submit_vote(session_id: str):
        """Submit user vote for candidates with comprehensive feedback."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        data = request.get_json()
        votes = data.get("votes", {})  # {candidate_id: rank}
        candidate_feedback = data.get("candidate_feedback", {})  # {candidate_id: feedback_text}
        overall_feedback = data.get("overall_feedback", "")  # General session feedback
        worker_feedback = data.get("worker_feedback", {})  # {worker_id: feedback_text}
        synthesizer_feedback = data.get("synthesizer_feedback", "")  # Feedback on synthesizer
        prompt_rating = data.get("prompt_rating", 0)  # Prompt quality rating (1-5, 0=skip)
        prompt_feedback = data.get("prompt_feedback", "")  # Feedback on prompt quality
        
        try:
            result = orchestrator.submit_user_votes(
                votes=votes,
                candidate_feedback=candidate_feedback,
                overall_feedback=overall_feedback,
                worker_feedback=worker_feedback,
                synthesizer_feedback=synthesizer_feedback,
                prompt_rating=prompt_rating,
                prompt_feedback=prompt_feedback
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.route("/api/session/<session_id>/finalize", methods=["GET"])
    def finalize_session(session_id: str):
        """Finalize session with axiom analysis and final output (SSE stream)."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        run_axioms = request.args.get("axioms", "true").lower() == "true"
        
        def generate():
            """Generate SSE events for finalize progress."""
            try:
                for event in orchestrator.finalize(run_axioms=run_axioms):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    @app.route("/api/session/<session_id>/final-feedback", methods=["POST"])
    def submit_final_feedback(session_id: str):
        """Submit feedback on the final output (for logging only)."""
        sessions = app.config.get("sessions", {})
        orchestrator = sessions.get(session_id)
        
        if not orchestrator:
            return jsonify({"error": "Session not found"}), 404
        
        data = request.get_json()
        feedback = data.get("feedback", "")
        
        try:
            result = orchestrator.submit_final_feedback(feedback)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    # =========================================================================
    # Memory API
    # =========================================================================
    
    @app.route("/api/system/memory", methods=["GET"])
    def get_memory_status():
        """Get current memory usage status."""
        from .utils import MemoryMonitor
        monitor = MemoryMonitor()
        return jsonify(monitor.get_status())
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Health check endpoint."""
        from .models import OllamaRuntime
        config_manager = app.config["AI_COUNCIL_CONFIG_MANAGER"]
        
        ollama_status = "unknown"
        try:
            runtime = OllamaRuntime(config_manager.config.ollama)
            if runtime.check_health():
                ollama_status = "healthy"
            else:
                ollama_status = "unhealthy"
        except Exception:
            ollama_status = "error"
        
        return jsonify({
            "status": "healthy",
            "mode": config_manager.config.mode.value,
            "ollama": ollama_status
        })
