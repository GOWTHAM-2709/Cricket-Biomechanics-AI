package com.bowling.demobowlinganalysisbackend.controller;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;

@RestController
@RequestMapping("/video")
public class VideoStreamController {

    private static final String DIR = System.getenv().getOrDefault("UPLOAD_DIR", "/tmp/uploads/") + "/";

    @GetMapping("/{filename}")
    public ResponseEntity<byte[]> streamVideo(@PathVariable String filename,
                                              @RequestHeader(value = "Range", required = false) String range)
            throws IOException {

        File file = new File(DIR + filename);
        if (!file.exists()) {
            return ResponseEntity.notFound().build();
        }

        long fileLength = file.length();
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.ACCEPT_RANGES, "bytes");

        String contentType = Files.probeContentType(file.toPath());
        if (contentType != null) {
            headers.setContentType(MediaType.parseMediaType(contentType));
        } else {
            headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
        }

        if (range == null || range.isBlank()) {
            byte[] data = readBytes(file, 0, fileLength - 1);
            headers.setContentLength(fileLength);
            return new ResponseEntity<>(data, headers, HttpStatus.OK);
        }

        // Range: bytes=start-end
        String[] parts = range.replace("bytes=", "").split("-");
        long start = Long.parseLong(parts[0]);
        long end = parts.length > 1 && !parts[1].isBlank() ? Long.parseLong(parts[1]) : (fileLength - 1);

        if (end >= fileLength) {
            end = fileLength - 1;
        }

        long contentLength = end - start + 1;
        byte[] data = readBytes(file, start, end);
        headers.setContentLength(contentLength);
        headers.set(HttpHeaders.CONTENT_RANGE, "bytes " + start + "-" + end + "/" + fileLength);

        return new ResponseEntity<>(data, headers, HttpStatus.PARTIAL_CONTENT);
    }

    private static byte[] readBytes(File file, long start, long end) throws IOException {
        int len = (int) (end - start + 1);
        byte[] buffer = new byte[len];
        try (RandomAccessFile raf = new RandomAccessFile(file, "r")) {
            raf.seek(start);
            raf.readFully(buffer);
        }
        return buffer;
    }
}
