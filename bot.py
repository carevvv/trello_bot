import telebot
from telebot import types
from configuration.config import TG_TOKEN
from model import *
import threading
import datetime
import pytz
import json
import time
from trello import trello_wrapper
from datetime import datetime, timedelta
from flask import Flask, request, abort
from configuration.config import API_KEY, TOKEN, board_id, ADMIN


app = Flask(__name__)
bot = telebot.TeleBot(TG_TOKEN)

bot_messages = {}



def is_valid_telegram_id(tg_id):
    try:
        chat = bot.get_chat(tg_id)
        return True
    except telebot.apihelper.ApiException as e:
        send_telegram_message(ADMIN, f'Произошла ошибка при обработке попытке добавить метку: {e}')
        return False 


def dicts_equal(d1, d2):
    d1_as_strings = {json.dumps(item, sort_keys=True) for item in d1}
    d2_as_strings = {json.dumps(item, sort_keys=True) for item in d2}
    return d1_as_strings == d2_as_strings

def send_reminders_about_project_deadlines(projects):
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz).replace(tzinfo=None)
  
    reminders = [
        {'delta': timedelta(weeks=1), 'message': "осталась неделя"},
        {'delta': timedelta(days=3), 'message': "осталось 3 дня"},
        {'delta': timedelta(days=2), 'message': "осталось 2 дня"},
        {'delta': timedelta(days=1), 'message': "остался 1 день"},
        {'delta': timedelta(hours=6), 'message': "осталось 6 часов"},
        {'delta': timedelta(hours=2), 'message': "осталось 2 часа"}
    ]
    for user_id, projs in projects.items():
        for title, project in projs.items():
            deadline_str = project.get('deadline')
            if deadline_str:
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=moscow_tz)
                for reminder in reminders:
                    reminder_time = (deadline - reminder['delta']).replace(tzinfo=None)
                    if now_moscow >= reminder_time and now_moscow < reminder_time + timedelta(minutes=5):
                        notify = Notifications.get_or_none(
                            (Notifications.tg_id == user_id) &
                            (Notifications.title == title) &
                            (Notifications.reminder_message == reminder['message'])
                        )

                        if not notify:
                            message = f"<b>{title}</b> - {reminder['message']}. Необходимо подготовиться к завершению!"
                            send_telegram_message(user_id, message, parse_mode='HTML')
                            Notifications.create(
                                tg_id=user_id,
                                title=title,
                                reminder_message=reminder['message'],
                                notification=False,
                                last_notification_time=now_moscow
                            )

 
def check_overdue_projects(projects):
    moscow_tz = pytz.timezone('Europe/Moscow')
    notification_interval = timedelta(hours=4)
    for user_id, projs in projects.items():
        user_id = str(user_id).strip()
        for title, project in projs.items():
            deadline_str = project.get('deadline')
            if deadline_str:
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M:%S')
                now_moscow = datetime.now(moscow_tz).replace(tzinfo=None)

                if deadline < now_moscow:
                    notify = Notifications.get_or_none((Notifications.tg_id == user_id) & (Notifications.title == title))
                    should_notify = False
                    if notify:
                        if notify.notification:
                            if notify.last_notification_time + notification_interval <= now_moscow:
                                should_notify = True
                        else:
                            should_notify = True
                    if should_notify:
                        message = f"Проект <b>{title}</b> просрочен. Необходимо срочно завершить!"
                        send_telegram_message(user_id, message, parse_mode='HTML')
                        notify.notification = True
                        notify.last_notification_time = now_moscow
                        notify.save()



def send_telegram_message(user_id, message, parse_mode='HTML'):
    try:
        bot.send_message(chat_id=user_id, text=message, parse_mode=parse_mode)
    except Exception as e:
        send_telegram_message(ADMIN, f'Пользователь заблокировал бота: {e}')


def create_project_dict(projects):
    project_dict = {}
    for project in projects:
        if project['tg_id'] not in project_dict:
            project_dict[project['tg_id']] = {}
        project_dict[project['tg_id']][project['title']] = project
    return project_dict


def check_for_updates(old_board_info, new_board_info):

    old_proj_dict = create_project_dict(old_board_info)
    new_proj_dict = create_project_dict(new_board_info)
    try:
        for user_id, new_projs in new_proj_dict.items():
            old_projs = old_proj_dict.get(user_id, {})
            for title, new_proj in new_projs.items():
                if old_projs:
                    old_proj = old_projs.get(title, {})
                else:
                    old_proj = {}
                if not old_proj:
                    if new_proj['status'] == 'В работе' and new_proj['deadline']:
                        add_notification(user_id, title)
                    if new_proj['status'] != 'завершен':
                        message = f"<b>Новый проект назначен: {new_proj['title']}</b>"
                        send_telegram_message(user_id, message, parse_mode='HTML')
                else:
                    new_deadline = datetime.strptime(new_proj['deadline'], '%Y-%m-%d %H:%M:%S') if new_proj['deadline'] else None
                    old_deadline = datetime.strptime(old_proj['deadline'], '%Y-%m-%d %H:%M:%S') if old_proj.get('deadline') else None
                    del_deadline = False
                    add_deadline = False

                    if old_proj['status'] != new_proj['status']:
                        status = new_proj['status']
                        if status == 'review':
                            del_deadline = True
                            message = f"Статус проекта <b>{title}</b> изменен на {new_proj['status']}."
                        elif status == 'завершен':
                            del_deadline = True
                            message = f"Статус проекта <b>{title}</b> изменен на {new_proj['status']}."
                        elif status == 'В работе':
                            add_deadline = True
                            message = f"Статус проекта <b>{title}</b> изменен на {new_proj['status']}."
                        else:
                            del_deadline = True
                            message = f"Статус проекта <b>{title}</b> изменен на {new_proj['status']}."
                        send_telegram_message(user_id, message, parse_mode='HTML')

                    if new_deadline != old_deadline:
                        if new_deadline:
                            message = f"Срок выполнения проекта <b>{title}</b> изменен на {new_deadline.strftime('%d %b %Y %H:%M')}."
                            send_telegram_message(user_id, message, parse_mode='HTML')
                        if not old_deadline:
                            add_deadline = True
                        elif new_deadline:
                            notify = Notifications.get_or_none((Notifications.tg_id == user_id) & (Notifications.title == title))
                            if notify:
                                notify.notification = False
                                notify.save()
                        else:
                            del_deadline = True
                            message = f"Срок выполнения проекта <b>{title}</b> сброшен."
                            send_telegram_message(user_id, message, parse_mode='HTML')

                    if del_deadline:
                        notify = Notifications.get_or_none((Notifications.tg_id == user_id) & (Notifications.title == title))
                        if notify:
                            notify.delete_instance()

                    if add_deadline and not del_deadline:
                        add_notification(user_id, title)
                    
                    old_comments = set(tuple(comment) for comment in old_proj.get('comments') or [])
                    new_comments = set(tuple(comment) for comment in new_proj.get('comments') or [])
                    added_comments = new_comments - old_comments
                    if added_comments:
                        message = f"Новые комментарии в проекте <b>{title}</b>:\n\n" + "<br>".join(f'{comment[0]}({comment[2]}): {comment[1]}' for comment in added_comments)
                        send_telegram_message(user_id, message, parse_mode='HTML')

                    if old_proj.get('description') != new_proj.get('description'):
                        message = f"Изменено описание проекта <b>{title}</b>:\n\n{new_proj['description']}"
                        send_telegram_message(user_id, message, parse_mode='HTML')
    except Exception as e:
        send_telegram_message(ADMIN, f'Произошла ошибка при обновлении проектов: {e}')


def remove_old_notifications(old_projects, new_projects):
    old_ids = set(project['tg_id'] for project in old_projects)
    new_ids = set(project['tg_id'] for project in new_projects)

    ids_to_remove = old_ids - new_ids

    if ids_to_remove:
        query = Notifications.delete().where(Notifications.tg_id.in_(ids_to_remove))
        query.execute()
        

def remove_trush(projects):
    valid_projects = [project for project in projects if is_valid_telegram_id(project['tg_id'])]
    return valid_projects


                
def perform_regular_task():
    while True:
        trello = trello_wrapper(API_KEY, TOKEN)
        board_info = remove_trush(trello.get_full_board_info(board_id))
        old_board_info = get_all_projects_records()
        statuses = trello.get_trello_board_lists()
        update_statuses(statuses) 
        if not dicts_equal(board_info, old_board_info):
            check_for_updates(old_board_info, board_info)
            remove_old_notifications(old_board_info, board_info)
            update_projects(board_info)

        new_proj_dict = create_project_dict(board_info)  
        check_overdue_projects(new_proj_dict)
        send_reminders_about_project_deadlines(new_proj_dict)
        time.sleep(1)

def start_thread():
    task_thread = threading.Thread(target=perform_regular_task)
    task_thread.daemon = True
    task_thread.start()


@bot.message_handler(commands=['start'])
def handle_start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton('/projects')
    markup.add(item1)
    bot.send_message(message.chat.id, "Введите /projects, чтобы увидеть список проектов.", reply_markup=markup)



def store_bot_message(chat_id, message_id):
    if chat_id not in bot_messages:
        bot_messages[chat_id] = []
    bot_messages[chat_id].append(message_id)


def delete_messages(chat_id):
    try:
        if chat_id in bot_messages:
            for msg_id in bot_messages[chat_id]:
                try:
                    bot.delete_message(chat_id, msg_id)
                except Exception as e:
                    send_telegram_message(ADMIN, f'Произошла ошибка при удалении сообщений: {e}')
            del bot_messages[chat_id]
    except Exception as e:
        send_telegram_message(ADMIN, f'Произошла ошибка при удалении сообщений: {e}')

@bot.message_handler(commands=['projects'])
def handle_projects(message):
    chat_id = message.chat.id
    tg_id = str(chat_id)
    
    try:
        projects = Projects.select().where(Projects.tg_id == tg_id)
        if projects.count() == 0:
            reply = bot.send_message(chat_id, "У вас нет проектов.")
            store_bot_message(chat_id, reply.message_id)
            return
            
        for project in projects:
            project_info = (
                f"<b>Проект:</b> {project.title}\n"
                f"<b>Статус:</b> {project.status}\n"
                f"<b>Дедлайн:</b> {project.deadline.strftime('%Y-%m-%d %H:%M') if project.deadline else 'не установлен'}\n"
            )
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("Изменить статус", callback_data=f"change_status_{project.id}"))
            markup.row(types.InlineKeyboardButton("Посмотреть описание", callback_data=f"description_{project.id}"))
            markup.row(types.InlineKeyboardButton("Посмотреть комментарии", callback_data=f"comments_{project.id}"))
            reply = bot.send_message(chat_id, project_info, reply_markup=markup, parse_mode='HTML')
            store_bot_message(chat_id, reply.message_id)

    except ValueError as e:
        send_telegram_message(ADMIN, f'Произошла ошибка при обработке команды /projects: {e}')


@bot.callback_query_handler(func=lambda query: query.data.startswith('change_status_'))
def change_status(query):
    project_id = query.data.split('_')[2]
    chat_id = query.message.chat.id

    try:
        project = Projects.get(id=project_id)
        available_statuses = [status.status_name for status in ProjectStatus if status.status_name != project.status]
        delete_messages(chat_id)

        markup = types.InlineKeyboardMarkup()
        for status in available_statuses:
            callback_data = f"update_status_{project_id}_{status}"
            markup.add(types.InlineKeyboardButton(text=status, callback_data=callback_data))

        response = f"Ваш текущий статус - <b><u>{project.status}</u></b>.\n\nВы можете поменять на:"
        msg = bot.send_message(chat_id, response, parse_mode='HTML', reply_markup=markup)
        store_bot_message(chat_id, msg.message_id)

    except Projects.DoesNotExist:
        send_telegram_message(ADMIN, f'Произошла ошибка при обновлении проектов: Project {project_id} not found')


@bot.callback_query_handler(func=lambda query: query.data.startswith('update_status_'))
def update_status_callback(query):
    try:
        _1, _2, project_id, new_status = query.data.split('_')
        chat_id = query.message.chat.id
        delete_messages(chat_id)

        project = Projects.get(id=project_id)
        trello = trello_wrapper(API_KEY, TOKEN)
        answer = trello.move_card(board_id, project.status, new_status, project.title)

        if answer == "Card not found in the source list.":
            bot.send_message(chat_id, f"Статус уже изменен")
        else:
            bot.send_message(chat_id, "Статус успешно обновлен")

    except Projects.DoesNotExist:
        send_telegram_message(ADMIN, f'Произошла ошибка при обновлении статуса проекта: Project {project_id} not found')
    except Exception as e:
        send_telegram_message(ADMIN, f'Произошла ошибка при обновлении статуса проекта: {e}')



@bot.callback_query_handler(lambda query: query.data.startswith('description_'))
def show_description(query):
    project_id = query.data.split('_')[1]
    chat_id = query.message.chat.id
    delete_messages(chat_id)
    try:
        description = Projects.get(id=project_id).description
        if not description:
            reply = bot.send_message(chat_id, "Описание отсутствует.")
            store_bot_message(chat_id, reply.message_id)
        else:
            reply = bot.send_message(chat_id, f"<u><b>Описание проекта</b></u>:\n\n{description}", parse_mode='HTML')
            store_bot_message(chat_id, reply.message_id)
    except Projects.DoesNotExist:
        send_telegram_message(ADMIN, f'Произошла ошибка при получении описания проекта: Project {project_id} not found')



@bot.callback_query_handler(lambda query: query.data.startswith('comments_'))
def show_comments(query):
    project_id = query.data.split('_')[1]
    chat_id = query.message.chat.id
    delete_messages(chat_id)
    try:
        comments = Projects.get(id=project_id).comments

        if not comments:
            reply = bot.send_message(chat_id, "Комментариев нет.")
            store_bot_message(chat_id, reply.message_id)
        else:
            comments_str = '\n\n'.join([f"{i[0]}({i[2]}): {i[1]}" for i in comments])

            reply = bot.send_message(chat_id, f"<u><b>Комментарии</b></u>:\n\n{comments_str}", parse_mode='HTML')
            store_bot_message(chat_id, reply.message_id)

    except Projects.DoesNotExist:
        send_telegram_message(ADMIN, f'Произошла ошибка при получении комментариев проекта: Project {project_id} not found')



@app.route('/WEBHOOK_PATH', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data(as_text=True)
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        abort(403)


if __name__ == "__main__":
    background_thread = threading.Thread(target=perform_regular_task, daemon=True)
    background_thread.start()
    app.run(host="0.0.0.0", port=int("8080"), debug=True)
