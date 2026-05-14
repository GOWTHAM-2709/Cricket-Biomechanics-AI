from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import json
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Cricket AI Analysis Service")

# Paths to scripts — relative to the container WORKDIR (/app)
BIOMECHANICS_SCRIPT = os.path.join(os.path.dirname(__file__), "src/main/resources/analysis/analysis.py")
SPEED_SCRIPT = os.path.join(os.path.dirname(__file__), "src/main/resources/analysis/speed_analysis.py")

# Timeout for analysis (30 minutes max)
ANALYSIS_TIMEOUT_SECS = 1800


class AnalysisRequest(BaseModel):
    video_path: str
    bowler_name: str = "Pro Athlete"


class SpeedRequest(BaseModel):
    video_path: str
    pitch_length: str = "20.12"


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker Compose and AWS load balancers."""
    return {"status": "ok", "service": "cricket-ai"}


@app.post("/api/v1/analyze/biomechanics")
async def analyze_biomechanics(req: AnalysisRequest):
    logger.info(f"Biomechanics request: video={req.video_path}, bowler={req.bowler_name}")

    if not os.path.exists(req.video_path):
        logger.error(f"Video file not found: {req.video_path}")
        raise HTTPException(status_code=400, detail=f"Video file not found at path: {req.video_path}")

    if not os.path.exists(BIOMECHANICS_SCRIPT):
        logger.error(f"Script not found: {BIOMECHANICS_SCRIPT}")
        raise HTTPException(status_code=500, detail=f"Analysis script missing: {BIOMECHANICS_SCRIPT}")

    try:
        logger.info(f"Starting biomechanics analysis...")
        result = subprocess.run(
            [sys.executable, BIOMECHANICS_SCRIPT, req.video_path, req.bowler_name],
            capture_output=True,
            text=True,
            timeout=ANALYSIS_TIMEOUT_SECS,
            env={**os.environ, "PYTHONWARNINGS": "ignore",
                 "TF_CPP_MIN_LOG_LEVEL": "3",
                 "GLOG_minloglevel": "3"}
        )
        logger.info(f"Script exit code: {result.returncode}")

        # Log any stderr warnings (MediaPipe/TF warnings are normal)
        if result.stderr:
            logger.warning(f"Script stderr: {result.stderr[-2000:]}")  # Last 2000 chars

        # Parse the last non-empty line from stdout as JSON
        output_lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        if not output_lines:
            logger.error(f"No output from script. stderr={result.stderr[-500:]}")
            raise HTTPException(status_code=500, detail="Analysis script produced no output")

        json_line = output_lines[-1]
        logger.info(f"Raw output (last line): {json_line[:200]}")

        parsed = json.loads(json_line)

        # If the script itself returned an error JSON, propagate it
        if "error" in parsed:
            raise HTTPException(status_code=500, detail=parsed["error"])

        logger.info("Biomechanics analysis completed successfully")
        return parsed

    except subprocess.TimeoutExpired:
        logger.error("Analysis timed out after 15 minutes")
        raise HTTPException(status_code=504, detail="Analysis timed out")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse script output as JSON: {e}")
        raise HTTPException(status_code=500, detail=f"Invalid JSON output from analysis script: {str(e)}")
    except HTTPException:
        raise  # Re-raise FastAPI HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.post("/api/v1/analyze/speed")
async def analyze_speed(req: SpeedRequest):
    logger.info(f"Speed request: video={req.video_path}, pitch={req.pitch_length}")

    if not os.path.exists(req.video_path):
        raise HTTPException(status_code=400, detail=f"Video file not found: {req.video_path}")

    if not os.path.exists(SPEED_SCRIPT):
        raise HTTPException(status_code=500, detail=f"Speed script missing: {SPEED_SCRIPT}")

    try:
        result = subprocess.run(
            [sys.executable, SPEED_SCRIPT, req.video_path, req.pitch_length],
            capture_output=True,
            text=True,
            timeout=ANALYSIS_TIMEOUT_SECS,
            env={**os.environ, "PYTHONWARNINGS": "ignore",
                 "TF_CPP_MIN_LOG_LEVEL": "3",
                 "GLOG_minloglevel": "3"}
        )
        output_lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        if not output_lines:
            raise HTTPException(status_code=500, detail="Speed script produced no output")

        parsed = json.loads(output_lines[-1])
        if "error" in parsed:
            raise HTTPException(status_code=500, detail=parsed["error"])

        return parsed

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Speed analysis timed out")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON from speed script: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Speed analysis failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
