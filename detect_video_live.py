"""
IRIS Accident Detection — Live Preview (Multi-Video)
Usage:
  python detect_video_live.py                       # default test1.mp4
  python detect_video_live.py vid1.mp4 vid2.mp4     # plays each video in sequence
  python detect_video_live.py --conf 0.10 vid1.mp4  # custom confidence
Press Q to skip to next video / quit.
"""
import cv2, time, argparse, os, requests
from ultralytics import YOLO

API_URL = "http://127.0.0.1:5000/api/new_alert"

def parse_args():
    parser = argparse.ArgumentParser(description="IRIS Accident Detector — Live Preview")
    parser.add_argument("videos", nargs="*", default=["test1.mp4"],
                        help="One or more video file paths")
    parser.add_argument("--model", default="m1.pt",    help="YOLO weights (.pt)")
    parser.add_argument("--conf", type=float, default=0.05, help="Confidence threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    return parser.parse_args()

def process_video(model, video_path, conf, imgsz):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Could not open: {video_path}")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"\n▶ Playing: {video_path}  ({w}x{h}, {total_frames} frames)")
    print("  Press Q to skip / quit\n")

    frame_id = 0
    alert_sent = False
    frame_skip = 1

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_id += 1
        
        # SPEED TRICK: Only run AI on every 3rd frame (configurable)
        if frame_id % frame_skip != 0:
            cv2.imshow("IRIS Accident Detection (Live)", frame)
            if (cv2.waitKey(1) & 0xFF) in [ord('q'), ord('Q')]:
                break
            continue

        results = model(frame, imgsz=imgsz, conf=conf, verbose=False)
        accident_detected = False

        if results[0].boxes is not None:
            for box in results[0].boxes:
                class_id = int(box.cls[0])
                conf_val = float(box.conf[0])
                
                # Check specifically for Accidents (Class 1)
                if class_id == 1 and conf_val >= 0.25:
                    accident_detected = True
                    
                    # --- ACTION 1: DRAW BOXES MANUALLY ---
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    cv2.putText(frame, f"ACCIDENT {conf_val:.2f}", (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                    
                    # --- ACTION 2: SAVE SNAPSHOT & SEND ALERT (EXACTLY ONCE) ---
                    if not alert_sent:
                        alert_sent = True
                        ts = time.time()
                        
                        snap_path = os.path.abspath(f"outputs/crash_{int(ts)}.jpg")
                        os.makedirs("outputs", exist_ok=True)
                        cv2.imwrite(snap_path, frame)
                        print(f"zSNAPSHOT SAVED: {snap_path}")
                        
                        # Send to Flask
                        payload = {
                            "location": "Main St", 
                            "image_path": snap_path,
                            "time": time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(ts))
                        }
                        try:
                            res = requests.post(API_URL, json=payload, timeout=2)
                            print(f"\n[!] FIRST ALERT SENT! status: {res.status_code}")
                        except Exception as e:
                            print(f"\n[!] API error: {e}")

        # 4. Show the AI frame
        if accident_detected:
            cv2.imshow("IRIS Accident Detection (Live)", frame)
        else:
            # If no accident, show the plot (shows cars too if you want)
            cv2.imshow("IRIS Accident Detection (Live)", results[0].plot())

        if (cv2.waitKey(1) & 0xFF) in [ord('q'), ord('Q')]:
            print("  ⏭ Skipped / Quit")
            break

    cap.release()

def main():
    args = parse_args()
    model = YOLO(args.model)
    print(f"\n{'='*55}")
    print(f"  IRIS Live Detector  |  Model: {args.model}")
    print(f"  Videos: {len(args.videos)}  Conf: {args.conf}  ImgSz: {args.imgsz}")
    print(f"{'='*55}")

    for i, video in enumerate(args.videos, 1):
        print(f"\n[{i}/{len(args.videos)}]", end="")
        process_video(model, video, args.conf, args.imgsz)

    cv2.destroyAllWindows()
    print("\n✅ All videos processed. Done.")

if __name__ == "__main__":
    main()
