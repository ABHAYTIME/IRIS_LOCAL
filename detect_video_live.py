"""
IRIS Accident Detection — Live Preview (Multi-Video)
Usage:
  python detect_video_live.py                       # default test1.mp4
  python detect_video_live.py vid1.mp4 vid2.mp4     # plays each video in sequence
  python detect_video_live.py --conf 0.10 vid1.mp4  # custom confidence
Press Q to skip to next video / quit.
"""
import cv2, time, argparse
from ultralytics import YOLO

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
    prev_t = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_id += 1

        results = model.predict(frame, imgsz=imgsz, conf=conf, verbose=False)[0]
        annotated = results.plot()

        now = time.time()
        fps = 1.0 / (now - prev_t) if now != prev_t else 0
        prev_t = now
        num_det = 0 if results.boxes is None else len(results.boxes)
        best_conf = float(results.boxes.conf.max().cpu().numpy()) if num_det > 0 else 0.0

        cv2.putText(annotated, f"File: {video_path} | Frame: {frame_id}/{total_frames}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 255, 200), 2)
        cv2.putText(annotated, f"FPS: {fps:.1f}  Det: {num_det}  BestConf: {best_conf:.3f}  Thres: {conf}",
                    (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 255, 200), 2)

        cv2.imshow("IRIS Accident Detection (Live)", annotated)
        if cv2.waitKey(1) & 0xFF in [ord('q'), ord('Q')]:
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
