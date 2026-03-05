"""
SSE (Server-Sent Events) helpers for streaming progress updates to the frontend.
"""
import json


def progress_event(step: str, detail: str, progress: int) -> str:
    """Format an SSE data line for a progress update."""
    return f"data: {json.dumps({'type': 'progress', 'step': step, 'detail': detail, 'progress': progress})}\n\n"


def result_event(data: dict) -> str:
    """Format an SSE data line for the final result."""
    return f"data: {json.dumps({'type': 'result', **data})}\n\n"


def error_event(message: str) -> str:
    """Format an SSE data line for an error."""
    return f"data: {json.dumps({'type': 'error', 'error': message})}\n\n"
