from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    # Новая ветка для создания записи
    waiting_for_client_name = State()
    waiting_for_client_phone = State()
    waiting_for_service = State()
    waiting_for_date = State()
    waiting_for_time = State()

class ClientStates(StatesGroup):
    # Состояния для пошаговой записи на услугу
    waiting_for_category = State()
    waiting_for_service = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_confirmation = State()
    waiting_for_phone = State()

