import logging
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import pytest

from backend.user_interface import UserInterface

TESTING_DB_URL = "sqlite:///testing.db"
TEST_API_URL = "http://localhost:8000/api/hello"
TEST_FRONTEND_URL = "http://localhost:3000/"
NPM_ROOT_DIR = Path(__file__, "../../").resolve()
STARTUP_TIMEOUT = 10

LOG_FILE = "test_server_backend.log"


@contextmanager
def cd(directory):
    owd = os.getcwd()
    try:
        os.chdir(directory)
        yield directory
    finally:
        os.chdir(owd)


@pytest.fixture(scope="session")
def backend_server():
    """
    Launch and finally close a test server, just for the backend
    """

    import subprocess as sp
    import os
    import signal

    with cd(NPM_ROOT_DIR):
        logging.info("Launching backend...")

        f = open(LOG_FILE, "w")
        dev_process = sp.Popen(
            ["npm", "run", "backend"],
            stdout=f,
            stderr=sp.STDOUT,
            preexec_fn=os.setsid,
        )

        wait_until_server_up(TEST_API_URL, STARTUP_TIMEOUT)

    try:
        yield dev_process
    finally:
        try:
            os.killpg(os.getpgid(dev_process.pid), signal.SIGTERM)

            try:
                dev_process.wait(timeout=3)
            except TimeoutError:
                os.killpg(os.getpgid(dev_process.pid), signal.SIGKILL)

            f.close()

            print("Server logs:")
            [print(l.strip()) for l in open(LOG_FILE, "r").readlines()]

        except ProcessLookupError:
            pass


@pytest.fixture(scope="session")
def full_server(backend_server):
    """
    Launch and finally close a test server for the backend and frontend
    """

    import subprocess as sp
    import os
    import signal

    with cd(NPM_ROOT_DIR):
        logging.info("Building site...")

        sp.run(["npm", "run", "build"], stdout=sp.PIPE)

        logging.info("Launching frontend server...")

        dev_process = sp.Popen(
            ["npm", "run", "frontend"],
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            preexec_fn=os.setsid,
        )

        wait_until_server_up(TEST_FRONTEND_URL, STARTUP_TIMEOUT)

    try:
        yield dev_process
    finally:
        os.killpg(os.getpgid(dev_process.pid), signal.SIGTERM)

        try:
            dev_process.wait(timeout=3)
        except TimeoutError:
            os.killpg(os.getpgid(dev_process.pid), signal.SIGKILL)
            dev_process.wait(timeout=3)


def wait_until_server_up(test_url, timeout):
    import requests
    import time

    interval = 0.5
    max_tries = int(timeout / interval)

    for i in range(0, max_tries):
        time.sleep(interval)

        logging.info("Connection attempt %s", i)
        try:
            r = requests.get(test_url)
            if r.is_success:
                logging.info("Server up and running")
                return
        except (ConnectionError, requests.exceptions.RequestException):
            pass

    raise TimeoutError(f"Server did not start in {timeout} seconds")


@pytest.fixture()
def clean_server(full_server):
    """
    Launch a full server if needed, and clean the database
    """
    import backend.database
    from backend.model import Base

    backend.database.load()
    engine = backend.database.engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    return full_server


@pytest.fixture(scope="session")
def engine():
    """Return an engine to the database.

    This fixture should not be used as the database is not cleaned between
    invocations. Use db_session instead.
    """
    if "IGNORE_TESTING_DB" not in os.environ:
        os.environ["DATABASE_URL"] = TESTING_DB_URL

    import backend.database

    backend.database.load()

    return backend.database.engine


@pytest.fixture
def db_session(engine):
    """
    Get an SQLAlchemy database session to a clean database with the model schema
    set up and seed the random number generator.
    """
    from backend.model import Base
    from backend.database import Session
    import random

    random.seed(123)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def api_client(api_client_factory):
    """
    Get a FastAPI TestClient pointing at the app with a clean database session
    """
    return api_client_factory()


@pytest.fixture
def api_client_factory(db_session):
    """
    Get a factory for FastAPI TestClients pointing at the app with a clean database session
    """
    from fastapi.testclient import TestClient
    from backend.main import app

    return lambda: TestClient(app)


@pytest.fixture
def game_factory(db_session):
    from backend.model import Game

    def factory():
        game = Game()

        db_session.add(game)
        db_session.commit()

        return game.id

    return factory


@pytest.fixture
def user_factory(db_session):
    import random

    from backend.model import User

    def factory():
        name = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))
        user = User(name=name)

        db_session.add(user)
        db_session.commit()

        return user.id

    return factory


@pytest.fixture
def team_factory(db_session, one_game):
    import random

    from backend.model import Team

    def factory():
        name = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))
        team = Team(name=name, game_id=one_game)

        db_session.add(team)
        db_session.commit()

        return team.id

    return factory


@pytest.fixture
def three_users(user_factory):
    return [user_factory() for _ in range(3)]


@pytest.fixture
def one_team(team_factory):
    return team_factory()


@pytest.fixture
def one_game(game_factory):
    return game_factory()


@pytest.fixture
def user_in_team(team_factory, user_factory):
    from backend.user_interface import UserInterface

    team_id = team_factory()
    user_id = user_factory()
    UserInterface(user_id).join_team(team_id)

    return user_id


@pytest.fixture
def two_users_in_different_teams(team_factory, user_factory):
    team_a = team_factory()
    team_b = team_factory()

    user_a = user_factory()
    user_b = user_factory()

    UserInterface(user_a).join_team(team_a)
    UserInterface(user_b).join_team(team_b)

    return user_a, user_b


@pytest.fixture
def api_user_id(api_client):
    response = api_client.get("/api/my_id")
    assert response.is_success
    return UUID(response.json())


@pytest.fixture
def test_image_string():
    return Path(__file__, "../sample_base64_image.txt").resolve().read_text()
