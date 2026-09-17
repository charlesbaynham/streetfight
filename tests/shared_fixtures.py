import logging
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID
from uuid import uuid4 as get_uuid

import pytest

from backend.admin_interface import AdminInterface
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

    import os
    import signal
    import subprocess as sp

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

    import os
    import signal
    import subprocess as sp

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
    import time

    import requests

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
    import random

    from backend.database import Session
    from backend.model import Base

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
def admin_api_client(api_client):
    """
    Get a FastAPI TestClient pointing at the app with a clean database session
    and admin rights
    """
    password = os.getenv("ADMIN_PASSWORD", "password")
    api_client.post(f"/api/admin_authenticate?password={password}")
    return api_client


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

    def factory():
        user_id = get_uuid()
        ui = UserInterface(user_id=user_id)
        user = ui.get_user()

        db_session.add(user)
        db_session.commit()

        name = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))
        ui.set_name(name)

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
    team_id = team_factory()
    user_id = user_factory()

    with UserInterface(user_id) as ui:
        ui.join_team(team_id)

    return user_id


@pytest.fixture
def two_users_in_different_teams(team_factory, user_factory):
    team_a = team_factory()
    team_b = team_factory()

    user_a = user_factory()
    user_b = user_factory()

    with UserInterface(user_a) as ui:
        ui.join_team(team_a)
    with UserInterface(user_b) as ui:
        ui.join_team(team_b)

    return user_a, user_b


@pytest.fixture
def api_user_id(api_client):
    response = api_client.get("/api/my_id")
    assert response.is_success
    return UUID(response.json())


@pytest.fixture
def test_image_string():
    return Path(__file__, "../sample_base64_image.txt").resolve().read_text()


# A player with no armour on: the next hit kills them. Since M1.2 a real
# player starts on model.STARTING_HIT_POINTS (2) -- "starting armour 1", since
# armour is hit points above one -- but a test about knockout cascades, kill
# announcements, invalidated shots or medpacks is about what happens when hit
# points reach zero, and should say what it needs rather than inherit it from
# the balance of the day. STARTING_HIT_POINTS has its own tests.
UNARMOURED_HIT_POINTS = 1


def strip_armour(*user_ids):
    """Take players down to UNARMOURED_HIT_POINTS, so one hit kills.

    Goes through UserInterface.set_HP rather than AdminInterface.set_user_HP,
    which would send a ticker message and disturb the tests that count them.
    """
    for user_id in user_ids:
        UserInterface(user_id).set_HP(UNARMOURED_HIT_POINTS)


# A weapon that can be fired again immediately. The server-side cooldown
# (M1.1) refuses a second shot inside the player's own shot_timeout, which is
# the whole point of it -- but a test about queue ordering, backlogs or
# adjudication is about what happens to a shot *after* it lands, and should
# not have to wait 25 s to queue a second one. The cooldown has its own tests
# in tests/test_shots.py.
NO_FIRE_DELAY = 0


@pytest.fixture
def shot_from_user_in_team(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    ui.set_weapon_data(1, NO_FIRE_DELAY)
    ui.submit_shot(test_image_string)

    return AdminInterface().get_shots_ids()[0]
