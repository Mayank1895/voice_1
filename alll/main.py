# main.py

from verification import authenticate_speaker
from command import CommandEngine
from simple_logger import SimpleLogger

MAX_ATTEMPTS = 5


def main():
    logger = SimpleLogger()

    print("\n===== VOICE CONTROL SYSTEM STARTED =====\n")
    logger.write("SYSTEM STARTED")

    attempts = 0
    user = None

    # -------------------------------
    # AUTHENTICATION LOOP
    # -------------------------------
    while attempts < MAX_ATTEMPTS:
        try:
            user = authenticate_speaker()

            if user is not None:
                break

            attempts += 1
            print(f"Authentication failed ({attempts}/{MAX_ATTEMPTS})\n")
            logger.write(f"AUTHENTICATION FAILED | Attempt {attempts}")

        except Exception as e:
            logger.write(f"AUTHENTICATION ERROR | {str(e)}")
            print("Unexpected authentication error.")
            attempts += 1

    if user is None:
        print("Maximum attempts reached. System locked.")
        logger.write("SYSTEM LOCKED | Max authentication attempts reached")
        return

    # -------------------------------
    # START COMMAND SESSION
    # -------------------------------
    try:
        engine = CommandEngine()
        engine.start_session(user)

    except Exception as e:
        print("SESSION ERROR:", e)
        raise

    print("\n===== SYSTEM STOPPED =====\n")
    logger.write("SYSTEM STOPPED")


if __name__ == "__main__":
    main()