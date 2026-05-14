# Cricket AI Biomechanics & Speed Analyzer 🏏🤖

A cloud-native, microservice-based architecture for real-time cricket bowling analysis. This platform processes video uploads to generate skeletal overlays, track biomechanical angles, and compute bowling speeds using deep learning.

## 🌟 Key Features
- **Biomechanics Hub**: MediaPipe-powered body tracking for shoulder rotation, knee flexion, elbow extension (chucking detection), and front-foot contact.
- **Speed Lab**: Object tracking-based velocity estimation calculated from release to pitch.
- **Cloud-Native Architecture**: Decoupled Java Spring Boot API and Python FastAPI inference engine, orchestrated via Docker Compose.
- **Transcoding Pipeline**: FFmpeg integrated for instant H.264 browser compatibility.

## 🏗️ Architecture Stack
- **Backend**: Java 21, Spring Boot, Maven
- **AI Microservice**: Python 3.11, FastAPI, Uvicorn
- **Machine Learning**: MediaPipe, OpenCV (headless), NumPy
- **Orchestration**: Docker, Docker Compose
- **Video Processing**: FFmpeg (H.264 ultrafast transcoding)
- **Frontend**: Vanilla HTML5, CSS3 (Glassmorphism UI), JavaScript

## 📂 Project Structure
```text
├── src/
│   ├── main/java/...        # Spring Boot application code
│   └── main/resources/
│       ├── analysis/        # Python AI scripts (analysis.py, speed_analysis.py)
│       └── static/          # Frontend UI (index.html, upload.html, css/js)
├── Dockerfile               # Multi-stage optimized Java container
├── Dockerfile.python        # Lightweight Python ML container
├── docker-compose.yml       # Production-ready container orchestration
├── pom.xml                  # Maven dependencies
└── requirements.txt         # Pinned Python dependencies
```

## 🚀 Deployment (AWS EC2 / Local)

The entire system is containerized. There are **zero** local dependencies required other than Docker.

### Prerequisites
- Docker Engine & Docker Compose

### 1. Build and Run
Clone the repository, navigate to the root folder, and run:
```bash
docker-compose up -d --build
```
*This command pulls the base images, installs dependencies, compiles the Java `.jar`, and starts both containers on isolated networks with resource constraints.*

### 2. Access the Application
- Web UI: `http://localhost:9090`
- AI Microservice API (Internal): `http://localhost:8000/health`

### 3. Graceful Shutdown
```bash
docker-compose down
```

## 🧠 AI Pipeline Flow
1. User uploads a video (`.mp4`) via the Web UI.
2. Spring Boot saves the file to a shared Docker volume (`/tmp/uploads`).
3. Spring Boot triggers the Python AI service via a synchronous HTTP REST call.
4. FastAPI spawns the MediaPipe inference script (`analysis.py`).
5. AI detects landmarks, computes angles, flags illegal actions (chucking), and renders visual overlays.
6. FFmpeg transcodes the output into browser-safe `H.264`.
7. Spring Boot intercepts the JSON response and serves the dashboard UI to the user.

## 🛠️ Performance Optimization Notes
- The Python container uses `mediapipe==0.10.9` and `opencv-python-headless` to eliminate 3GB of unnecessary CUDA/Torch bloat, resulting in a lean ~1.2GB image.
- Memory and CPU constraints are strictly defined in `docker-compose.yml` to prevent OOM errors on EC2 `t3.medium` instances.
- The JVM is configured with `-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0`.
