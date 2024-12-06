from dotenv import find_dotenv
from dotenv import load_dotenv


def load_env_vars():
    load_dotenv(find_dotenv(usecwd=True))
