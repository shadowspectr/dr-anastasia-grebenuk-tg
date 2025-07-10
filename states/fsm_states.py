from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    # Пока не используем, но можно расширить для добавления записей админом
    pass

class ClientStates(StatesGroup):
    # Состояния для пошаговой записи на услугу
    waiting_for_category = State()
    waiting_for_service = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_confirmation = State()