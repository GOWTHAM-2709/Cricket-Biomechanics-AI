import cv2
import mediapipe as mp
import math
import json
import sys
import time
import os
import shutil
import subprocess
import statistics
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

input_path = sys.argv[1]
bowler_name = sys.argv[2] if len(sys.argv) > 2 else "Professional Athlete"

base, ext = os.path.splitext(input_path)

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=0,
    smooth_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)
draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(input_path)
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)
if not fps or fps <= 0:
    fps = 30.0
if w == 0 or h == 0:
    ok, first = cap.read()
    if not ok:
        print(json.dumps({"error": "Unable to read video frames"}))
        sys.exit(1)
    h, w = first.shape[:2]
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

out_w = w if w % 2 == 0 else w + 1
out_h = h if h % 2 == 0 else h + 1

output_path = None
out = None
chosen_codec = None
angle_output_path = None
angle_out = None
output_path = base + "_skeleton.mp4"
chosen_codec = "mp4v"
out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))
if not out.isOpened():
    print(json.dumps({"error": "VideoWriter failed to open"}))
    sys.exit(1)

angle_output_path = base + "_angles.mp4"
angle_out = cv2.VideoWriter(angle_output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))
if not angle_out.isOpened():
    print(json.dumps({"error": "Angle VideoWriter failed to open"}))
    sys.exit(1)

chucking_output_path = base + "_chucking_analysis.mp4"
chucking_out = cv2.VideoWriter(chucking_output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))
if not chucking_out.isOpened():
    print(json.dumps({"error": "Chucking VideoWriter failed to open"}))
    sys.exit(1)

prev_x = None
prev_t = None
shoulder_angle = 0

lean_angle = 0
weight_transfer = "Unknown"
head_position = "Unknown"
shoulder_status = "Unknown"
knee_flexion = 0
last_head_deviation = 0
elbow_extension_deg = 0.0
chucking_suspected = False
chucking_data_ready = False
hip_flexion_deg = 0.0
trunk_flexion_deg = 0.0
elbow_joint_deg = 0.0
front_knee_deg = 0.0
back_knee_deg = 0.0
left_elbow_deg = 0.0
right_elbow_deg = 0.0
front_foot_deg = 0.0
back_foot_deg = 0.0
current_elbow_angle = 0.0
delivery_min_elbow = None
delivery_max_elbow = None
max_elbow_extension = 0.0
icc_verdict = "INCONCLUSIVE"
freeze_frames_remaining = 0
freeze_frame = None
legal_flash_frames = 0
arm_frames_for_chucking = 0
arm_visible_frames = 0

lean_angle_list = []
shoulder_angle_list = []
head_x_list = []
knee_angle_list = []
ankle_y_list = []
wrist_x_list = []
wrist_y_list = []

frame_idx = 0
frame_skip = int(os.environ.get("FRAME_SKIP", "6"))  # Docker: 6, local: set FRAME_SKIP=3
process_width = 480
process_height = 270
last_landmarks = None
head_center_x = None
foot_contact_frame = None
back_foot_contact_frame = None
release_frame = None
current_phase = "Run-up"
phase_transitions = [("Run-up", 0)]

ankle_prev_y = None
r_ankle_prev_y = None
wrist_prev = None
wrist_speed_prev = None
wrist_speed_prevprev = None
wrist_prev_frame_idx = None
wrist_trail = []
ankle_trail = []
TRAIL_LENGTH = 18
VISIBILITY_THRESHOLD = 0.55
pose_frames_processed = 0
confident_frames = 0
low_confidence_frames = 0
visibility_samples = []
analysis_started_at = time.time()
prev_pose_frame_idx = None
side_on_good_frames = 0
full_body_visible_frames = 0
right_elbow_angle_series = []
right_upperarm_horizontal_flags = []
FONT_CACHE = {}
TNR_FONT_PATHS = [
    "C:/Windows/Fonts/timesbd.ttf",
    "C:/Windows/Fonts/times.ttf"
]
HIGH_FPS_THRESHOLD = 60.0
CHUCKING_CONF_THRESHOLD = 0.70
ICC_ELBOW_LIMIT_DEG = 15.0
CHUCKING_ARM_VISIBILITY_THRESHOLD = 0.65
fps_gate_passed = fps >= HIGH_FPS_THRESHOLD
CHUCKING_LANDMARK_VIS_THRESHOLD = 0.60
CHUCKING_OUTLIER_DELTA_DEG = 20.0
CHUCKING_SMOOTH_WINDOW = 5
CHUCKING_PHASE_WINDOW_FRAMES = 5
CHUCKING_MIN_CONFIDENCE = 0.60


def angle(a, b, c):
    ab = (a[0] - b[0], a[1] - b[1])
    cb = (c[0] - b[0], c[1] - b[1])
    dot = ab[0] * cb[0] + ab[1] * cb[1]
    mag = math.hypot(*ab) * math.hypot(*cb)
    return 0 if mag == 0 else abs(math.degrees(math.acos(dot / mag)))


def draw_angle_lines(frame, a, b, c, color, thickness=2):
    cv2.line(frame, b, a, color, thickness, cv2.LINE_AA)
    cv2.line(frame, b, c, color, thickness, cv2.LINE_AA)


def draw_arc(frame, center, radius, start_angle, end_angle, color, thickness=2):
    cv2.ellipse(frame, center, (radius, radius), 0, start_angle, end_angle, color, thickness, cv2.LINE_AA)


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def risk_color_for(lean_val, shoulder_val):
    score = 0
    if lean_val > 25:
        score += 1
    if shoulder_val > 30:
        score += 1
    if score >= 2:
        return "High Risk", (0, 0, 255)
    if score == 1:
        return "Moderate Risk", (0, 200, 255)
    return "Low Risk", (0, 200, 0)


PALETTE = {
    "panel_dark": (28, 24, 34),
    "text_light": (248, 250, 252),
    "text_dark": (8, 12, 20),
    "lean": (82, 220, 255),
    "shoulder": (72, 170, 255),
    "knee": (110, 235, 140),
    "head": (220, 140, 255),
    "marker": (84, 255, 255)
}

LANDMARK_DRAW_SPEC = draw.DrawingSpec(color=(255, 245, 235), thickness=2, circle_radius=2)
CONNECTION_DRAW_SPEC = draw.DrawingSpec(color=(95, 175, 255), thickness=3, circle_radius=1)


def draw_translucent_rect(frame, top_left, bottom_right, color, alpha=0.55):
    x1, y1 = top_left
    x2, y2 = bottom_right
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def draw_label(frame, text, origin, text_color, bg_color=PALETTE["panel_dark"], scale=0.62, thickness=2, padding=6):
    x, y = origin
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, scale, thickness)
    draw_translucent_rect(frame, (x - padding, y - th - padding), (x + tw + padding, y + padding), bg_color, 0.7)
    draw_text(frame, text, (x, y), text_color, scale, thickness)


def draw_marker(frame, point, fill_color, radius=7):
    cv2.circle(frame, point, radius + 2, (0, 0, 0), -1, cv2.LINE_AA)
    cv2.circle(frame, point, radius, fill_color, -1, cv2.LINE_AA)


def draw_styled_pose(frame, landmarks):
    draw.draw_landmarks(
        frame,
        landmarks,
        mp_pose.POSE_CONNECTIONS,
        landmark_drawing_spec=LANDMARK_DRAW_SPEC,
        connection_drawing_spec=CONNECTION_DRAW_SPEC
    )


def append_trail_point(trail, point, max_len=TRAIL_LENGTH):
    trail.append(point)
    if len(trail) > max_len:
        del trail[0:len(trail) - max_len]


def draw_motion_trail(frame, trail_points, color, min_intensity=0.35):
    if len(trail_points) < 2:
        return
    seg_count = len(trail_points) - 1
    for i in range(1, len(trail_points)):
        p1 = trail_points[i - 1]
        p2 = trail_points[i]
        progress = i / seg_count
        scale = min_intensity + (1 - min_intensity) * progress
        seg_color = (
            int(color[0] * scale),
            int(color[1] * scale),
            int(color[2] * scale)
        )
        thickness = max(1, int(1 + 4 * progress))
        cv2.line(frame, p1, p2, seg_color, thickness, cv2.LINE_AA)


def apply_color_grade(frame):
    # Teal-cyan cinematic grade with mild contrast boost.
    tint = frame.copy()
    tint[:] = (36, 74, 92)
    cv2.addWeighted(tint, 0.10, frame, 0.90, 0, frame)
    cv2.convertScaleAbs(frame, frame, alpha=1.08, beta=4)


def _get_tnr_font(size_px):
    if not PIL_AVAILABLE:
        return None
    key = max(10, int(size_px))
    if key in FONT_CACHE:
        return FONT_CACHE[key]
    font = None
    for path in TNR_FONT_PATHS:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, key)
                break
            except Exception:
                continue
    FONT_CACHE[key] = font
    return font


def draw_text(frame, text, origin, color, scale=0.62, thickness=2):
    font = _get_tnr_font(scale * 42)
    if font is None:
        cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_DUPLEX, scale, color, thickness, cv2.LINE_AA)
        return
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    draw_obj = ImageDraw.Draw(pil_img)
    x, y = origin
    draw_obj.text((x, y - int(scale * 26)), text, fill=(color[2], color[1], color[0]), font=font)
    frame[:, :, :] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)



def draw_glass_panel(frame, x, y, w, h, title=None):
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (18, 22, 28), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    cv2.rectangle(frame, (x, y), (x + w, y + h), (60, 75, 90), 1)
    if title:
        draw_text(frame, title, (x + 15, y + 25), (200, 215, 230), 0.45, 1)

def draw_metric(frame, x, y, label, value, val_color=(255,255,255)):
    draw_text(frame, label, (x, y), (140, 150, 160), 0.40, 1)
    draw_text(frame, value, (x, y + 25), val_color, 0.65, 2)
    
def draw_glowing_circle(frame, center, radius, color):
    overlay = frame.copy()
    cv2.circle(overlay, center, radius + 8, color, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
    cv2.circle(frame, center, radius, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(frame, center, radius + 2, color, 2, cv2.LINE_AA)


def draw_telemetry_hud(frame, phase_name, conf_ratio, frame_no, frame_total, has_bfc, has_ffc, has_rel):
    box_w = 320
    box_h = 132
    x1 = max(12, w - box_w - 20)
    y1 = 52
    x2 = x1 + box_w
    y2 = y1 + box_h
    draw_translucent_rect(frame, (x1, y1), (x2, y2), (20, 28, 38), 0.58)

    draw_text(frame, "Live Telemetry", (x1 + 12, y1 + 26), (230, 245, 255), 0.56, 1)
    draw_text(frame, f"Phase: {phase_name}", (x1 + 12, y1 + 50), (184, 255, 255), 0.54, 1)

    secs = frame_no / fps if fps > 0 else 0.0
    mm = int(secs // 60)
    ss = int(secs % 60)
    draw_text(frame, f"Time: {mm:02d}:{ss:02d}", (x1 + 12, y1 + 73), (232, 240, 250), 0.50, 1)

    bar_x1 = x1 + 12
    bar_x2 = x2 - 12
    bar_y1 = y1 + 82
    bar_y2 = y1 + 96
    cv2.rectangle(frame, (bar_x1, bar_y1), (bar_x2, bar_y2), (72, 82, 94), -1, cv2.LINE_AA)
    filled_x = int(bar_x1 + (bar_x2 - bar_x1) * clamp(conf_ratio, 0.0, 1.0))
    cv2.rectangle(frame, (bar_x1, bar_y1), (filled_x, bar_y2), (64, 210, 255), -1, cv2.LINE_AA)
    draw_text(frame, f"Confidence: {int(conf_ratio * 100)}%", (x1 + 12, y1 + 116), (215, 248, 255), 0.48, 1)

    prog_total = frame_total if frame_total and frame_total > 0 else max(frame_no + 1, 1)
    prog = clamp(frame_no / prog_total, 0.0, 1.0)
    p_x1 = x1 + 150
    p_x2 = x2 - 12
    p_y1 = y1 + 106
    p_y2 = y1 + 118
    cv2.rectangle(frame, (p_x1, p_y1), (p_x2, p_y2), (75, 85, 96), -1, cv2.LINE_AA)
    p_fill = int(p_x1 + (p_x2 - p_x1) * prog)
    cv2.rectangle(frame, (p_x1, p_y1), (p_fill, p_y2), (95, 180, 255), -1, cv2.LINE_AA)

    flags = f"BFC:{'Y' if has_bfc else 'N'}  FFC:{'Y' if has_ffc else 'N'}  REL:{'Y' if has_rel else 'N'}"
    draw_text(frame, flags, (x1 + 150, y1 + 130), (215, 236, 255), 0.40, 1)


def draw_phase_timeline(frame, frame_no, frame_total, bfc_frame, ffc_frame, rel_frame):
    x1 = 24
    x2 = w - 24
    y1 = h - 46
    y2 = h - 24
    if x2 <= x1 + 20:
        return

    total = frame_total if frame_total and frame_total > 0 else max(frame_no + 1, 1)
    def to_x(f):
        return int(x1 + (x2 - x1) * clamp(f / total, 0.0, 1.0))

    # Base background bar
    cv2.rectangle(frame, (x1, y1), (x2, y2), (45, 55, 68), -1, cv2.LINE_AA)

    bfc_x = to_x(bfc_frame if bfc_frame is not None else 0)
    ffc_x = to_x(ffc_frame if ffc_frame is not None else total)
    rel_x = to_x(rel_frame if rel_frame is not None else total)

    # Ensure ordering
    bfc_x = max(x1, min(x2, bfc_x))
    ffc_x = max(bfc_x, min(x2, ffc_x))
    rel_x = max(ffc_x, min(x2, rel_x))

    # Phase segments
    cv2.rectangle(frame, (x1, y1), (bfc_x, y2), (65, 120, 235), -1, cv2.LINE_AA)     # Run-up
    cv2.rectangle(frame, (bfc_x, y1), (ffc_x, y2), (100, 95, 240), -1, cv2.LINE_AA)   # Back-foot Contact
    cv2.rectangle(frame, (ffc_x, y1), (rel_x, y2), (85, 185, 255), -1, cv2.LINE_AA)   # Front-foot Contact
    cv2.rectangle(frame, (rel_x, y1), (x2, y2), (110, 220, 150), -1, cv2.LINE_AA)     # Follow-through

    # Event lines
    if bfc_frame is not None:
        cv2.line(frame, (bfc_x, y1 - 4), (bfc_x, y2 + 4), (225, 232, 255), 2, cv2.LINE_AA)
    if ffc_frame is not None:
        cv2.line(frame, (ffc_x, y1 - 4), (ffc_x, y2 + 4), (215, 255, 255), 2, cv2.LINE_AA)
    if rel_frame is not None:
        cv2.line(frame, (rel_x, y1 - 4), (rel_x, y2 + 4), (255, 225, 180), 2, cv2.LINE_AA)

    # Current frame pointer
    cur_x = to_x(frame_no)
    cv2.line(frame, (cur_x, y1 - 8), (cur_x, y2 + 8), (255, 255, 255), 2, cv2.LINE_AA)
    cv2.circle(frame, (cur_x, y1 - 10), 4, (255, 255, 255), -1, cv2.LINE_AA)

    draw_text(frame, "Run-up", (x1 + 4, y1 - 8), (214, 232, 255), 0.36, 1)
    draw_text(frame, "BFC", (bfc_x + 4, y1 - 8), (214, 232, 255), 0.34, 1)
    draw_text(frame, "FFC", (ffc_x + 4, y1 - 8), (214, 232, 255), 0.34, 1)
    draw_text(frame, "REL", (rel_x + 4, y1 - 8), (214, 232, 255), 0.34, 1)


def draw_body_flexion_overlay(
    frame, has_pose, phase_text, mid_sh, l_sh, r_sh, l_hip, r_hip, l_knee, r_knee, l_ankle, r_ankle,
    l_foot, r_foot, l_elbow, r_elbow, l_wrist, r_wrist,
    trunk_flex, hip_flex, front_knee, back_knee, left_elbow, right_elbow, front_foot, back_foot
):
    draw_translucent_rect(frame, (22, 56), (430, 346), (20, 26, 38), 0.55)
    draw_text(frame, "Body Angle Flexion View", (34, 82), (232, 245, 255), 0.60, 1)
    draw_text(frame, f"Phase: {phase_text}", (34, 106), (170, 244, 255), 0.52, 1)
    draw_text(frame, f"Trunk {trunk_flex:.1f} deg", (34, 134), (95, 245, 255), 0.50, 1)
    draw_text(frame, f"Hip {hip_flex:.1f} deg", (34, 160), (80, 210, 255), 0.50, 1)
    draw_text(frame, f"Front Knee {front_knee:.1f} deg", (34, 186), (130, 255, 150), 0.50, 1)
    draw_text(frame, f"Back Knee {back_knee:.1f} deg", (34, 212), (110, 220, 255), 0.50, 1)
    draw_text(frame, f"Front Foot {front_foot:.1f} deg", (34, 238), (150, 255, 190), 0.50, 1)
    draw_text(frame, f"Back Foot {back_foot:.1f} deg", (34, 264), (150, 225, 255), 0.50, 1)
    draw_text(frame, f"Left Elbow {left_elbow:.1f} deg", (34, 290), (255, 205, 110), 0.50, 1)
    draw_text(frame, f"Right Elbow {right_elbow:.1f} deg", (34, 316), (255, 155, 95), 0.50, 1)
    if not has_pose:
        draw_text(frame, "Pose unavailable in this frame", (34, 336), (255, 215, 150), 0.46, 1)
        return

    c_trunk = (90, 240, 255)
    c_front_leg = (120, 255, 130)
    c_back_leg = (120, 210, 255)
    c_left_arm = (255, 210, 120)
    c_right_arm = (255, 165, 100)
    hip_mid = ((l_hip[0] + r_hip[0]) // 2, (l_hip[1] + r_hip[1]) // 2)

    cv2.line(frame, mid_sh, hip_mid, c_trunk, 6, cv2.LINE_AA)

    # Front leg (left)
    cv2.line(frame, l_hip, l_knee, c_front_leg, 5, cv2.LINE_AA)
    cv2.line(frame, l_knee, l_ankle, c_front_leg, 5, cv2.LINE_AA)
    cv2.line(frame, l_ankle, l_foot, c_front_leg, 4, cv2.LINE_AA)
    # Back leg (right)
    cv2.line(frame, r_hip, r_knee, c_back_leg, 5, cv2.LINE_AA)
    cv2.line(frame, r_knee, r_ankle, c_back_leg, 5, cv2.LINE_AA)
    cv2.line(frame, r_ankle, r_foot, c_back_leg, 4, cv2.LINE_AA)
    # Both arms
    cv2.line(frame, l_sh, l_elbow, c_left_arm, 4, cv2.LINE_AA)
    cv2.line(frame, l_elbow, l_wrist, c_left_arm, 4, cv2.LINE_AA)
    cv2.line(frame, r_sh, r_elbow, c_right_arm, 4, cv2.LINE_AA)
    cv2.line(frame, r_elbow, r_wrist, c_right_arm, 4, cv2.LINE_AA)

    joint_points = [
        (mid_sh, c_trunk), (hip_mid, c_trunk),
        (l_hip, c_front_leg), (l_knee, c_front_leg), (l_ankle, c_front_leg),
        (l_foot, c_front_leg),
        (r_hip, c_back_leg), (r_knee, c_back_leg), (r_ankle, c_back_leg), (r_foot, c_back_leg),
        (l_elbow, c_left_arm), (l_wrist, c_left_arm),
        (r_elbow, c_right_arm), (r_wrist, c_right_arm)
    ]
    for p, c in joint_points:
        cv2.circle(frame, p, 7, (0, 0, 0), -1, cv2.LINE_AA)
        cv2.circle(frame, p, 5, c, -1, cv2.LINE_AA)
    draw_text(frame, f"{hip_flex:.0f} deg", (hip_mid[0] + 10, hip_mid[1] - 10), (245, 255, 170), 0.44, 1)
    draw_text(frame, f"{front_knee:.0f} deg", (l_knee[0] + 10, l_knee[1] - 10), (170, 255, 170), 0.44, 1)
    draw_text(frame, f"{back_knee:.0f} deg", (r_knee[0] + 10, r_knee[1] - 10), (170, 225, 255), 0.44, 1)
    draw_text(frame, f"{front_foot:.0f} deg", (l_ankle[0] + 8, l_ankle[1] + 18), (170, 255, 195), 0.42, 1)
    draw_text(frame, f"{back_foot:.0f} deg", (r_ankle[0] + 8, r_ankle[1] + 18), (170, 230, 255), 0.42, 1)
    draw_text(frame, f"{left_elbow:.0f} deg", (l_elbow[0] + 10, l_elbow[1] - 10), (255, 225, 170), 0.44, 1)
    draw_text(frame, f"{right_elbow:.0f} deg", (r_elbow[0] + 10, r_elbow[1] - 10), (255, 195, 160), 0.44, 1)


def extension_color(ext_deg):
    ext = max(0.0, ext_deg)
    if ext > ICC_ELBOW_LIMIT_DEG:
        return (70, 70, 255)
    if ext <= 10.0:
        t = ext / 10.0 if 10.0 > 0 else 0.0
        b = int(70 + (40 * t))
        g = int(240 - (20 * t))
        r = int(70 + (185 * t))
        return (b, g, r)
    t = (ext - 10.0) / 5.0
    b = int(110 - (50 * t))
    g = int(230 - (50 * t))
    r = 255
    return (b, g, r)


def draw_chucking_guidelines_overlay(frame):
    draw_translucent_rect(frame, (30, 24), (w - 30, 220), (16, 22, 30), 0.78)
    draw_text(frame, "FOR ACCURATE CHUCKING ANALYSIS:", (48, 56), (230, 245, 255), 0.66, 1)
    draw_text(frame, "- Side-on camera view required", (52, 88), (205, 235, 255), 0.52, 1)
    draw_text(frame, "- Arm fully visible", (52, 116), (205, 235, 255), 0.52, 1)
    draw_text(frame, "- Camera perpendicular to bowling arm", (52, 144), (205, 235, 255), 0.52, 1)
    draw_text(frame, "- Minimum 30 FPS video", (52, 172), (205, 235, 255), 0.52, 1)
    draw_text(frame, "- Avoid front or diagonal angles", (52, 200), (205, 235, 255), 0.52, 1)


def draw_chucking_overlay(
    frame, shoulder, elbow, wrist, phase_text, ext_deg_raw, warning_on, legal_on, verdict_text,
    arm_conf_warning_on
):
    ext_display = clamp(ext_deg_raw, 0.0, ICC_ELBOW_LIMIT_DEG)
    ext_color = extension_color(ext_deg_raw)
    draw_translucent_rect(frame, (20, 18), (430, 172), (16, 22, 30), 0.62)
    draw_text(frame, "ICC Chucking Analysis", (32, 42), (230, 245, 255), 0.60, 1)
    draw_text(frame, f"Phase: {phase_text}", (32, 68), (180, 245, 255), 0.50, 1)
    draw_text(frame, f"Elbow Extension: {ext_display:.1f} deg", (32, 94), ext_color, 0.54, 1)
    draw_text(frame, "Scale: 0-15 deg (ICC)", (32, 120), (190, 255, 220), 0.50, 1)
    draw_text(frame, f"ICC Limit: {ICC_ELBOW_LIMIT_DEG:.0f} deg", (32, 146), (255, 210, 170), 0.48, 1)
    verdict_color = (200, 235, 255)
    if verdict_text == "ILLEGAL":
        verdict_color = (80, 95, 255)
    elif verdict_text == "FAIR":
        verdict_color = (120, 255, 145)
    draw_text(frame, f"Verdict: {verdict_text}", (260, 146), verdict_color, 0.48, 1)

    if shoulder is not None and elbow is not None and wrist is not None:
        arm_color = ext_color
        elbow_color = (110, 255, 130)
        if warning_on:
            elbow_color = (50, 60, 255)
        elif legal_on:
            elbow_color = (80, 250, 120)
        cv2.line(frame, shoulder, elbow, arm_color, 7, cv2.LINE_AA)
        cv2.line(frame, elbow, wrist, arm_color, 7, cv2.LINE_AA)
        for p, c in [(shoulder, (140, 240, 255)), (wrist, (140, 240, 255)), (elbow, elbow_color)]:
            cv2.circle(frame, p, 10, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(frame, p, 7, c, -1, cv2.LINE_AA)
        arc_r = int(max(18, math.hypot(shoulder[0] - elbow[0], shoulder[1] - elbow[1]) / 5))
        arc_extent = clamp(ext_display * 12.0, 6.0, 180.0)
        draw_arc(frame, elbow, arc_r, 0, arc_extent, ext_color, 3)
        draw_text(frame, f"Ext {ext_display:.1f}", (elbow[0] + 12, elbow[1] - 8), ext_color, 0.44, 1)

    if warning_on:
        draw_translucent_rect(frame, (42, h // 2 - 82), (w - 42, h // 2 + 82), (18, 24, 32), 0.80)
        draw_text(frame, "ILLEGAL ACTION DETECTED", (64, h // 2 - 24), (80, 95, 255), 0.98, 2)
        draw_text(frame, f"Extension: {ext_deg_raw:.1f} deg", (64, h // 2 + 14), (235, 245, 255), 0.66, 1)
        draw_text(frame, f"ICC Limit: {ICC_ELBOW_LIMIT_DEG:.0f} deg", (64, h // 2 + 46), (255, 215, 170), 0.62, 1)
    elif legal_on:
        draw_translucent_rect(frame, (42, h // 2 - 52), (w - 42, h // 2 + 52), (18, 28, 34), 0.76)
        draw_text(frame, "LEGAL DELIVERY", (64, h // 2 - 6), (120, 255, 145), 0.92, 2)
        draw_text(frame, "Extension within ICC limit", (64, h // 2 + 28), (210, 245, 220), 0.56, 1)

    if arm_conf_warning_on:
        draw_translucent_rect(frame, (42, h - 100), (w - 42, h - 30), (18, 24, 32), 0.80)
        draw_text(frame, "Camera angle unsuitable for ICC elbow analysis", (60, h - 58), (120, 210, 255), 0.56, 1)


def visible(lm, idx, threshold=VISIBILITY_THRESHOLD):
    return lm[idx].visibility >= threshold


def keypoints_confident(lm):
    key_idx = [0, 11, 12, 24, 26, 27, 28, 16]
    vis = [lm[i].visibility for i in key_idx]
    avg_vis = statistics.fmean(vis)
    visibility_samples.append(round(avg_vis, 4))
    if avg_vis < 0.60:
        return False
    return all(visible(lm, i, 0.45) for i in key_idx)


def in_frame(lm, idx):
    return 0.0 <= lm[idx].x <= 1.0 and 0.0 <= lm[idx].y <= 1.0


def phase_for_frame(f_idx, back_contact, front_contact, release):
    if back_contact is None or f_idx < back_contact:
        return "Run-up"
    if front_contact is None or f_idx < front_contact:
        return "Back-foot Contact"
    if release is None or f_idx < release:
        return "Front-foot Contact"
    return "Follow-through"


def elbow_angle(shoulder, elbow, wrist):
    return angle(shoulder, elbow, wrist)


def compute_elbow_angle(shoulder, elbow, wrist):
    return angle(shoulder, elbow, wrist)


def smooth_angles(angle_series, window_size=CHUCKING_SMOOTH_WINDOW):
    if not angle_series:
        return []
    ordered = sorted(angle_series, key=lambda x: x[0])
    values = [v for (_, v) in ordered]
    half = max(1, window_size // 2)
    smoothed = []
    for i, (frm, _) in enumerate(ordered):
        start = max(0, i - half)
        end = min(len(values), i + half + 1)
        avg = float(np.mean(values[start:end]))
        smoothed.append((frm, avg))
    return smoothed


def remove_outliers(angle_series, max_step=CHUCKING_OUTLIER_DELTA_DEG):
    if not angle_series:
        return []
    ordered = sorted(angle_series, key=lambda x: x[0])
    cleaned = [ordered[0]]
    for frm, val in ordered[1:]:
        last_val = cleaned[-1][1]
        if abs(val - last_val) > max_step:
            continue
        cleaned.append((frm, val))
    return cleaned


def compute_extension_window(angle_series, bfc_frame, release_frame, window_radius=CHUCKING_PHASE_WINDOW_FRAMES):
    if not angle_series or bfc_frame is None or release_frame is None:
        return None
    if release_frame < bfc_frame:
        return None
    bfc_start = max(0, bfc_frame - window_radius)
    bfc_end = bfc_frame + window_radius
    rel_start = max(0, release_frame - window_radius)
    rel_end = release_frame + window_radius
    bfc_vals = [ang for (frm, ang) in angle_series if bfc_start <= frm <= bfc_end]
    rel_vals = [ang for (frm, ang) in angle_series if rel_start <= frm <= rel_end]
    if not bfc_vals or not rel_vals:
        return None
    min_angle_bfc = min(bfc_vals)
    max_angle_release = max(rel_vals)
    return max(0.0, max_angle_release - min_angle_bfc)


while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    apply_color_grade(frame)
    angle_frame = frame.copy()
    chucking_frame = frame.copy()

    run_pose = (frame_idx % frame_skip == 0)
    if run_pose:
        resized = cv2.resize(frame, (process_width, process_height))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        res = pose.process(rgb)
        if res.pose_landmarks:
            last_landmarks = res.pose_landmarks
    else:
        res = None

    landmarks = None
    if res and res.pose_landmarks:
        landmarks = res.pose_landmarks
    elif last_landmarks:
        landmarks = last_landmarks

    if landmarks:
        pose_frames_processed += 1
        lm = landmarks.landmark
        draw_styled_pose(frame, landmarks)

        l_sh = (int(lm[11].x * w), int(lm[11].y * h))
        r_sh = (int(lm[12].x * w), int(lm[12].y * h))
        l_hip = (int(lm[23].x * w), int(lm[23].y * h))
        hip = (int(lm[24].x * w), int(lm[24].y * h))
        l_knee = (int(lm[25].x * w), int(lm[25].y * h))
        r_knee = (int(lm[26].x * w), int(lm[26].y * h))
        r_ankle = (int(lm[28].x * w), int(lm[28].y * h))
        l_ankle = (int(lm[27].x * w), int(lm[27].y * h))
        l_foot = (int(lm[31].x * w), int(lm[31].y * h))
        r_foot = (int(lm[32].x * w), int(lm[32].y * h))
        l_elbow = (int(lm[13].x * w), int(lm[13].y * h))
        r_wrist = (int(lm[16].x * w), int(lm[16].y * h))
        l_wrist = (int(lm[15].x * w), int(lm[15].y * h))
        r_elbow = (int(lm[14].x * w), int(lm[14].y * h))
        head = (int(lm[0].x * w), int(lm[0].y * h))

        shoulder_span = abs(lm[11].x - lm[12].x)
        hip_span = abs(lm[23].x - lm[24].x)
        if shoulder_span < 0.22 and hip_span < 0.19:
            side_on_good_frames += 1

        full_body_visible = (
            visible(lm, 0, 0.4) and visible(lm, 27, 0.4) and visible(lm, 28, 0.4) and
            in_frame(lm, 0) and in_frame(lm, 27) and in_frame(lm, 28)
        )
        if full_body_visible:
            full_body_visible_frames += 1

        low_conf_frame = not keypoints_confident(lm)
        if low_conf_frame:
            low_confidence_frames += 1
        else:
            confident_frames += 1

            lean_angle = angle(l_sh, hip, r_sh)
            shoulder_angle = abs(math.degrees(math.atan2(r_sh[1] - l_sh[1], r_sh[0] - l_sh[0])))
            knee_flexion = angle(hip, r_knee, r_ankle)
            r_elbow_ang = compute_elbow_angle(r_sh, r_elbow, r_wrist)
            elbow_joint_deg = r_elbow_ang
            current_elbow_angle = r_elbow_ang
            left_elbow_deg = compute_elbow_angle(l_sh, l_elbow, l_wrist)
            right_elbow_deg = r_elbow_ang
            mid_sh = ((l_sh[0] + r_sh[0]) // 2, (l_sh[1] + r_sh[1]) // 2)
            hip_flexion_deg = angle(mid_sh, hip, r_knee)
            front_knee_deg = angle(l_hip, l_knee, l_ankle)
            back_knee_deg = angle(hip, r_knee, r_ankle)
            front_foot_deg = angle(l_knee, l_ankle, l_foot)
            back_foot_deg = angle(r_knee, r_ankle, r_foot)
            torso_dx = mid_sh[0] - hip[0]
            torso_dy = mid_sh[1] - hip[1]
            trunk_flexion_deg = abs(math.degrees(math.atan2(torso_dx, -torso_dy))) if torso_dy != 0 else 0.0
            if (
                lm[12].visibility >= CHUCKING_LANDMARK_VIS_THRESHOLD and
                lm[14].visibility >= CHUCKING_LANDMARK_VIS_THRESHOLD and
                lm[16].visibility >= CHUCKING_LANDMARK_VIS_THRESHOLD
            ):
                right_elbow_angle_series.append((frame_idx, r_elbow_ang))
            arm_frames_for_chucking += 1
            if visible(lm, 12, 0.5) and visible(lm, 14, 0.5) and visible(lm, 16, 0.5):
                arm_visible_frames += 1
            upperarm_horizontal = abs(r_sh[1] - r_elbow[1]) <= int(0.06 * h)
            right_upperarm_horizontal_flags.append((frame_idx, upperarm_horizontal))

            center_x = hip[0]
            dt = None
            if prev_x is not None:
                dx = center_x - prev_x
                if prev_pose_frame_idx is not None and fps > 0:
                    frame_delta = frame_idx - prev_pose_frame_idx
                    dt = frame_delta / fps
                if dt and dt > 0:
                    pass
            prev_x = center_x
            prev_t = time.time()
            prev_pose_frame_idx = frame_idx

            weight_transfer = "Unknown"
            head_position = "Head Lean Right" if lm[0].x > lm[11].x else "Head Lean Left"
            shoulder_status = "Open Shoulder"

            lean_angle_list.append(round(lean_angle, 2))
            shoulder_angle_list.append(round(shoulder_angle, 2))
            head_x_list.append(round(lm[0].x * w, 2))
            knee_angle_list.append(round(knee_flexion, 2))
            ankle_y_list.append(l_ankle[1])
            wrist_x_list.append(r_wrist[0])
            wrist_y_list.append(r_wrist[1])

            if head_center_x is None:
                head_center_x = head[0]

            # Front foot contact detection (left ankle)
            if ankle_prev_y is not None and foot_contact_frame is None:
                ankle_vy = l_ankle[1] - ankle_prev_y
                if ankle_vy > 0 and l_ankle[1] > int(0.85 * h):
                    if abs(ankle_vy) < 2:
                        foot_contact_frame = frame_idx
            ankle_prev_y = l_ankle[1]

            # Back foot contact detection (right ankle)
            if r_ankle_prev_y is not None and back_foot_contact_frame is None:
                r_ankle_vy = r_ankle[1] - r_ankle_prev_y
                if r_ankle_vy > 0 and r_ankle[1] > int(0.82 * h):
                    if abs(r_ankle_vy) < 2:
                        back_foot_contact_frame = frame_idx
            r_ankle_prev_y = r_ankle[1]

            if back_foot_contact_frame is not None and frame_idx >= back_foot_contact_frame and release_frame is None:
                if delivery_min_elbow is None:
                    delivery_min_elbow = r_elbow_ang
                    delivery_max_elbow = r_elbow_ang
                else:
                    delivery_min_elbow = min(delivery_min_elbow, r_elbow_ang)
                    delivery_max_elbow = max(delivery_max_elbow, r_elbow_ang)

            # Release frame detection (right wrist local speed peak)
            if wrist_prev is not None and wrist_prev_frame_idx is not None and fps > 0:
                frame_delta_w = max(1, frame_idx - wrist_prev_frame_idx)
                dt_w = frame_delta_w / fps
                if dt_w > 0:
                    dx_w = r_wrist[0] - wrist_prev[0]
                    dy_w = r_wrist[1] - wrist_prev[1]
                    wrist_speed = math.hypot(dx_w, dy_w) / dt_w
                    if wrist_speed_prevprev is not None and wrist_speed_prev is not None:
                        if release_frame is None:
                            if wrist_speed_prev > wrist_speed_prevprev and wrist_speed_prev > wrist_speed and wrist_speed_prev > 300:
                                release_frame = frame_idx - 1
                                smoothed_series = smooth_angles(right_elbow_angle_series, CHUCKING_SMOOTH_WINDOW)
                                cleaned_series = remove_outliers(smoothed_series, CHUCKING_OUTLIER_DELTA_DEG)
                                ext_val = compute_extension_window(
                                    cleaned_series,
                                    back_foot_contact_frame,
                                    release_frame,
                                    CHUCKING_PHASE_WINDOW_FRAMES
                                )
                                if ext_val is not None:
                                    elbow_extension_deg = max(0.0, ext_val)
                                    max_elbow_extension = max(max_elbow_extension, elbow_extension_deg)
                                    chucking_suspected = elbow_extension_deg > ICC_ELBOW_LIMIT_DEG
                                    chucking_data_ready = True
                                    arm_ratio_now = (arm_visible_frames / arm_frames_for_chucking) if arm_frames_for_chucking else 0.0
                                    gate_now = (
                                        fps_gate_passed and
                                        arm_ratio_now >= CHUCKING_ARM_VISIBILITY_THRESHOLD and
                                        chucking_data_ready
                                    )
                                    if gate_now:
                                        if chucking_suspected:
                                            freeze_frames_remaining = int(max(1, round(fps * 2.0)))
                                        else:
                                            legal_flash_frames = int(max(1, round(fps * 1.0)))
                                delivery_min_elbow = None
                                delivery_max_elbow = None
                    wrist_speed_prevprev = wrist_speed_prev
                    wrist_speed_prev = wrist_speed
            wrist_prev = r_wrist
            wrist_prev_frame_idx = frame_idx

        # Colors (BGR)
        c_lean = PALETTE["lean"]
        c_shoulder = PALETTE["shoulder"]
        c_knee = PALETTE["knee"]
        c_head = PALETTE["head"]
        c_marker = PALETTE["marker"]
        c_wrist_trail = (60, 170, 255)
        c_ankle_trail = (140, 235, 110)

        append_trail_point(wrist_trail, r_wrist)
        append_trail_point(ankle_trail, l_ankle)
        draw_motion_trail(frame, wrist_trail, c_wrist_trail)
        draw_motion_trail(frame, ankle_trail, c_ankle_trail)

        phase_now = phase_for_frame(frame_idx, back_foot_contact_frame, foot_contact_frame, release_frame)
        if release_frame is not None and frame_idx >= release_frame:
            phase_now = "Release"
        if phase_now != current_phase:
            current_phase = phase_now
            phase_transitions.append((current_phase, frame_idx))
        live_conf_ratio = (confident_frames / pose_frames_processed) if pose_frames_processed else 0.0

        # Risk banner (permanent)
        risk_label, risk_color = risk_color_for(lean_angle, shoulder_angle)
        draw_translucent_rect(frame, (0, 0), (w, 42), risk_color, 0.82)
        draw_text(frame, f"Injury Risk: {risk_label}", (14, 29), PALETTE["text_dark"], 0.78, 2)

        draw_translucent_rect(frame, (20, 46), (390, 298), PALETTE["panel_dark"], 0.52)

        # Lean angle line (torso)
        mid_sh = ((l_sh[0] + r_sh[0]) // 2, (l_sh[1] + r_sh[1]) // 2)
        cv2.line(frame, mid_sh, hip, c_lean, 4, cv2.LINE_AA)
        draw_marker(frame, hip, c_lean, 6)

        # Shoulder rotation arc + line
        cv2.line(frame, l_sh, r_sh, c_shoulder, 4, cv2.LINE_AA)
        arc_radius = int(max(20, math.hypot(r_sh[0] - l_sh[0], r_sh[1] - l_sh[1]) / 3))
        arc_center = mid_sh
        start_angle = 0
        end_angle = clamp(shoulder_angle, 5, 175)
        draw_arc(frame, arc_center, arc_radius, start_angle, end_angle, c_shoulder, 3)

        # Knee angle line + arc
        draw_angle_lines(frame, hip, r_knee, r_ankle, c_knee, 4)
        knee_arc_radius = int(max(16, math.hypot(hip[0] - r_knee[0], hip[1] - r_knee[1]) / 4))
        draw_arc(frame, r_knee, knee_arc_radius, 0, clamp(knee_flexion, 5, 175), c_knee, 3)
        draw_marker(frame, r_knee, c_knee, 6)

        # Head stability line (center + deviation)
        if head_center_x is not None:
            cv2.line(frame, (head_center_x, 0), (head_center_x, h), c_head, 2, cv2.LINE_AA)
            cv2.line(frame, (head_center_x, head[1]), (head[0], head[1]), c_head, 3, cv2.LINE_AA)
            draw_marker(frame, head, c_head, 6)
            deviation = head[0] - head_center_x
            last_head_deviation = deviation

        # Weight transfer

        if foot_contact_frame is not None and frame_idx >= foot_contact_frame:
            pass
        if release_frame is not None and frame_idx >= release_frame:


            pass

        draw_telemetry_hud(frame, phase_now, live_conf_ratio, frame_idx, total_frames,
                           back_foot_contact_frame is not None,
                           foot_contact_frame is not None,
                           release_frame is not None)
                           
        draw_phase_timeline(frame, frame_idx, total_frames, 
                            back_foot_contact_frame, 
                            foot_contact_frame, 
                            release_frame)
                            
        draw_text(frame, f"Lean {lean_angle:.1f} deg", (25, 75), PALETTE["lean"], 0.65, 2)
        draw_text(frame, f"Shoulder {shoulder_angle:.1f} deg", (25, 105), PALETTE["shoulder"], 0.65, 2)
        draw_text(frame, f"Knee {knee_flexion:.1f} deg", (25, 135), PALETTE["knee"], 0.65, 2)
        dev = head[0] - head_center_x if head_center_x else 0
        draw_text(frame, f"Head dev {dev}px", (25, 165), PALETTE["head"], 0.65, 2)
        
        draw_text(frame, f"Weight: {weight_transfer}", (25, 195), PALETTE["text_light"], 0.65, 2)
        draw_text(frame, f"Phase: {phase_now}", (25, 225), (150, 220, 255), 0.65, 2)
        
        if foot_contact_frame is not None and frame_idx >= foot_contact_frame:
            draw_text(frame, "Front Foot Contact", (25, 255), (82, 200, 255), 0.65, 2)
        if release_frame is not None and frame_idx >= release_frame:
            draw_text(frame, "Release", (25, 285), (50, 150, 255), 0.65, 2)

        # Release Trigger Glow
        if release_frame is not None and frame_idx == release_frame:
            draw_glowing_circle(frame, r_wrist, 18, (80, 180, 255))
            draw_text(frame, "BALL RELEASE", (r_wrist[0] + 25, r_wrist[1]), (200, 255, 255), 0.6, 2)

        if foot_contact_frame is not None and frame_idx >= foot_contact_frame:
            draw_marker(frame, l_ankle, c_marker, 8)
        if release_frame is not None and frame_idx >= release_frame:
            draw_marker(frame, r_wrist, c_marker, 8)

        # Persistent values even on low-confidence frames
        if low_conf_frame:
            pass
        running_ext = elbow_extension_deg if chucking_data_ready else 0.0
        arm_ratio_live = (arm_visible_frames / arm_frames_for_chucking) if arm_frames_for_chucking else 0.0
        arm_unsuitable_live = arm_frames_for_chucking >= int(max(10, fps * 0.5)) and arm_ratio_live < CHUCKING_ARM_VISIBILITY_THRESHOLD
        verdict_live = "INCONCLUSIVE"
        if chucking_data_ready and fps_gate_passed and not arm_unsuitable_live:
            verdict_live = "ILLEGAL" if chucking_suspected else "FAIR"
        draw_chucking_overlay(
            chucking_frame,
            r_sh, r_elbow, r_wrist,
            phase_now,
            running_ext,
            freeze_frames_remaining > 0 and chucking_suspected and verdict_live == "ILLEGAL",
            legal_flash_frames > 0 and verdict_live == "FAIR" and release_frame is not None,
            verdict_live,
            arm_unsuitable_live
        )
        draw_body_flexion_overlay(
            angle_frame, True, phase_now, mid_sh, l_sh, r_sh, l_hip, hip, l_knee, r_knee, l_ankle, r_ankle,
            l_foot, r_foot, l_elbow, r_elbow, l_wrist, r_wrist,
            trunk_flexion_deg, hip_flexion_deg, front_knee_deg, back_knee_deg, left_elbow_deg, right_elbow_deg,
            front_foot_deg, back_foot_deg
        )
    else:
        # No landmarks at all: still keep metrics visible.
        risk_label, risk_color = risk_color_for(lean_angle, shoulder_angle)
        draw_translucent_rect(frame, (0, 0), (w, 42), risk_color, 0.82)
        draw_text(frame, f"Injury Risk: {risk_label}", (14, 29), PALETTE["text_dark"], 0.78, 2)
        draw_translucent_rect(frame, (20, 46), (390, 370), PALETTE["panel_dark"], 0.52)
        phase_now = phase_for_frame(frame_idx, back_foot_contact_frame, foot_contact_frame, release_frame)
        if release_frame is not None and frame_idx >= release_frame:
            phase_now = "Release"
        if phase_now != current_phase:
            current_phase = phase_now
            phase_transitions.append((current_phase, frame_idx))
        live_conf_ratio = (confident_frames / pose_frames_processed) if pose_frames_processed else 0.0
        running_ext = elbow_extension_deg if chucking_data_ready else 0.0
        arm_ratio_live = (arm_visible_frames / arm_frames_for_chucking) if arm_frames_for_chucking else 0.0
        arm_unsuitable_live = arm_frames_for_chucking >= int(max(10, fps * 0.5)) and arm_ratio_live < CHUCKING_ARM_VISIBILITY_THRESHOLD
        verdict_live = "INCONCLUSIVE"
        if chucking_data_ready and fps_gate_passed and not arm_unsuitable_live:
            verdict_live = "ILLEGAL" if chucking_suspected else "FAIR"
        draw_chucking_overlay(
            chucking_frame,
            None, None, None,
            phase_now,
            running_ext,
            freeze_frames_remaining > 0 and chucking_suspected and verdict_live == "ILLEGAL",
            legal_flash_frames > 0 and verdict_live == "FAIR" and release_frame is not None,
            verdict_live,
            arm_unsuitable_live
        )
        draw_body_flexion_overlay(
            angle_frame, False, phase_now, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, trunk_flexion_deg, hip_flexion_deg, front_knee_deg, back_knee_deg,
            left_elbow_deg, right_elbow_deg, front_foot_deg, back_foot_deg
        )

    if frame is None:
        continue
    if out_w != w or out_h != h:
        frame = cv2.copyMakeBorder(
            frame, 0, out_h - h, 0, out_w - w, cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )
        angle_frame = cv2.copyMakeBorder(
            angle_frame, 0, out_h - h, 0, out_w - w, cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )
        chucking_frame = cv2.copyMakeBorder(
            chucking_frame, 0, out_h - h, 0, out_w - w, cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )
    if frame_idx < int(max(1, round(fps * 3.0))):
        draw_chucking_guidelines_overlay(chucking_frame)
    out.write(frame)
    angle_out.write(angle_frame)
    if freeze_frames_remaining > 0:
        if freeze_frame is None:
            freeze_frame = chucking_frame.copy()
        chucking_out.write(freeze_frame)
        freeze_frames_remaining -= 1
    else:
        freeze_frame = None
        chucking_out.write(chucking_frame)
        if legal_flash_frames > 0:
            legal_flash_frames -= 1
    frame_idx += 1

cap.release()
out.release()
angle_out.release()
chucking_out.release()

# ── ffmpeg H.264 post-processing ────────────────────────────────────────
def _transcode_h264(src, dst):
    """Re-encode src (mp4v) to dst (libx264/yuv420p) for browser playback.
    Returns dst path on success, src path on failure."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", src,
                "-c:v", "libx264",
                "-preset", "fast",       # fast encode, good compression
                "-crf", "23",            # constant quality (18=best, 28=worst)
                "-pix_fmt", "yuv420p",   # required for browser <video> compat
                "-movflags", "+faststart", # stream-friendly: moov atom at front
                dst
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=600            # 10-min max per video
        )
        # Verify output is a real file, not a zero-byte artifact
        if os.path.exists(dst) and os.path.getsize(dst) > 1024:
            try:
                os.remove(src)     # free disk space in shared volume
            except OSError:
                pass
            return dst, True
        else:
            print(f"[ffmpeg] WARN: output {dst} is missing or too small", file=sys.stderr)
            return src, False
    except subprocess.TimeoutExpired:
        print(f"[ffmpeg] ERROR: transcode timed out for {src}", file=sys.stderr)
        return src, False
    except subprocess.CalledProcessError as exc:
        print(f"[ffmpeg] ERROR: transcode failed for {src}: {exc.stderr.decode()[-500:]}", file=sys.stderr)
        return src, False
    except Exception as exc:
        print(f"[ffmpeg] ERROR: unexpected error: {exc}", file=sys.stderr)
        return src, False

final_output_path = output_path
final_angle_output_path = angle_output_path
final_chucking_output_path = chucking_output_path
ffmpeg_available = shutil.which("ffmpeg") is not None
transcoded = False
angle_transcoded = False
chucking_transcoded = False

if ffmpeg_available:
    print("[ffmpeg] Starting H.264 transcode of 3 videos...", file=sys.stderr)
    final_output_path, transcoded = _transcode_h264(
        output_path, base + "_skeleton_h264.mp4")
    final_angle_output_path, angle_transcoded = _transcode_h264(
        angle_output_path, base + "_angles_h264.mp4")
    final_chucking_output_path, chucking_transcoded = _transcode_h264(
        chucking_output_path, base + "_chucking_analysis_h264.mp4")
    print(f"[ffmpeg] Done. transcoded={transcoded} angle={angle_transcoded} chucking={chucking_transcoded}", file=sys.stderr)
else:
    print("[ffmpeg] WARNING: ffmpeg not found — videos may not play in browser", file=sys.stderr)

def risk_level(max_lean, max_shoulder):
    score = 0
    if max_lean > 25:
        score += 1
    if max_shoulder > 30:
        score += 1
    if score >= 2:
        return "High Risk"
    if score == 1:
        return "Moderate Risk"
    return "Low Risk"


max_lean = max(lean_angle_list) if lean_angle_list else 0
max_shoulder = max(shoulder_angle_list) if shoulder_angle_list else 0
injury_risk = risk_level(max_lean, max_shoulder)



def score_stability(head_x, lean_vals, width):
    if not head_x or not lean_vals or width == 0:
        return 0
    head_std = statistics.pstdev(head_x) / width
    lean_std = statistics.pstdev(lean_vals)
    penalty = head_std * 200 + lean_std * 1.5
    score = 100 - penalty
    return max(0, min(100, round(score, 2)))


stability_score = score_stability(head_x_list, lean_angle_list, w)
avg_visibility = round(statistics.fmean(visibility_samples), 3) if visibility_samples else 0.0
confidence_ratio = round((confident_frames / pose_frames_processed), 3) if pose_frames_processed else 0.0
processing_ms = int((time.time() - analysis_started_at) * 1000)
side_on_ratio = round((side_on_good_frames / pose_frames_processed), 3) if pose_frames_processed else 0.0
full_body_ratio = round((full_body_visible_frames / pose_frames_processed), 3) if pose_frames_processed else 0.0
arm_visibility_ratio = round((arm_visible_frames / arm_frames_for_chucking), 3) if arm_frames_for_chucking else 0.0
smoothed_elbow_series = smooth_angles(right_elbow_angle_series, CHUCKING_SMOOTH_WINDOW)
filtered_elbow_series = remove_outliers(smoothed_elbow_series, CHUCKING_OUTLIER_DELTA_DEG)
valid_angle_frames = len(filtered_elbow_series)
angle_total_frames = total_frames if total_frames and total_frames > 0 else max(frame_idx, 1)
elbow_confidence = round(valid_angle_frames / max(1, angle_total_frames), 3)

if confidence_ratio >= 0.8:
    analysis_quality = "Good"
elif confidence_ratio >= 0.55:
    analysis_quality = "Moderate"
else:
    analysis_quality = "Low"

if side_on_ratio >= 0.7 and full_body_ratio >= 0.8:
    camera_angle_quality = "Good"
elif side_on_ratio >= 0.5 and full_body_ratio >= 0.65:
    camera_angle_quality = "Moderate"
else:
    camera_angle_quality = "Poor"
camera_gate_passed = camera_angle_quality != "Poor"

fps_norm = clamp(fps / 30.0, 0.0, 1.0)
lean_conf = clamp(0.6 * confidence_ratio + 0.4 * side_on_ratio, 0.0, 1.0)
contact_conf = clamp(
    0.45 * confidence_ratio +
    0.25 * (1.0 if foot_contact_frame is not None else 0.0) +
    0.2 * (1.0 if back_foot_contact_frame is not None else 0.0) +
    0.1 * full_body_ratio,
    0.0, 1.0
)
release_conf = clamp(
    0.5 * confidence_ratio +
    0.3 * (1.0 if release_frame is not None else 0.0) +
    0.2 * fps_norm,
    0.0, 1.0
)

warning = None
if chosen_codec not in ("avc1", "H264", "X264", "VP90", "VP80", "vp90", "vp80") and not transcoded:
    warning = "Processed video codec may not be browser-compatible. Install ffmpeg for H.264 output."
if analysis_quality != "Good":
    confidence_msg = "Pose confidence was limited in some frames. Use side-on angle and better lighting."
    warning = confidence_msg if warning is None else f"{warning} {confidence_msg}"
if camera_angle_quality == "Poor":
    camera_msg = "Camera quality is poor for precision. Keep full body visible with stable side-on framing."
    warning = camera_msg if warning is None else f"{warning} {camera_msg}"

chucking_gate_passed = (
    camera_gate_passed and
    fps_gate_passed and
    arm_visibility_ratio >= CHUCKING_ARM_VISIBILITY_THRESHOLD and
    confidence_ratio >= CHUCKING_CONF_THRESHOLD and
    elbow_confidence >= CHUCKING_MIN_CONFIDENCE and
    chucking_data_ready
)
chucking_gate_reasons = []
if not fps_gate_passed:
    chucking_gate_reasons.append("FPS_BELOW_60")
if not camera_gate_passed:
    chucking_gate_reasons.append("CAMERA_QUALITY_POOR")
if arm_visibility_ratio < CHUCKING_ARM_VISIBILITY_THRESHOLD:
    chucking_gate_reasons.append("ARM_NOT_CLEARLY_VISIBLE")
if confidence_ratio < CHUCKING_CONF_THRESHOLD:
    chucking_gate_reasons.append("POSE_CONFIDENCE_LOW")
if elbow_confidence < CHUCKING_MIN_CONFIDENCE:
    chucking_gate_reasons.append("ELBOW_SIGNAL_CONFIDENCE_LOW")
if not chucking_data_ready:
    chucking_gate_reasons.append("RELEASE_OR_ELBOW_SERIES_NOT_RELIABLE")
if elbow_confidence < CHUCKING_MIN_CONFIDENCE:
    chucking_verdict = "INCONCLUSIVE"
elif chucking_gate_passed:
    chucking_verdict = "SUSPECTED" if max_elbow_extension > ICC_ELBOW_LIMIT_DEG else "LEGAL"
else:
    chucking_verdict = "INCONCLUSIVE"

if not fps_gate_passed:
    fps_msg = f"High-FPS requirement not met for chucking screening (need >= {int(HIGH_FPS_THRESHOLD)} fps)."
    warning = fps_msg if warning is None else f"{warning} {fps_msg}"
if not chucking_gate_passed:
    gate_msg = "Chucking verdict is inconclusive due to capture/confidence gate. Use side-on full-body 60/120fps video and keep arm fully visible."
    warning = gate_msg if warning is None else f"{warning} {gate_msg}"
elif chucking_suspected:
    chuck_msg = "Screening flagged possible illegal action (>15deg elbow extension). Confirm with formal biomechanics testing."
    warning = chuck_msg if warning is None else f"{warning} {chuck_msg}"

phase_summary = [{"phase": name, "frame": frm} for name, frm in phase_transitions]
elbow_angle_series = [{"frame": f, "angle": round(a, 2)} for (f, a) in right_elbow_angle_series]
elbow_angle_series_filtered = [{"frame": f, "angle": round(a, 2)} for (f, a) in filtered_elbow_series]

import sys
print(f"Generated {final_output_path}: {os.path.getsize(final_output_path) if os.path.exists(final_output_path) else 0} bytes", file=sys.stderr)
print(f"Generated {final_angle_output_path}: {os.path.getsize(final_angle_output_path) if os.path.exists(final_angle_output_path) else 0} bytes", file=sys.stderr)
print(f"Generated {final_chucking_output_path}: {os.path.getsize(final_chucking_output_path) if os.path.exists(final_chucking_output_path) else 0} bytes", file=sys.stderr)

print(json.dumps({
    "video": final_output_path.replace("\\", "/"),
    "angleVideo": final_angle_output_path.replace("\\", "/"),
    "chuckingVideo": final_chucking_output_path.replace("\\", "/"),
    "ffmpegAvailable": ffmpeg_available,
    "transcoded": transcoded,
    "angleTranscoded": angle_transcoded,
    "chuckingTranscoded": chucking_transcoded,
    "codec": chosen_codec,
    "fps": round(fps, 2),
    "warning": warning,
    "analysisQuality": analysis_quality,
    "cameraAngleQuality": camera_angle_quality,
    "cameraGatePassed": camera_gate_passed,
    "fpsGatePassed": fps_gate_passed,
    "confidenceRatio": confidence_ratio,
    "sideOnRatio": side_on_ratio,
    "fullBodyVisibleRatio": full_body_ratio,
    "armVisibilityRatio": arm_visibility_ratio,
    "avgPoseVisibility": avg_visibility,
    "poseFramesProcessed": pose_frames_processed,
    "validElbowAngleFrames": valid_angle_frames,
    "elbowSignalConfidence": elbow_confidence,
    "confidentFrames": confident_frames,
    "lowConfidenceFrames": low_confidence_frames,
    "processingMs": processing_ms,
    "currentPhase": current_phase,
    "backFootContactFrame": back_foot_contact_frame,
    "phaseSummary": phase_summary,
    "leanAngle": round(lean_angle, 2),
    "shoulder": shoulder_status,
    "head": head_position,
    "weightTransfer": weight_transfer,
    "kneeFlexion": round(knee_flexion, 2),
    "injuryRisk": injury_risk,
    "footContactFrame": foot_contact_frame,
    "releaseFrame": release_frame,
    "stabilityScore": stability_score,
    "chuckingThresholdDeg": ICC_ELBOW_LIMIT_DEG,
    "elbowExtensionDeg": round(elbow_extension_deg, 2),
    "elbowExtension": round(elbow_extension_deg, 2),
    "maxElbowExtension": round(max_elbow_extension, 2),
    "chuckingSuspected": chucking_suspected,
    "chuckingDataReady": chucking_data_ready,
    "chuckingGatePassed": chucking_gate_passed,
    "chuckingGateReasons": chucking_gate_reasons,
    "chuckingVerdict": chucking_verdict,
    "highFpsThreshold": HIGH_FPS_THRESHOLD,
    "chuckingConfidenceThreshold": CHUCKING_CONF_THRESHOLD,
    "chuckingSignalConfidenceThreshold": CHUCKING_MIN_CONFIDENCE,
    "elbowAngleSeries": elbow_angle_series,
    "elbowAngleSeriesFiltered": elbow_angle_series_filtered,
    "iccVerdict": chucking_verdict,
    "metricConfidence": {
        "lean": round(lean_conf, 3),
        "contact": round(contact_conf, 3),
        "release": round(release_conf, 3)
    },
    "leanAngleSeries": lean_angle_list,
    "shoulderRotationSeries": shoulder_angle_list,
    "headXSeries": head_x_list,
    "kneeFlexionSeries": knee_angle_list
}))
