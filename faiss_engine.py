import os
import faiss
import numpy as np
from deepface import DeepFace

class FaissBiometricEngine:
    """
    High-Performance Biometric matching using DeepFace and FAISS
    O(1) vector nearest-neighbor search for instantaneous Edge verification.
    """
    def __init__(self, model_name="Facenet"):
        self.model_name = model_name
        self.embedding_dim = 128  # Facenet outputs 128-d vectors
        self.index = faiss.IndexFlatL2(self.embedding_dim)
        self.user_mapping = {}

    def extract_vector(self, image_source):
        """Extracts deep features from image path or Base64."""
        try:
            # enforce_detection=True combined with alignment guarantees the vector is isolated entirely to facial geometry (not the background room).
            res = DeepFace.represent(img_path=image_source, model_name=self.model_name, enforce_detection=True, align=True)
            if res and len(res) > 0:
                vec = np.array(res[0]['embedding'], dtype='float32')
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                return vec
        except ValueError:
            # Expected behavior if no confident face crops were found in this frame.
            return None
        except Exception as e:
            print(f"[FAISS] DeepFace Extraction Error: {e}")
        return None

    def build_index(self, users):
        """Initializes the FAISS L2 index with known users."""
        self.index.reset()
        self.user_mapping.clear()
        
        vector_list = []
        
        current_idx = 0
        for user in users:
            # We assume user object has a Face_encoding property that stores the filename path
            if user.Face_encoding and os.path.exists(user.Face_encoding):
                print(f"[FAISS] Bootstrapping Identity: {user.name}")
                vec = self.extract_vector(user.Face_encoding)
                if vec is not None:
                    vector_list.append(vec)
                    self.user_mapping[current_idx] = user
                    current_idx += 1
        
        if vector_list:
            vectors_np = np.array(vector_list).astype('float32')
            self.index.add(vectors_np)
            print(f"✅ [FAISS] Successfully built biometric index with {self.index.ntotal} authorized identities.")
            return True
            
        print("⚠️ [FAISS] Warning: No biometric profiles found to index.")
        return False

    def verify_subject(self, camera_frame_source, threshold=0.75):
        """Returns User Object if matched, else None. 0.75 is the relaxed squared L2 threshold for normalized FaceNet."""
        if self.index.ntotal == 0:
            return None, "System not enrolled - Index is empty."

        vec = self.extract_vector(camera_frame_source)
        if vec is None:
            return None, "No Face Detected in Frame."

        query_vec = np.array([vec]).astype('float32')
        # Search for 1 nearest neighbor
        distances, indices = self.index.search(query_vec, 1)

        closest_distance = distances[0][0]
        closest_id = indices[0][0]

        print(f"[FAISS Search] Closest match distance: {closest_distance} (Threshold: {threshold})")

        # In L2, lower distance = more similar
        if closest_distance < threshold and closest_id in self.user_mapping:
            matched_user = self.user_mapping[closest_id]
            return matched_user, f"Verified (Distance: {closest_distance:.2f})"
        
        return None, "Access Denied (Face Unknown)"
