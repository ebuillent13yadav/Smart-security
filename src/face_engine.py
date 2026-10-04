"""
face_engine.py
--------------
Face detection and recognition engine powered by InsightFace (ArcFace + RetinaFace).

Pipeline per frame
──────────────────
  1. Detect all faces via InsightFace's bundled RetinaFace detector.
  2. For each detected face, extract a 512-d ArcFace embedding.
  3. L2-normalise the embedding (already done by InsightFace, but we guard it).
  4. Compute cosine similarity against every registered embedding.
  5. The best-matching identity whose similarity ≥ RECOGNITION_THRESHOLD
     is returned as the recognised person; otherwise → UNKNOWN.
"""

import os
import pickle
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import (
    KNOWN_FACES_DIR,
    EMBEDDINGS_CACHE,
    INSIGHTFACE_ROOT,
    MODELS_DIR,
    INSIGHTFACE_MODEL_PACK,
    ONNX_PROVIDERS,
    DETECTION_THRESHOLD,
    RECOGNITION_THRESHOLD,
    SUPPORTED_EXTENSIONS,
)


# ─────────────────────────────────────────────────────────────
# Helper: cosine similarity
# ─────────────────────────────────────────────────────────────

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two 1-D vectors.

    sim(u, v) = (u · v) / (‖u‖ · ‖v‖)

    InsightFace embeddings are already L2-normalised, so this reduces
    to a simple dot product — but we keep the full formula for safety.
    """
    a = a / (np.linalg.norm(a) + 1e-8)
    b = b / (np.linalg.norm(b) + 1e-8)
    return float(np.dot(a, b))


# ─────────────────────────────────────────────────────────────
# FaceEngine class
# ─────────────────────────────────────────────────────────────

class FaceEngine:
    """
    Wraps InsightFace model loading, face gallery management,
    and per-frame recognition inference.
    """

    def __init__(self):
        self._app = None            # InsightFace FaceAnalysis object
        # Gallery: {name: embedding_vector (512-d np.ndarray)}
        self._gallery: dict[str, np.ndarray] = {}

        self._load_model()
        self._load_or_build_gallery()

    # ── Model Loading ─────────────────────────────────────────

    def _load_model(self):
        """Download (first run) and initialise the InsightFace model pack."""
        try:
            import insightface
            from insightface.app import FaceAnalysis
        except ImportError:
            print("[ERROR] insightface is not installed. Run: pip install insightface")
            sys.exit(1)

        os.makedirs(MODELS_DIR, exist_ok=True)

        # Filter to only providers that onnxruntime actually supports on this machine.
        # This silences the "CUDAExecutionProvider not available" warning when no GPU.
        import onnxruntime as ort
        available = ort.get_available_providers()
        providers = [p for p in ONNX_PROVIDERS if p in available]
        if not providers:
            providers = ["CPUExecutionProvider"]

        print(f"[INFO] Loading InsightFace model pack: '{INSIGHTFACE_MODEL_PACK}' …")
        print(f"[INFO] Using ONNX providers: {providers}")
        self._app = FaceAnalysis(
            name=INSIGHTFACE_MODEL_PACK,
            root=INSIGHTFACE_ROOT,    # InsightFace stores at root/models/<pack>
            providers=providers,
        )
        # ctx_id=0 → use GPU if available; -1 → force CPU
        ctx = 0 if any("CUDA" in p for p in providers) else -1
        self._app.prepare(ctx_id=ctx, det_thresh=DETECTION_THRESHOLD, det_size=(640, 640))
        print("[INFO] Model loaded successfully.")

    # ── Gallery Management ────────────────────────────────────

    def _load_or_build_gallery(self):
        """
        Load the embedding cache from disk if it exists and is up-to-date,
        otherwise rebuild it from images in KNOWN_FACES_DIR.
        """
        cache_valid = self._is_cache_valid()

        if cache_valid:
            print(f"[INFO] Loading embeddings from cache: {EMBEDDINGS_CACHE}")
            with open(EMBEDDINGS_CACHE, "rb") as f:
                self._gallery = pickle.load(f)
            print(f"[INFO] Gallery loaded — {len(self._gallery)} identit(ies): "
                  f"{list(self._gallery.keys())}")
        else:
            self._build_gallery()

    def _is_cache_valid(self) -> bool:
        """
        Cache is considered valid if it exists AND is newer than all images
        in the known_faces directory (no new images added since last build).
        """
        if not os.path.exists(EMBEDDINGS_CACHE):
            return False

        cache_mtime = os.path.getmtime(EMBEDDINGS_CACHE)
        known_dir = Path(KNOWN_FACES_DIR)

        for img_path in known_dir.iterdir():
            if img_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                if img_path.stat().st_mtime > cache_mtime:
                    return False  # a newer image exists — rebuild

        # Also invalidate if gallery is empty but dir has images
        with open(EMBEDDINGS_CACHE, "rb") as f:
            cached_gallery = pickle.load(f)
        images_present = any(
            p.suffix.lower() in SUPPORTED_EXTENSIONS
            for p in known_dir.iterdir()
        )
        if images_present and not cached_gallery:
            return False

        return True

    def _build_gallery(self):
        """
        Scan KNOWN_FACES_DIR, extract an ArcFace embedding for each image,
        and persist the gallery to the cache pickle file.
        """
        print(f"[INFO] Building face gallery from: {KNOWN_FACES_DIR}")
        os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

        gallery: dict[str, np.ndarray] = {}
        known_dir = Path(KNOWN_FACES_DIR)
        image_files = [
            p for p in known_dir.iterdir()
            if p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        if not image_files:
            print("[WARNING] No images found in data/known_faces/. "
                  "The system will treat everyone as UNKNOWN until faces are registered.")

        for img_path in image_files:
            name = img_path.stem  # filename without extension = identity name
            embedding = self._extract_embedding_from_file(str(img_path))
            if embedding is not None:
                gallery[name] = embedding
                print(f"  ✔  Registered: {name}")
            else:
                print(f"  ✘  Skipped (no face detected): {img_path.name}")

        self._gallery = gallery
        self._save_cache()

        if gallery:
            print(f"[INFO] Gallery built — {len(gallery)} identit(ies): {list(gallery.keys())}")
        else:
            print("[INFO] Gallery is empty — no valid faces registered.")

    def _extract_embedding_from_file(self, image_path: str) -> Optional[np.ndarray]:
        """
        Load an image from disk, detect faces, and return the ArcFace embedding
        of the *first* (largest) detected face.

        Returns None if no face is detected or the image cannot be read.
        """
        img = cv2.imread(image_path)
        if img is None:
            print(f"[ERROR] Cannot read image: {image_path}")
            return None

        faces = self._app.get(img)
        if not faces:
            return None

        # If multiple faces, warn and use the largest one (by bounding-box area)
        if len(faces) > 1:
            print(f"[WARNING] {os.path.basename(image_path)} contains {len(faces)} faces. "
                  "Using the largest detected face.")
            faces = sorted(
                faces,
                key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
                reverse=True,
            )

        return faces[0].embedding  # 512-d np.ndarray

    def _save_cache(self):
        """Persist the current gallery dict to the embeddings cache file."""
        os.makedirs(os.path.dirname(EMBEDDINGS_CACHE), exist_ok=True)
        with open(EMBEDDINGS_CACHE, "wb") as f:
            pickle.dump(self._gallery, f)
        print(f"[INFO] Embeddings cached to: {EMBEDDINGS_CACHE}")

    # ── Registration Helpers ──────────────────────────────────

    def register_from_file(self, image_path: str, name: str) -> bool:
        """
        Register a new identity from an image file.
        Copies nothing — just extracts the embedding, updates the gallery,
        and saves the image to KNOWN_FACES_DIR.
        Returns True on success, False on failure.
        """
        ext = Path(image_path).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            print(f"[ERROR] Unsupported image format: {ext}")
            return False

        embedding = self._extract_embedding_from_file(image_path)
        if embedding is None:
            print(f"[ERROR] No face detected in '{image_path}'. Registration aborted.")
            return False

        # Copy the image to known_faces with the chosen name
        import shutil
        dest = os.path.join(KNOWN_FACES_DIR, f"{name}{ext}")
        shutil.copy2(image_path, dest)

        self._gallery[name] = embedding
        self._save_cache()
        print(f"[INFO] '{name}' registered successfully.")
        return True

    def register_from_frame(self, frame: np.ndarray, name: str) -> bool:
        """
        Register a new identity directly from a webcam frame (BGR numpy array).
        Returns True on success.
        """
        faces = self._app.get(frame)
        if not faces:
            print("[ERROR] No face detected in the captured frame.")
            return False

        embedding = faces[0].embedding

        # Save the frame as a reference image
        dest = os.path.join(KNOWN_FACES_DIR, f"{name}.jpg")
        cv2.imwrite(dest, frame)

        self._gallery[name] = embedding
        self._save_cache()
        print(f"[INFO] '{name}' registered from webcam frame.")
        return True

    def reload_gallery(self):
        """Force a rebuild of the face gallery from disk (e.g. after adding images)."""
        print("[INFO] Reloading gallery from disk …")
        self._build_gallery()

    # ── Per-Frame Inference ───────────────────────────────────

    def process_frame(self, frame: np.ndarray) -> list[dict]:
        """
        Run face detection + recognition on a single BGR frame.

        Returns a list of result dicts — one per detected face:
        {
            "bbox":       (x1, y1, x2, y2),    # ints
            "name":       str,                  # identity name or "UNKNOWN"
            "status":     "AUTHORIZED" | "DENIED",
            "similarity": float,                # best cosine similarity found
            "det_score":  float,                # detection confidence
        }
        """
        faces = self._app.get(frame)
        results = []

        for face in faces:
            # ── Embedding ──────────────────────────────────────
            probe_emb = face.embedding   # 512-d, already L2-normalised by InsightFace

            # ── Gallery Matching ───────────────────────────────
            best_name  = "UNKNOWN"
            best_score = -1.0

            for name, gallery_emb in self._gallery.items():
                score = cosine_similarity(probe_emb, gallery_emb)
                if score > best_score:
                    best_score = score
                    best_name  = name

            # ── Decision ───────────────────────────────────────
            if best_score >= RECOGNITION_THRESHOLD:
                identity = best_name
                status   = "AUTHORIZED"
            else:
                identity = "UNKNOWN"
                status   = "DENIED"

            # ── Bounding Box ───────────────────────────────────
            x1, y1, x2, y2 = [int(v) for v in face.bbox]

            results.append({
                "bbox":       (x1, y1, x2, y2),
                "name":       identity,
                "status":     status,
                "similarity": round(best_score, 4),
                "det_score":  round(float(face.det_score), 4),
            })

        return results
