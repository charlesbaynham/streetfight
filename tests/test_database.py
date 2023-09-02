from uuid import uuid4 as uuid

from backend.model import Game
from backend.model import User


def test_db_init(db_session):
    assert len(db_session.query(Game).all()) == 0
    assert len(db_session.query(User).all()) == 0


def test_storage(db_session):
    id = uuid()
    db_session.add(User(id=id, name="Hello"))
    db_session.commit()

    assert db_session.query(User.name).first()[0] == "Hello"


def test_update(db_session):
    # Add four games
    db_session.add(Game())
    db_session.add(Game())
    db_session.add(Game())

    g = Game()
    db_session.add(g)

    db_session.commit()
    db_session.expire_all()

    # Get the last game from the db
    final_game_id = g.id
    g = db_session.query(Game).filter_by(id=final_game_id).first()
    counter = g.update_tag

    # Touch it
    g.touch()
    db_session.commit()
    db_session.expire_all()

    # Get it again and check that the update_tag changed
    g = db_session.query(Game).filter_by(id=g.id).first()

    assert g.update_tag != counter
