ROLE_NAMES = {
    "admin": "Администратор",
    "requester": "Инициатор заявки",
    "internal_approver": "Согласующий по внутреннему транспорту",
    "external_approver": "Согласующий по стороннему транспорту",
    "fueler": "Оператор заправки",
    "controller": "Контролёр",
    "ats_operator": "АТС-диспетчер"
}

def get_role_name(role):
    return ROLE_NAMES.get(role, role)
