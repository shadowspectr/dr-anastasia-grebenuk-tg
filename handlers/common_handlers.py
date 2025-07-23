from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from config_reader import config
from keyboards.admin_keyboards import get_admin_main_keyboard
from keyboards.client_keyboards import get_client_main_keyboard
from aiogram import types

router = Router()

@router.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == config.admin_id:
        await message.answer("Добро пожаловать, Администратор!", reply_markup=get_admin_main_keyboard())
    else:
        await message.answer(f"Здравствуйте, {message.from_user.full_name}!\nДобро пожаловать в наш салон.", reply_markup=get_client_main_keyboard())