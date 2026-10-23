from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    waiting_for_discount_code = State()


class DepositStates(StatesGroup):
    waiting_for_custom_amount = State()


class TicketStates(StatesGroup):
    waiting_for_subject = State()
    waiting_for_message = State()
