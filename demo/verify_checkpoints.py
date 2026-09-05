import torch

for name, path in [("classifier", "checkpoints/classifier_best.pt"),
                    ("segmenter", "checkpoints/unet_wholescene_best.pt")]:
    ckpt = torch.load(path, map_location="cpu")
    print(f"{name}: OK, keys={list(ckpt.keys())}")
