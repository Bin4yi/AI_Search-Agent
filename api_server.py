from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
from datetime import datetime
import logging
import threading
import time
import concurrent.futures
from typing import Optional, Dict, Any

# Import your existing main.py functions
from main import graph, State

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Multi-Source Research Agent API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store for tracking search sessions
search_sessions: Dict[str, Dict[str, Any]] = {}

class SearchRequest(BaseModel):
    question: str

class SearchResponse(BaseModel):
    session_id: str
    status: str
    message: str

class StatusResponse(BaseModel):
    session_id: str
    status: str
    progress: int
    current_step: str
    message: str
    result: Optional[str] = None

class OutputResponse(BaseModel):
    session_id: str
    output_log: str

def log_to_session(session_id: str, message: str):
    """Add a timestamped message to the session output log"""
    if session_id in search_sessions:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        search_sessions[session_id]["output_log"] = search_sessions[session_id].get("output_log", "") + log_entry
        print(f"[{session_id}] {message}")

def update_session_progress(session_id: str, progress: int, step: str, message: str):
    """Update session progress and log"""
    if session_id in search_sessions:
        search_sessions[session_id].update({
            "progress": progress,
            "current_step": step,
            "message": message,
            "updated_at": datetime.now().isoformat()
        })
        log_to_session(session_id, f"{step}: {message}")

def run_research_with_tracking(question: str, session_id: str):
    """Run the research process with progress tracking and timeouts"""
    try:
        search_sessions[session_id]["status"] = "running"
        update_session_progress(session_id, 5, "initializing", "Starting research process...")
        log_to_session(session_id, f"🚀 Starting multi-source research for: '{question}'")
        
        # Create the state exactly as in your main.py
        state = {
            "messages": [{"role": "user", "content": question}],
            "user_question": question,
            "google_results": None,
            "bing_results": None,
            "reddit_results": None,
            "selected_reddit_urls": None,
            "reddit_post_data": None,
            "google_analysis": None,
            "bing_analysis": None,
            "reddit_analysis": None,
            "final_answer": None,
        }

        # Run with timeout using ThreadPoolExecutor
        def run_graph():
            log_to_session(session_id, "🔄 Starting parallel research process...")
            update_session_progress(session_id, 10, "research_started", "Running parallel searches...")
            return graph.invoke(state)
        
        # Use ThreadPoolExecutor for timeout
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_graph)
            
            try:
                # Wait for result with timeout - Changed to 7 minutes (420 seconds)
                final_state = future.result(timeout=420)  # 7 minute timeout
                
                if final_state and final_state.get("final_answer"):
                    search_sessions[session_id].update({
                        "status": "completed",
                        "progress": 100,
                        "current_step": "completed",
                        "message": "Research completed successfully!",
                        "result": final_state.get("final_answer"),
                        "completed_at": datetime.now().isoformat()
                    })
                    log_to_session(session_id, "🎉 Research completed successfully!")
                else:
                    search_sessions[session_id].update({
                        "status": "partial_success",
                        "progress": 90,
                        "current_step": "completed_with_issues",
                        "message": "Research completed but with some issues",
                        "result": "Research completed with partial results. Some data sources may have failed.",
                        "completed_at": datetime.now().isoformat()
                    })
                    log_to_session(session_id, "⚠️ Research completed with some issues")
                    
            except concurrent.futures.TimeoutError:
                search_sessions[session_id].update({
                    "status": "timeout",
                    "progress": 75,
                    "current_step": "timeout",
                    "message": "Research timed out after 7 minutes",
                    "result": "Research process timed out. Try a simpler query or check your internet connection.",
                    "completed_at": datetime.now().isoformat()
                })
                log_to_session(session_id, "⏰ Research timed out after 7 minutes")

    except Exception as e:
        logger.error(f"Error in research process: {str(e)}")
        log_to_session(session_id, f"❌ Research failed: {str(e)}")
        search_sessions[session_id].update({
            "status": "error",
            "progress": 0,
            "current_step": "error",
            "message": f"Error occurred: {str(e)}",
            "result": f"Research failed due to an error: {str(e)}",
            "completed_at": datetime.now().isoformat()
        })

@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML file"""
    return FileResponse("frontend_fastapi.html")

@app.post("/search", response_model=SearchResponse)
async def start_search(request: SearchRequest):
    """Start a new research session"""
    session_id = str(uuid.uuid4())
    
    # Initialize session
    search_sessions[session_id] = {
        "session_id": session_id,
        "question": request.question,
        "status": "started",
        "progress": 0,
        "current_step": "initializing",
        "message": "Research session started",
        "result": None,
        "output_log": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    # Start the research process in a background thread
    thread = threading.Thread(
        target=run_research_with_tracking, 
        args=(request.question, session_id)
    )
    thread.daemon = True
    thread.start()
    
    return SearchResponse(
        session_id=session_id,
        status="started",
        message="Research session started successfully"
    )

@app.get("/status/{session_id}", response_model=StatusResponse)
async def get_search_status(session_id: str):
    """Get the status of a research session"""
    if session_id not in search_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = search_sessions[session_id]
    
    return StatusResponse(
        session_id=session_id,
        status=session["status"],
        progress=session["progress"],
        current_step=session["current_step"],
        message=session["message"],
        result=session.get("result")
    )

@app.get("/output/{session_id}", response_model=OutputResponse)
async def get_output_log(session_id: str):
    """Get the output log for a research session"""
    if session_id not in search_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = search_sessions[session_id]
    
    return OutputResponse(
        session_id=session_id,
        output_log=session.get("output_log", "")
    )

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a research session"""
    if session_id not in search_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del search_sessions[session_id]
    return {"message": "Session deleted successfully"}

@app.get("/sessions")
async def list_sessions():
    """List all active sessions"""
    return {"sessions": list(search_sessions.values())}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(search_sessions)
    }

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting Multi-Source Research Agent API...")
    print("📊 Your original main.py logic is preserved")
    print("🌐 Frontend will be available at: http://localhost:8000")
    print("📚 API docs at: http://localhost:8000/docs")
    print("⏰ Research timeout: 7 minutes")
    
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)