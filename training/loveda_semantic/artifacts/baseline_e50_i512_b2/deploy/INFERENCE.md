# YOLO26n Semantic LoveDA deployment

## PT inference (recommended fallback)
Load `best.pt` with `ultralytics.YOLO`, call `predict(source, imgsz=512)`, and read `result.semantic_mask.data`. Resize with nearest-neighbor to the original image when needed. Collapse internal label 7 to public background (0). Public labels are documented in `metadata.json`; 255 is ground-truth ignore only.

## ONNX inference
Input is RGB float32 NCHW scaled to [0,1], nominally 512x512. Run the ONNX output logits, take argmax over channel axis, collapse label 7 to 0, and nearest-neighbor resize to source dimensions. Consult `export_status.json` before using ONNX.
