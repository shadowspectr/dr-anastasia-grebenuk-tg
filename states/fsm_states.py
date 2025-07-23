from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_client_name = State()  # Начальное состояние: ввод имени клиента
    waiting_for_category = State()  # Затем, как у клиента
    waiting_for_service = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_phone = State()
    waiting_for_confirmation = State()

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