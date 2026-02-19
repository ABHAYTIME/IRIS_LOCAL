from ultralytics import YOLO
import cv2
import os

# Load model
model = YOLO("best.pt")

# Image path
IMAGE_PATH = "test.jpg"
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Run prediction
results = model.predict(
    source=IMAGE_PATH,
    conf=0.25,
    imgsz=960,
    save=False
)

# Get annotated image
annotated_img = results[0].plot()

# Save image
out_path = os.path.join(OUTPUT_DIR, "detected_test.jpg")
cv2.imwrite(out_path, annotated_img)

# Show image
cv2.imshow("Accident Detection", annotated_img)
cv2.waitKey(0)
cv2.destroyAllWindows()

print(f"✅ Detection saved at: {out_path}")
