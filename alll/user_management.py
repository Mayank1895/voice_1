# user_management.py

import os
import json

USER_DB = "data/users.json"
EMB_DIR = "data/embeddings"


class UserManager:

    def load_users(self):
        if not os.path.exists(USER_DB):
            return {}

        with open(USER_DB, "r") as f:
            return json.load(f)

    def save_users(self, users):
        with open(USER_DB, "w") as f:
            json.dump(users, f, indent=4)

    def authorize_user(self, user_id):
        users = self.load_users()

        if user_id not in users:
            return False, "User not found"

        users[user_id]["authorized"] = True
        self.save_users(users)

        return True, f"{users[user_id]['name']} authorized"

    def remove_user(self, user_id):
        users = self.load_users()

        if user_id not in users:
            return False, "User not found"

        emb_file = users[user_id]["voice_emb"]
        emb_path = os.path.join(EMB_DIR, emb_file)

        if os.path.exists(emb_path):
            os.remove(emb_path)

        name = users[user_id]["name"]
        del users[user_id]

        self.save_users(users)

        return True, f"{name} removed"