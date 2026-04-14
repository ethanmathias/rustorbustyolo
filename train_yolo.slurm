#!/bin/bash
#SBATCH --job-name=yolo_rust
#SBATCH --output=/u/fkm5yp/rustdetection/yolo_%j.log
#SBATCH --error=/u/fkm5yp/rustdetection/yolo_%j.err
#SBATCH -p gpu
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH -t 4:00:00
#SBATCH --gres=gpu:1

echo "=== YOLOv8-seg Training: $(date) ==="
nvidia-smi
module load gcc
cd /u/fkm5yp/rustdetection

pip uninstall torch torchvision -y --quiet 2>/dev/null
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 --quiet 2>&1 | tail -1
pip install ultralytics --quiet 2>&1 | tail -1

python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"NONE\"}')"

python3 -u train_yolo.py

# Save best model with image count label
N=$(ls labeled/images/ | wc -l | tr -d ' ')
cp runs/rust_seg/weights/best.pt models/${N}images.pt
echo "=== Saved models/${N}images.pt ==="
echo "=== Done: $(date) ==="
