"""
Run this after uploading your labeled dataset from Roboflow.
Expects:
  ~/rustdetection/labeled/images/*.jpg
  ~/rustdetection/labeled/labels/*.txt

Splits 80/20 into train/val and creates data.yaml.
"""
import os, shutil, random

os.chdir(os.path.dirname(os.path.abspath(__file__)))

LABELED_DIR = "labeled"
DATASET_DIR = "dataset"
VAL_SPLIT = 0.2
SEED = 42

img_dir = os.path.join(LABELED_DIR, "images")
lbl_dir = os.path.join(LABELED_DIR, "labels")

images = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg','.jpeg','.png'))])
random.seed(SEED)
random.shuffle(images)

n_val = max(1, int(len(images) * VAL_SPLIT))
val_set = set(images[:n_val])
train_set = set(images[n_val:])

for split, files in [("train", train_set), ("val", val_set)]:
    os.makedirs(f"{DATASET_DIR}/{split}/images", exist_ok=True)
    os.makedirs(f"{DATASET_DIR}/{split}/labels", exist_ok=True)
    for fname in files:
        shutil.copy(os.path.join(img_dir, fname), f"{DATASET_DIR}/{split}/images/{fname}")
        label = fname.rsplit(".", 1)[0] + ".txt"
        lbl_path = os.path.join(lbl_dir, label)
        if os.path.exists(lbl_path):
            shutil.copy(lbl_path, f"{DATASET_DIR}/{split}/labels/{label}")

print(f"Train: {len(train_set)} | Val: {len(val_set)}")

# Write data.yaml
yaml_content = f"""path: /u/fkm5yp/rustdetection/dataset
train: train/images
val: val/images

nc: 1
names: ['rust']
"""
with open(f"{DATASET_DIR}/data.yaml", "w") as f:
    f.write(yaml_content)

print(f"Dataset ready at '{DATASET_DIR}/'")
print(f"data.yaml written.")
