from uuid import UUID

from .database_scope_provider import DatabaseScopeProvider

TickerScopeWrapper = DatabaseScopeProvider(
    "ticker",
    precommit_method=touch_user,
    postcommit_method=lambda user_interface: trigger_update_event(
        user_interface.user_id
    ),
)


db_scoped = UserScopeWrapper.db_scoped


class Ticker:
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id

    def get_message(self, n_entries):
        pass
