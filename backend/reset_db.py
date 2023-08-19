from .database import engine
from .model import Base


def reset_database():
    target_metadata = Base.metadata
    target_metadata.bind = engine
    target_metadata.drop_all()
    target_metadata.create_all()


if __name__ == "__main__":
    reset_database()
