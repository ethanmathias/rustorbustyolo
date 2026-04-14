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

PYTHON=/sw/ubuntu2204/ebu082025/software/common/compiler/gcc/11.4.0/python/3.12.3/bin/python

echo "=== YOLOv8-seg Training: $(date) ==="
nvidia-smi
cd /u/fkm5yp/rustdetection

$PYTHON -c "import torch; print(torch.cuda.is_available(), torch.__version__)"

$PYTHON -u train_yolo.py

LATEST=$(ls -td runs/rust_seg*/weights/best.pt 2>/dev/null | head -1)
N=$(ls labeled/images/ | wc -l | tr -d ' ')
mkdir -p models
if [ -f "$LATEST" ] && [ $(stat -c%s "$LATEST") -gt 1000000 ]; then
    cp "$LATEST" models/${N}images.pt
    echo "=== Saved models/${N}images.pt ==="
else
    echo "ERROR: Model file missing or too small: $LATEST"
fi
echo "=== Done: $(date) ==="
