import sounddevice as sd
import numpy as np
import os
import json
from resemblyzer import VoiceEncoder

USER_DB = "data/users.json"
EMB_DIR = "data/embeddings"
SAMPLE_RATE = 16000
DURATION = 5

ENROLLMENT_PHRASES = [
    "start voice assistant",
    "master off",
    "shutdown",
    "insert faraday cup"
]

os.makedirs(EMB_DIR, exist_ok=True)
os.makedirs(os.path.dirname(USER_DB), exist_ok=True)

encoder = VoiceEncoder("cpu")


def normalize_audio(audio):
    max_val = np.max(np.abs(audio)) + 1e-6
    return audio / max_val


def record_audio(prompt):
    print(f"\nRecording for {DURATION} seconds...")
    print(f'Say clearly: "{prompt}"\n')

    audio = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32"
    )
    sd.wait()

    return audio.flatten()


def safe_load_users():
    if not os.path.exists(USER_DB):
        return {}

    try:
        with open(USER_DB, "r") as f:
            return json.load(f)
    except:
        return {}


def get_next_user(users: dict) -> str:
    if not users:
        return "1"
    return str(max(map(int, users.keys())) + 1)


def enroll(name, logger=print):

    logger(f"Starting enrollment for: {name}")

    if not name:
        logger("ERROR: Name is empty.")
        return

    embeddings = []

    logger(f"Embedding directory: {EMB_DIR}")
    logger(f"Does directory exist? {os.path.exists(EMB_DIR)}")

    try:
        for phrase in ENROLLMENT_PHRASES:

            logger(f"\nRecording phrase: {phrase}")

            audio = sd.rec(
                int(DURATION * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32"
            )
            sd.wait()

            audio = audio.flatten()
            audio = normalize_audio(audio)

            logger("Generating embedding...")
            emb = encoder.embed_utterance(audio)

            logger("Embedding generated successfully.")
            embeddings.append(emb)

    except Exception as e:
        logger(f"ERROR during recording/embedding: {str(e)}")
        return

    if not embeddings:
        logger("ERROR: No embeddings collected.")
        return

    try:
        avg_embedding = np.mean(embeddings, axis=0)

        embedding_filename = f"{name}.npy"
        full_path = os.path.join(EMB_DIR, embedding_filename)

        logger(f"Saving embedding to: {full_path}")

        np.save(full_path, avg_embedding)

        logger("Embedding file saved successfully.")

    except Exception as e:
        logger(f"ERROR during saving embedding: {str(e)}")
        return

    try:
        users = safe_load_users()
        user_id = get_next_user(users)

        users[user_id] = {
            "name": name,
            "voice_emb": embedding_filename,
            "role": "approved",
            "authorized": True
        }

        with open(USER_DB, "w") as f:
            json.dump(users, f, indent=4)

        logger("User database updated successfully.")

    except Exception as e:
        logger(f"ERROR updating users.json: {str(e)}")
        return

    logger("Enrollment completed successfully.")

if __name__ == "__main__":
    name = input("Enter your name: ").strip().lower()
    enroll(name)