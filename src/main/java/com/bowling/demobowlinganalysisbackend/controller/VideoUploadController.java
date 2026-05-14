package com.bowling.demobowlinganalysisbackend.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/video")
public class VideoUploadController {

    private static final String DIR = System.getenv().getOrDefault("UPLOAD_DIR", "D:/bowling_uploads/") + "/";
    private static final String SESSIONS_FILE = DIR + "sessions.jsonl";
    private static final Logger log = LoggerFactory.getLogger(VideoUploadController.class);
    private final ObjectMapper mapper = new ObjectMapper();
    private final RestTemplate restTemplate = buildRestTemplate();

    private static RestTemplate buildRestTemplate() {
        // 35-minute timeout — must be longer than Python's 30-min timeout
        int timeoutMs = 35 * 60 * 1000;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10_000);   // 10 seconds to establish connection
        factory.setReadTimeout(timeoutMs);    // 35 minutes to wait for analysis response
        return new RestTemplate(factory);
    }

    // AI_SERVICE_URL is set via environment variable in Docker Compose.
    // Defaults to localhost:8000 for local development.
    private static final String AI_SERVICE_URL = System.getenv().getOrDefault("AI_SERVICE_URL", "http://localhost:8000");

    @PostMapping("/upload")
    public ResponseEntity<String> upload(@RequestParam("file") MultipartFile file,
                                         @RequestParam(value = "bowlerName", required = false) String bowlerName,
                                         @RequestParam(value = "bowlerType", required = false) String bowlerType,
                                         @RequestParam(value = "analysisMode", required = false, defaultValue = "single") String analysisMode,
                                         @RequestParam(value = "secondaryFile", required = false) MultipartFile secondaryFile,
                                         @RequestParam(value = "pipelineType", required = false, defaultValue = "biomechanics") String pipelineType,
                                         @RequestParam(value = "pitchLength", required = false, defaultValue = "20.12") String pitchLength) {
        try {
            if (file.isEmpty()) {
                return ResponseEntity.badRequest().body("{\"error\":\"Uploaded file is empty\"}");
            }
            new File(DIR).mkdirs();
            String originalName = file.getOriginalFilename() == null ? "upload.mp4" : file.getOriginalFilename();
            String safeName = originalName.replaceAll("[^a-zA-Z0-9._-]", "_");
            String jobId = UUID.randomUUID().toString().substring(0, 8);
            long startedAt = System.currentTimeMillis();
            File saved = new File(DIR + jobId + "_" + safeName);
            file.transferTo(saved);
            log.info("job={} upload saved path={} size={}B", jobId, saved.getAbsolutePath(), saved.length());

            // -------------------------------------------------------
            // PHASE 4: Call Python AI Microservice via HTTP
            // (replaces the old shell-command approach)
            // -------------------------------------------------------
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            Map<String, String> requestBody = new HashMap<>();
            requestBody.put("video_path", saved.getAbsolutePath());

            String baseUrl = AI_SERVICE_URL.replaceAll("/+$", "");
            String endpoint;
            if ("speed".equalsIgnoreCase(pipelineType)) {
                requestBody.put("pitch_length", pitchLength);
                endpoint = baseUrl + "/api/v1/analyze/speed";
            } else {
                requestBody.put("bowler_name", bowlerName != null ? bowlerName : "Pro Athlete");
                endpoint = baseUrl + "/api/v1/analyze/biomechanics";
            }

            log.info("job={} calling AI service endpoint={}", jobId, endpoint);
            HttpEntity<Map<String, String>> httpRequest = new HttpEntity<>(requestBody, headers);

            String aiResponseRaw;
            try {
                aiResponseRaw = restTemplate.postForObject(endpoint, httpRequest, String.class);
            } catch (org.springframework.web.client.HttpStatusCodeException httpEx) {
                String errorBody = httpEx.getResponseBodyAsString();
                log.error("job={} AI service call failed: code={} body={}", jobId, httpEx.getStatusCode(), errorBody);
                return ResponseEntity.internalServerError()
                        .body("{\"error\":\"AI service failed: " + errorBody.replace("\"", "'").replace("\n", " ") + "\"}");
            } catch (Exception ex) {
                log.error("job={} AI service connection failed: {}", jobId, ex.getMessage());
                return ResponseEntity.internalServerError()
                        .body("{\"error\":\"AI service unreachable: " + ex.getMessage().replace("\"", "'") + "\"}");
            }

            JsonNode analysis;
            try {
                analysis = mapper.readTree(aiResponseRaw);
            } catch (Exception parseEx) {
                log.error("job={} invalid AI response", jobId);
                return ResponseEntity.internalServerError()
                        .body("{\"error\":\"Invalid response from AI service\"}");
            }

            String originalFilename = saved.getName();
            String skeletonFilename = originalFilename.replace(".mp4", "_skeleton.mp4");
            String angleFilename = originalFilename.replace(".mp4", "_angles.mp4");
            String chuckingFilename = originalFilename.replace(".mp4", "_chucking_analysis.mp4");
            String speedFilename = originalFilename.replace(".mp4", "_speed_tracking.mp4");
            JsonNode videoNode = analysis.get("video");
            if (videoNode != null && !videoNode.isNull()) {
                String videoPath = videoNode.asText();
                int slash = Math.max(videoPath.lastIndexOf('/'), videoPath.lastIndexOf('\\'));
                if (slash >= 0 && slash + 1 < videoPath.length()) {
                    skeletonFilename = videoPath.substring(slash + 1);
                }
            }
            JsonNode angleNode = analysis.get("angleVideo");
            if (angleNode != null && !angleNode.isNull()) {
                String videoPath = angleNode.asText();
                int slash = Math.max(videoPath.lastIndexOf('/'), videoPath.lastIndexOf('\\'));
                if (slash >= 0 && slash + 1 < videoPath.length()) {
                    angleFilename = videoPath.substring(slash + 1);
                }
            }
            JsonNode chuckNode = analysis.get("chuckingVideo");
            if (chuckNode != null && !chuckNode.isNull()) {
                String videoPath = chuckNode.asText();
                int slash = Math.max(videoPath.lastIndexOf('/'), videoPath.lastIndexOf('\\'));
                if (slash >= 0 && slash + 1 < videoPath.length()) {
                    chuckingFilename = videoPath.substring(slash + 1);
                }
            }
            JsonNode speedNode = analysis.get("speedVideoUrl");
            if (speedNode != null && !speedNode.isNull()) {
                String videoPath = speedNode.asText();
                int slash = Math.max(videoPath.lastIndexOf('/'), videoPath.lastIndexOf('\\'));
                if (slash >= 0 && slash + 1 < videoPath.length()) {
                    speedFilename = videoPath.substring(slash + 1);
                }
            }

            ObjectNode response = mapper.createObjectNode();
            response.set("analysis", analysis);
            response.put("jobId", jobId);
            response.put("processingMs", System.currentTimeMillis() - startedAt);
            response.put("originalVideoUrl", "/video/" + originalFilename);
            response.put("skeletonVideoUrl", "/video/" + skeletonFilename);
            response.put("angleVideoUrl", "/video/" + angleFilename);
            response.put("chuckingVideoUrl", "/video/" + chuckingFilename);
            response.put("speedVideoUrl", "/video/" + speedFilename);
            response.put("pipelineType", pipelineType);
            response.put("analysisMode", analysisMode);
            response.put("secondaryProvided", secondaryFile != null && !secondaryFile.isEmpty());
            response.put("dualCameraReconstruction", false);
            response.put("dualCameraNote", "Dual-camera reconstruction is in beta planning; current run uses primary camera metrics.");

            ObjectNode sessionNode = mapper.createObjectNode();
            sessionNode.put("jobId", jobId);
            sessionNode.put("timestamp", Instant.now().toString());
            sessionNode.put("bowlerName", bowlerName == null ? "" : bowlerName.trim());
            sessionNode.put("bowlerType", bowlerType == null ? "" : bowlerType.trim());
            sessionNode.put("analysisMode", analysisMode);
            sessionNode.put("pipelineType", pipelineType);
            sessionNode.put("secondaryProvided", secondaryFile != null && !secondaryFile.isEmpty());
            sessionNode.put("originalVideoUrl", "/video/" + originalFilename);
            sessionNode.put("skeletonVideoUrl", "/video/" + skeletonFilename);
            sessionNode.put("processingMs", System.currentTimeMillis() - startedAt);
            sessionNode.set("analysis", analysis);
            appendSession(sessionNode);

            log.info("job={} completed output={}", jobId, skeletonFilename);

            return ResponseEntity.ok(mapper.writeValueAsString(response));

        } catch (Exception e) {
            log.error("upload request failed", e);
            return ResponseEntity.internalServerError()
                    .body("{\"error\":\""+e.getMessage()+"\"}");
        }
    }

    @GetMapping("/sessions")
    public ResponseEntity<String> sessions(@RequestParam(value = "limit", required = false, defaultValue = "20") int limit) {
        try {
            int safeLimit = Math.max(1, Math.min(limit, 200));
            ArrayNode arr = readRecentSessions(safeLimit);
            return ResponseEntity.ok(mapper.writeValueAsString(arr));
        } catch (Exception e) {
            log.error("sessions read failed", e);
            return ResponseEntity.internalServerError().body("{\"error\":\"Unable to load sessions\"}");
        }
    }

    @PostMapping("/sessions/clear")
    public ResponseEntity<String> clearSessions() {
        try {
            int cleared = clearSessionStore();
            ObjectNode out = mapper.createObjectNode();
            out.put("cleared", cleared);
            return ResponseEntity.ok(mapper.writeValueAsString(out));
        } catch (Exception e) {
            log.error("sessions clear failed", e);
            return ResponseEntity.internalServerError().body("{\"error\":\"Unable to clear sessions\"}");
        }
    }

    private synchronized void appendSession(ObjectNode sessionNode) throws Exception {
        File dir = new File(DIR);
        dir.mkdirs();
        Path p = Path.of(SESSIONS_FILE);
        String line = mapper.writeValueAsString(sessionNode) + System.lineSeparator();
        Files.writeString(p, line, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    private synchronized ArrayNode readRecentSessions(int limit) throws Exception {
        ArrayNode out = mapper.createArrayNode();
        Path p = Path.of(SESSIONS_FILE);
        if (!Files.exists(p)) {
            return out;
        }
        List<JsonNode> all = new ArrayList<>();
        List<String> lines = Files.readAllLines(p, StandardCharsets.UTF_8);
        for (String line : lines) {
            if (line == null || line.isBlank()) {
                continue;
            }
            try {
                all.add(mapper.readTree(line));
            } catch (Exception ignored) {
                // Skip malformed line and continue.
            }
        }
        all.sort(Comparator.comparing((JsonNode n) -> n.path("timestamp").asText("")).reversed());
        int count = Math.min(limit, all.size());
        for (int i = 0; i < count; i++) {
            out.add(all.get(i));
        }
        return out;
    }

    private synchronized int clearSessionStore() throws Exception {
        Path p = Path.of(SESSIONS_FILE);
        if (!Files.exists(p)) {
            return 0;
        }
        int count = 0;
        for (String line : Files.readAllLines(p, StandardCharsets.UTF_8)) {
            if (line != null && !line.isBlank()) {
                count++;
            }
        }
        Files.deleteIfExists(p);
        return count;
    }
}
