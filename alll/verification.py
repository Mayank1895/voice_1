# verification.py

import os
import json
import torch
import numpy as np
import sounddevice as sd
import keyboard
import warnings
import logging

from transformers import WhisperProcessor, WhisperForConditionalGeneration
from resemblyzer import VoiceEncoder
from difflib import SequenceMatcher
from simple_logger import SimpleLogger


# -------- SILENCE WARNINGS --------
warnings.filterwarnings("ignore")
logging.getLogger("transformers").setLevel(logging.ERROR)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# ----------------------------------


# -------- CONFIG --------
USER_DB = "data/users.json"
EMB_DIR = "data/embeddings"

MODEL_ID = "openai/whisper-tiny"

SAMPLE_RATE = 16000
DURATION = 5

THRESHOLD = 0.75      # calibrated
MARGIN = 0.04

ACTIVATION_SENTENCE = "start voice assistant"
KEY = "space"

MAX_LOCAL_ATTEMPTS = 1
# ------------------------


# -------- MODEL LOAD --------
processor = WhisperProcessor.from_pretrained(MODEL_ID)
model = WhisperForConditionalGeneration.from_pretrained(MODEL_ID)
model.eval()

encoder = VoiceEncoder("cpu")
logger = SimpleLogger()
# -----------------------------


# -------- AUDIO UTILS --------
def trim_silence(audio, threshold=0.01):
    mask = np.abs(audio) > threshold
    if np.sum(mask) == 0:
        return audio
    start = np.argmax(mask)
    end = len(audio) - np.argmax(mask[::-1])
    return audio[start:end]


def normalize_audio(audio):
    audio = trim_silence(audio)
    max_val = np.max(np.abs(audio)) + 1e-6
    return audio / max_val
# --------------------------------


# -------- SIMILARITY --------
def cosine_similarity(a, b):
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return np.dot(a, b) / denom


def phrase_similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()
# --------------------------------


# -------- RECORD --------
def record_audio():
    print(f'\nSay: "{ACTIVATION_SENTENCE}"')

    audio = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32"
    )
    sd.wait()

    return audio.flatten()


def transcribe(audio):
    try:
        inputs = processor(
            audio,
            sampling_rate=SAMPLE_RATE,
            return_tensors="pt"
        )

        forced_decoder_ids = processor.get_decoder_prompt_ids(
            language="en",
            task="transcribe"
        )

        with torch.no_grad():
            predicted_ids = model.generate(
                inputs.input_features,
                forced_decoder_ids=forced_decoder_ids,
                do_sample=False,
                temperature=0.0
            )

        text = processor.batch_decode(
            predicted_ids,
            skip_special_tokens=True
        )[0]

        return text.lower().strip()

    except Exception:
        return ""
# --------------------------------


# -------- AUTHENTICATION --------
def authenticate_speaker():

    if not os.path.exists(USER_DB):
        print("No users enrolled.")
        return None

    print(f"Press '{KEY.upper()}' to start authentication...")
    keyboard.wait(KEY)

    # 1 attempt per trigger
    for attempt in range(MAX_LOCAL_ATTEMPTS):

        audio = record_audio()
        audio = normalize_audio(audio)

        transcript = transcribe(audio)
        print(f"Recognized text: {transcript}")

        if phrase_similarity(transcript, ACTIVATION_SENTENCE) < 0.75:
            print("Activation phrase mismatch.")
            logger.write("AUTH FAIL | Activation phrase mismatch")
            continue

        try:
            input_embedding = encoder.embed_utterance(audio)
        except Exception as e:
            logger.write(f"EMBED ERROR | {str(e)}")
            continue

        try:
            with open(USER_DB, "r") as f:
                users = json.load(f)
        except Exception:
            print("User database error.")
            return None

        scores = []

        for user in users.values():
            emb_path = os.path.join(EMB_DIR, user["voice_emb"])
            if not os.path.exists(emb_path):
                continue

            try:
                stored_embedding = np.load(emb_path)
                score = cosine_similarity(input_embedding, stored_embedding)
                scores.append((score, user))
            except Exception:
                continue

        if not scores:
            print("No embeddings found.")
            return None

        scores.sort(key=lambda x: x[0], reverse=True)

        best_score, best_user = scores[0]
        second_score = scores[1][0] if len(scores) > 1 else 0.0

        print(f"Best match: {best_user['name']} (score: {best_score:.3f})")

        if best_score < THRESHOLD:
            print("Speaker not recognized.")
            logger.write("AUTH FAIL | Below threshold")
            continue

        if (best_score - second_score) < MARGIN:
            print("Speaker match ambiguous.")
            logger.write("AUTH FAIL | Ambiguous match")
            continue

        if not best_user.get("authorized", False):
            print("User not authorized.")
            logger.write(f"AUTH FAIL | Unauthorized user: {best_user['name']}")
            return None

        logger.write(f"SESSION START | Authorized User: {best_user['name']}")
        print("\nAccess granted.")
        return best_user

    return None