import keyboard
import time
import sounddevice as sd
import torch
import json
import os
import numpy as np
from transformers import WhisperProcessor, WhisperForConditionalGeneration
from difflib import SequenceMatcher
from resemblyzer import VoiceEncoder
from simple_logger import SimpleLogger

# -------- SAFE EPICS IMPORT --------
try:
    from epics import caput, caget
    EPICS_AVAILABLE = True
except ImportError:
    EPICS_AVAILABLE = False
# -----------------------------------

MODEL_ID = "openai/whisper-tiny"
SAMPLE_RATE = 16000
DURATION = 5
CONFIG_PATH = "data/command.json"
USER_DB = "data/users.json"
EMB_DIR = "data/embeddings"
KEY = "space"


class CommandEngine:

    def __init__(self, message_callback=None):
        self.message_callback = message_callback
        self.logger = SimpleLogger()

        self.processor = WhisperProcessor.from_pretrained(MODEL_ID)
        self.model = WhisperForConditionalGeneration.from_pretrained(MODEL_ID)
        self.model.eval()

        self.encoder = VoiceEncoder("cpu")

        self.speaker_threshold = 0.65
        self.speaker_margin = 0.04

        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        self.command_threshold = config.get("command_threshold", 0.68)
        self.session_duration = config.get("session_duration", 30)
        self.commands = config.get("commands", [])

        self.log("Command engine initialized.")

    # -------------------------
    # Unified Log (Console + UI)
    # -------------------------
    def log(self, message):
        print(message)
        if self.message_callback:
            self.message_callback(message + "\n")

    # -------------------------
    def cosine_similarity(self, a, b):
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return np.dot(a, b) / denom

    # -------------------------
    def record_audio(self):
        self.log(f"Press '{KEY.upper()}' to start recording...")
        keyboard.wait(KEY)

        self.log("Recording... Speak command.")
        audio = sd.rec(
            int(DURATION * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32"
        )
        sd.wait()

        return audio.flatten()

    # -------------------------
    def transcribe(self, audio):

        inputs = self.processor(
            audio,
            sampling_rate=SAMPLE_RATE,
            return_tensors="pt"
        )

        forced_decoder_ids = self.processor.get_decoder_prompt_ids(
            language="en",
            task="transcribe"
        )

        with torch.no_grad():
            predicted_ids = self.model.generate(
                inputs.input_features,
                forced_decoder_ids=forced_decoder_ids,
                do_sample=False,
                temperature=0.0
            )

        text = self.processor.batch_decode(
            predicted_ids,
            skip_special_tokens=True
        )[0]

        return text.lower().strip()

    # -------------------------
    def start_session(self, authenticated_user):

        self.log(f"Session active for {self.session_duration} seconds.")
        start_time = time.time()

        while True:

            if time.time() - start_time > self.session_duration:
                self.log("Session expired.")
                self.logger.write("SESSION ENDED | TIMEOUT")
                return

            audio = self.record_audio()
            audio = audio / (np.max(np.abs(audio)) + 1e-6)

            input_embedding = self.encoder.embed_utterance(audio)

            with open(USER_DB, "r") as f:
                users = json.load(f)

            scores = []

            for user in users.values():
                emb_path = os.path.join(EMB_DIR, user["voice_emb"])
                if not os.path.exists(emb_path):
                    continue

                stored_embedding = np.load(emb_path)
                score = self.cosine_similarity(input_embedding, stored_embedding)
                scores.append((score, user))

            if not scores:
                self.log("No embeddings found.")
                continue

            scores.sort(key=lambda x: x[0], reverse=True)

            best_score, best_user = scores[0]
            second_score = scores[1][0] if len(scores) > 1 else 0.0

            self.log(f"Similarity: {best_score:.3f}")

            if best_user["name"] != authenticated_user["name"]:
                self.log(f"Unauthorized speaker: {best_user['name']}")
                continue

            if best_score < self.speaker_threshold:
                self.log("Similarity below threshold.")
                continue

            if (best_score - second_score) < self.speaker_margin:
                self.log("Speaker match ambiguous.")
                continue

            command_text = self.transcribe(audio)
            self.log(f"Command recognized: {command_text}")

            if command_text.strip() == "exit":
                self.log("Session ended by voice command.")
                return

            for cmd in self.commands:
                score = SequenceMatcher(None, command_text, cmd["name"]).ratio()

                if score >= self.command_threshold:

                    response = cmd.get("response", "Executing command")
                    self.log(response)

                    epics_info = cmd.get("epics", {})

                    if not epics_info.get("pv"):
                        return

                    if not EPICS_AVAILABLE:
                        self.log(f"(SIMULATION) {epics_info['pv']} -> {epics_info['value']}")
                        return

                    try:
                        initial_pv = caget(epics_info["pv"])
                        caput(epics_info["pv"], epics_info["value"])
                        final_pv = caget(epics_info["pv"])
                        self.log(f"Execution success | {initial_pv} -> {final_pv}")
                    except Exception as e:
                        self.log(f"EPICS ERROR | {str(e)}")

                    return