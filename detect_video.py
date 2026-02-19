"""
IRIS Accident Detection — Multi-Video Batch Processor
Usage:
  python detect_video.py                        # process default test1.mp4
  python detect_video.py vid1.mp4 vid2.mp4      # process multiple videos
  python detect_video.py --conf 0.15 vid1.mp4   # custom confidence
"""
import sys, argparse
from ultralytics import YOLO

MODEL_PATH = "m1.pt"

def parse_args():
    parser = argparse.ArgumentParser(description="IRIS Accident Detector — Video")
    parser.add_argument("videos", nargs="*", default=["test1.mp4"],
                        help="One or more video file paths to process")
    parser.add_argument("--model", default=MODEL_PATH, help="YOLO model weights (.pt)")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold (default: 0.25)")
    parser.add_argument("--iou",  type=float, default=0.5,  help="IoU threshold (default: 0.5)")
    parser.add_argument("--imgsz", type=int, default=960,   help="Inference image size (default: 960)")
    return parser.parse_args()

def main():
    args = parse_args()
    model = YOLO(args.model)
    print(f"\n{'='*55}")
    print(f"  IRIS Accident Detection  |  Model: {args.model}")
    print(f"  Videos to process: {len(args.videos)}")
    print(f"  Conf: {args.conf}  IoU: {args.iou}  ImgSz: {args.imgsz}")
    print(f"{'='*55}\n")

    for i, video in enumerate(args.videos, 1):
        print(f"[{i}/{len(args.videos)}] Processing: {video}")
        try:
            results = model.predict(
                source=video,
                conf=args.conf,
                iou=args.iou,
                imgsz=args.imgsz,
                save=True,
                verbose=True
            )
            total_detections = sum(len(r.boxes) for r in results if r.boxes is not None)
            print(f"  ✅ Done — {total_detections} total detections across all frames\n")
        except Exception as e:
            print(f"  ❌ Failed to process {video}: {e}\n")

    print("All done. Check runs/detect/ for annotated output videos.")

if __name__ == "__main__":
    main()
