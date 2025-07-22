from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    # Пока не используем, но можно расширить для добавления записей админом
    pass

# states/fsm_states.py
from aiogram.fsm.state import State, StatesGroup

class ClientStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_service = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_phone = State()
    waiting_for_confirmation = State()

    # Новое состояние для клиента, если мы его введем
    # client_state_new = State() # Пока не нужно, но можно оставить в виду